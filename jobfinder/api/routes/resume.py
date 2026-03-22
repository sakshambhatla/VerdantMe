from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from jobfinder.api.auth import get_current_user
from jobfinder.config import load_config
from jobfinder.resume.parser import parse_resumes, parse_single_resume
from jobfinder.storage import get_storage_backend

router = APIRouter()


@router.post("/resume/upload")
async def upload_resume(
    file: UploadFile,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Upload a .txt resume file. Appends to existing resumes (multi-resume)."""
    user_id, jwt_token = _auth if _auth else (None, None)

    # Sanitize: strip any directory components to prevent path traversal.
    safe_filename = Path(file.filename or "").name
    if not safe_filename or not safe_filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt resume files are supported.")

    content = await file.read()
    if len(content) > 512_000:
        raise HTTPException(status_code=413, detail="Resume file too large. Maximum size is 500 KB.")

    store = get_storage_backend(user_id, jwt_token)

    if os.environ.get("SUPABASE_URL"):
        # Managed/cloud mode: parse in memory — no disk write needed.
        # The .txt files would be lost on container restart anyway.
        text = content.decode("utf-8", errors="replace")
        parsed_resume = await asyncio.to_thread(parse_single_resume, safe_filename, text)

        existing_data = store.read("resumes.json") or []
        existing_by_filename: dict[str, dict] = {
            r.get("filename", ""): r
            for r in existing_data
            if isinstance(r, dict)
        }
        dumped = parsed_resume.model_dump()
        if safe_filename in existing_by_filename:
            dumped["id"] = existing_by_filename[safe_filename].get("id", dumped["id"])
        # Replace entry for this filename; append if new
        updated = [r for r in existing_data if r.get("filename") != safe_filename] + [dumped]
        store.write("resumes.json", updated)
        return {"resumes": updated}

    # Local mode: write .txt to disk, then parse all files in the directory.
    config = load_config()
    resume_dir = config.resume_dir
    resume_dir.mkdir(parents=True, exist_ok=True)

    dest = resume_dir / safe_filename
    dest.write_bytes(content)

    all_parsed = await asyncio.to_thread(parse_resumes, resume_dir)

    existing_data = store.read("resumes.json") or []
    existing_by_filename = {}
    if isinstance(existing_data, list):
        for r in existing_data:
            existing_by_filename[r.get("filename", "")] = r

    result = []
    for r in all_parsed:
        dumped = r.model_dump()
        if r.filename in existing_by_filename:
            dumped["id"] = existing_by_filename[r.filename].get("id", dumped["id"])
        result.append(dumped)

    store.write("resumes.json", result)
    return {"resumes": result}


@router.get("/resume")
async def get_resume(_auth: tuple[str, str] | None = Depends(get_current_user)) -> dict:
    """Return the most recently parsed resume data."""
    user_id, jwt_token = _auth if _auth else (None, None)
    store = get_storage_backend(user_id, jwt_token)
    data = store.read("resumes.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No resume found. Upload one first.")
    return {"resumes": data}


@router.delete("/resume/{filename}")
async def delete_resume(
    filename: str,
    _auth: tuple[str, str] | None = Depends(get_current_user),
) -> dict:
    """Remove a resume entry from resumes.json and delete its .txt file if present."""
    user_id, jwt_token = _auth if _auth else (None, None)
    config = load_config()
    store = get_storage_backend(user_id, jwt_token)
    data = store.read("resumes.json") or []

    updated = [r for r in data if r.get("filename") != filename]
    if len(updated) == len(data):
        raise HTTPException(status_code=404, detail=f"Resume '{filename}' not found.")

    store.write("resumes.json", updated)

    # Best-effort: delete the .txt file if it still exists.
    # Sanitize filename to prevent path traversal (e.g. "../../config.json").
    safe_filename = Path(filename).name
    txt_path = config.resume_dir / safe_filename
    if txt_path.exists():
        txt_path.unlink()

    return {"resumes": updated}
