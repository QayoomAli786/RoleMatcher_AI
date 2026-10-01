"""Resume management endpoints — in-memory storage."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status

from backend.core.schemas import UserProfile
from backend.core.store import (
    _Resume,
    get_resume,
    list_resumes,
    save_resume,
    delete_resume as _del_resume,
)
from backend.security.auth import get_current_user
from backend.security.sanitization import sanitize_file_upload
from backend.services.resume_parser import extract_text_from_bytes, parse_resume_from_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resumes")


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: Annotated[UploadFile, File()],
    user: UserProfile = Depends(get_current_user),
):
    """Upload a resume file (PDF/DOCX/TXT). Parsing runs synchronously."""
    raw = await sanitize_file_upload(file)

    # DOCX/PDF are binary — decode them properly instead of as UTF-8 text
    _text = extract_text_from_bytes(raw, file.filename or "")[:100_000]
    _text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", _text)

    resume_id = uuid.uuid4()
    content_hash = hashlib.sha256(_text.encode()).hexdigest()

    # Parse synchronously
    try:
        profile = parse_resume_from_text(_text, content_hash=content_hash)
        parsed = profile.model_dump()
        word_count = len(_text.split())
        sections_found = sum(1 for v in [
            profile.skills, profile.experience, profile.education,
            profile.projects, profile.certifications,
        ] if v)
        parsing_status = "completed"
    except Exception as exc:
        logger.warning("Resume parsing failed: %s", exc)
        parsed = {}
        word_count = 0
        sections_found = 0
        parsing_status = "failed"

    now = datetime.now(timezone.utc).isoformat()
    resume = _Resume(
        id=resume_id,
        user_id=user.id,
        original_filename=file.filename or "resume.pdf",
        raw_text=_text,
        parsed_profile=parsed,
        parsing_status=parsing_status,
        created_at=now,
        versions=[{
            "id": str(uuid.uuid4()),
            "version_number": 1,
            "content_hash": content_hash,
            "created_at": now,
        }],
    )
    save_resume(resume)

    return {
        "resume_id": str(resume.id),
        "status": parsing_status,
        "filename": file.filename,
        "word_count": word_count,
        "sections_found": sections_found,
        "summary": profile.summary if parsing_status == "completed" else "",
    }


@router.get("")
async def list_user_resumes(user: UserProfile = Depends(get_current_user)):
    rows = list_resumes(user.id)
    return {
        "resumes": [
            {
                "id": str(r.id),
                "filename": r.original_filename,
                "status": r.parsing_status,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


@router.get("/{resume_id}")
async def get_resume_detail(
    resume_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
):
    resume = get_resume(resume_id)
    if resume is None or resume.user_id != user.id:
        raise HTTPException(status_code=404, detail="Resume not found")

    profile = resume.parsed_profile or {}
    word_count = len(resume.raw_text.split())
    sections_found = sum(1 for v in [
        profile.get("skills"), profile.get("experience"), profile.get("education"),
        profile.get("projects"), profile.get("certifications"),
    ] if v)

    return {
        "id": str(resume.id),
        "filename": resume.original_filename,
        "status": resume.parsing_status,
        "parsed_profile": profile,
        "word_count": word_count,
        "sections_found": sections_found,
        "summary": profile.get("summary", ""),
        "versions": resume.versions,
    }


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume_endpoint(
    resume_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
):
    resume = get_resume(resume_id)
    if resume is None or resume.user_id != user.id:
        raise HTTPException(status_code=404, detail="Resume not found")
    _del_resume(resume_id)
