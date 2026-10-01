"""Cover letter endpoints — form-based + resume-based generation via cover_letter_graph."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.schemas import UserProfile
from backend.core.store import _cover_letters, get_resume, get_generic, list_generic, store_generic
from backend.graphs.orchestrator import run_cover_letter_pipeline
from backend.security.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cover-letters")


class _CoverLetterBody(BaseModel):
    resume_id: str | None = None
    company_name: str | None = None
    job_title: str | None = None
    job_description: str | None = None
    tone: str = "professional"


@router.post("", status_code=201)
async def generate_cover_letter(body: _CoverLetterBody, user: UserProfile = Depends(get_current_user)):
    """Generate a cover letter from form inputs (optionally using the resume)."""
    company = (body.company_name or "").strip() or "the company"
    title = (body.job_title or "").strip() or "the position"

    resume_id = uuid.UUID(body.resume_id) if body.resume_id else None
    resume_profile = {}
    resume_text = ""
    if resume_id:
        resume = get_resume(resume_id)
        if resume is not None:
            resume_profile = resume.parsed_profile or {}
            resume_text = resume.raw_text

    result = await run_cover_letter_pipeline(
        user_id=user.id,
        resume_id=resume_id or uuid.UUID("00000000-0000-0000-0000-000000000000"),
        job_description=body.job_description or "",
        job_title=title,
        company_name=company,
        tone=body.tone or "professional",
        resume_profile=resume_profile,
    )

    content = result.get("cover_letter", "")
    error = result.get("error")
    if error and not content:
        raise HTTPException(status_code=500, detail=error)

    cl_id = str(uuid.uuid4())
    store_generic(_cover_letters, uuid.UUID(cl_id), {
        "user_id": user.id,
        "company_name": company,
        "job_title": title,
        "tone": body.tone or "professional",
        "content": content,
        "created_at": str(uuid.uuid4()),
    })

    return {
        "cover_letter_id": cl_id,
        "content": content,
        "company_name": company,
        "job_title": title,
        "tone": body.tone or "professional",
    }


@router.get("/{cl_id}")
async def get_cover_letter(cl_id: uuid.UUID, user: UserProfile = Depends(get_current_user)):
    data = get_generic(_cover_letters, cl_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    return data


@router.get("")
async def list_cover_letters(user: UserProfile = Depends(get_current_user)):
    letters = list_generic(_cover_letters, user.id)
    return {"cover_letters": letters}