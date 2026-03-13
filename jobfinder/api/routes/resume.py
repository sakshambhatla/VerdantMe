from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, UploadFile

from jobfinder.config import load_config
from jobfinder.resume.parser import parse_resumes
from jobfinder.storage.store import StorageManager

router = APIRouter()


@router.post("/resume/upload")
async def upload_resume(file: UploadFile) -> dict:
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

    store = StorageManager(config.data_dir)
    store.write("resumes.json", [r.model_dump() for r in resumes])

    return {"resumes": [r.model_dump() for r in resumes]}


@router.get("/resume")
async def get_resume() -> dict:
    """Return the most recently parsed resume data."""
    config = load_config()
    store = StorageManager(config.data_dir)
    data = store.read("resumes.json")
    if data is None:
        raise HTTPException(status_code=404, detail="No resume found. Upload one first.")
    return {"resumes": data}
