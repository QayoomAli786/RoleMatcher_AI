"""Resume optimisation endpoints â€” tailor a resume to a job and serve it as DOCX."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from backend.core.schemas import UserProfile
from backend.core.store import (
    _job_matches,
    _optimized_resumes,
    get_generic,
    get_resume,
    list_generic,
    list_resumes,
    store_generic,
)
from backend.graphs.resume_optimizer_graph import resume_optimizer_pipeline
from backend.security.auth import get_current_user
from backend.services.docx_builder import build_resume_docx, resume_filename

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resume-optimizer")


class _TailorBody(BaseModel):
    resume_id: str | None = None
    job_id: str | None = None
    job_title: str | None = None
    company_name: str | None = None
    job_description: str | None = None


def _resolve_job(user: UserProfile, job_id: str | None) -> dict | None:
    """Look up a matched job across this user's stored search pipelines."""
    if not job_id:
        return None
    for match in list_generic(_job_matches, user.id):
        for job in match.get("jobs", []):
            jid = job.get("id") or job.get("job_id") or job.get("source_job_id")
            if jid is not None and str(jid) == str(job_id):
                return job
    return None


def _resolve_resume(user: UserProfile, resume_id: str | None):
    resume = None
    if resume_id:
        try:
            resume = get_resume(uuid.UUID(resume_id))
        except (ValueError, TypeError):
            pass
        if resume and resume.user_id != user.id:
            resume = None

    if resume is None:
        resumes = list_resumes(user.id)
        resume = resumes[0] if resumes else None
    return resume


@router.post("/tailor")
async def tailor_resume(
    body: _TailorBody,
    user: UserProfile = Depends(get_current_user),
):
    """Rewrite the candidate's resume so it is tailored to a specific job.

    Returns the structured resume plus the DOCX download id. Nothing outside
    the original resume is ever added.
    """
    resume = _resolve_resume(user, body.resume_id)
    if resume is None:
        raise HTTPException(status_code=400, detail="Upload a resume first to tailor your resume")

    job = _resolve_job(user, body.job_id)

    job_title = (body.job_title or "").strip() or (
        str(job.get("title", "")) if job else ""
    ).strip()
    company_name = (body.company_name or "").strip() or (
        str(job.get("company", "")) if job else ""
    ).strip()

    job_desc = (body.job_description or "").strip()
    if not job_desc and job:
        job_desc = job.get("description") or job.get("job_description") or ""
    if not job_desc and job:
        # Some sources do not fetch full descriptions â€” build a usable stub
        parts = []
        if job.get("title"):
            parts.append(f"Role: {job['title']}")
        if job.get("company"):
            parts.append(f"Company: {job['company']}")
        if job.get("skills"):
            parts.append(f"Required skills: {', '.join(job['skills'])}")
        if job.get("location"):
            parts.append(f"Location: {job['location']}")
        job_desc = "\n".join(parts)

    if not job_desc and not job_title:
        raise HTTPException(
            status_code=400,
            detail="This job has no information to tailor your resume against",
        )

    job_uuid = None
    raw_jid = (body.job_id or (job or {}).get("id"))
    if raw_jid:
        try:
            job_uuid = uuid.UUID(str(raw_jid))
        except (ValueError, TypeError):
            job_uuid = None

    try:
        result = await resume_optimizer_pipeline.ainvoke(
            {
                "user_id": user.id,
                "resume_id": resume.id,
                "job_id": job_uuid,
                "resume_text": resume.raw_text,
                "resume_profile": resume.parsed_profile or {},
                "job_description": job_desc,
                "job_title": job_title,
                "company_name": company_name,
                "target_keywords": [],
                "optimized": {},
                "stripped": [],
                "error": None,
            }
        )
    except Exception as exc:
        logger.error("Resume optimisation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Resume optimisation failed: {exc}") from exc

    optimized = result.get("optimized") or {}
    if not optimized:
        raise HTTPException(
            status_code=500,
            detail=result.get("error") or "Resume optimisation failed. Please try again.",
        )

    optimized_id = str(uuid.uuid4())
    store_generic(_optimized_resumes, uuid.UUID(optimized_id), {
        "user_id": user.id,
        "resume_id": str(resume.id),
        "optimized": optimized,
        "stripped": result.get("stripped", []),
        "job_title": optimized.get("target_role", job_title),
        "company_name": optimized.get("target_company", company_name),
        "filename": resume_filename(optimized),
    })

    return {
        "optimized_id": optimized_id,
        "optimized": optimized,
        "stripped": result.get("stripped", []),
        "job_title": optimized.get("target_role", job_title),
        "company_name": optimized.get("target_company", company_name),
        "filename": resume_filename(optimized),
    }


@router.get("/{optimized_id}/download")
async def download_optimized_resume(
    optimized_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
):
    """Download the tailored resume as a .docx file."""
    entry = get_generic(_optimized_resumes, optimized_id)
    if entry is None or entry.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Optimized resume not found")

    try:
        payload = build_resume_docx(entry.get("optimized") or {})
    except Exception:
        logger.exception("DOCX generation failed for %s", optimized_id)
        raise HTTPException(
            status_code=500,
            detail="Could not build the DOCX file. Please try again.",
        )

    filename = entry.get("filename") or "tailored-resume.docx"
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(payload)),
        },
    )


@router.get("/{optimized_id}")
async def get_optimized_resume(
    optimized_id: uuid.UUID,
    user: UserProfile = Depends(get_current_user),
):
    entry = get_generic(_optimized_resumes, optimized_id)
    if entry is None or entry.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Optimized resume not found")
    return entry


@router.get("")
async def list_optimized_resumes(user: UserProfile = Depends(get_current_user)):
    return {"resumes": list_generic(_optimized_resumes, user.id)}
