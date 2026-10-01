"""Career endpoints — field-based + resume-based plan generation via career_graph."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.schemas import UserProfile
from backend.core.store import _career_plans, get_resume, get_generic, list_generic, store_generic
from backend.graphs.orchestrator import run_career_pipeline
from backend.security.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/career")


class _PlanBody(BaseModel):
    target_role: str | None = None
    resume_id: str | None = None
    career_field: str | None = None


@router.post("/plan")
async def generate_plan(body: _PlanBody, user: UserProfile = Depends(get_current_user)):
    """Generate a career plan either from a described field or from a resume."""
    target = (body.target_role or body.career_field or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Provide a target_role or career_field")

    resume_id = uuid.UUID(body.resume_id) if body.resume_id else None
    resume_profile = None
    if resume_id:
        resume = get_resume(resume_id)
        if resume is not None:
            resume_profile = resume.parsed_profile

    try:
            result = await run_career_pipeline(
            user_id=user.id,
            resume_id=resume_id or uuid.UUID("00000000-0000-0000-0000-000000000000"),
            target_role=target,
            resume_profile=resume_profile or {},
        )
    except Exception as exc:
        logger.error("Career pipeline failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Career plan generation failed: {exc}") from exc

    plan = result.get("plan", {})
    plan_id = str(uuid.uuid4())
    store_generic(_career_plans, uuid.UUID(plan_id), {
        "user_id": user.id,
        "target_role": target,
        "plan": plan,
    })

    return {
        "plan_id": plan_id,
        "target_role": target,
        "plan": plan,
        "skill_gaps": result.get("skill_gaps", []),
        "recommendations": result.get("recommendations", []),
    }


@router.get("/plan")
async def get_plans(user: UserProfile = Depends(get_current_user)):
    plans = list_generic(_career_plans, user.id)
    return {"plans": [p.get("plan") for p in plans]}


@router.get("/market")
async def get_market(user: UserProfile = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Market data not available in in-memory mode")


@router.get("/skill-gaps")
async def get_skill_gaps(user: UserProfile = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Skill gap analysis requires a resume")