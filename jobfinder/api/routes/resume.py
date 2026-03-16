from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from jobfinder.api.auth import get_current_user
from jobfinder.config import load_config
from jobfinder.resume.parser import parse_resumes
from jobfinder.storage import get_storage_backend

router = APIRouter()


@router.post("/resume/upload")
async def upload_resume(
    file: UploadFile,
    user_id: str | None = Depends(get_current_user),
) -> dict:
    """Upload a .txt resume file. Clears the resume directory first."""
    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt resume files are supported.")

    content = await file.read()
    if len(content) > 512_000:
        raise HTTPException(status_code=413, detail="Resume file too large. Maximum size is 500 KB.")

    config = load_config()
    resume_dir = config.resume_dir
    resume_dir.mkdir(parents=True, exist_ok=True)

    # Clear existing .txt files (single-resume mode)
    for existing in resume_dir.glob("*.txt"):
        existing.unlink()

    # Save the uploaded file
    dest = resume_dir / file.filename
    dest.write_bytes(content)

    # Parse in a thread (file I/O + regex, not CPU-heavy but keeps event loop free)
    resumes = await asyncio.to_thread(parse_resumes, resume_dir)

    store = get_storage_backend(user_id)
    store.write("resumes.json", [r.model_dump() for r in resumes])

    return {"resumes": [r.model_dump() for r in resumes]}


@router.get("/resume")
async def get_resume(user_id: str | None = Depends(get_current_user)) -> dict:
    """Return the most recently parsed resume data."""
    store = get_storage_backend(user_id)
    data = store.read("resumes.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No resume found. Upload one first.")
    return {"resumes": data}


@router.delete("/resume/{filename}")
async def delete_resume(
    filename: str,
    user_id: str | None = Depends(get_current_user),
) -> dict:
    """Remove a resume entry from resumes.json and delete its .txt file if present."""
    config = load_config()
    store = get_storage_backend(user_id)
    data = store.read("resumes.json") or []

    updated = [r for r in data if r.get("filename") != filename]
    if len(updated) == len(data):
        raise HTTPException(status_code=404, detail=f"Resume '{filename}' not found.")

    store.write("resumes.json", updated)

    # Best-effort: delete the .txt file if it still exists
    txt_path = config.resume_dir / filename
    if txt_path.exists():
        txt_path.unlink()

    return {"resumes": updated}
