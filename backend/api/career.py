"""Career endpoints — field-based + resume-based plan generation via career_graph."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.schemas import UserProfile
from backend.core.store import _career_plans, get_resume, list_generic, store_generic
from backend.graphs.career_graph import career_pipeline
from backend.security.auth import get_current_user
from backend.services.llm_service import ModelRouter, TaskCategory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/career")

_router = ModelRouter()


class _PlanBody(BaseModel):
    target_role: str | None = None
    resume_id: str | None = None
    career_field: str | None = None


_INVALID_PROFESSION_MSG = (
    'Please enter a valid profession name (e.g. "Cardiologist", "Software Engineer")'
)

_PROFESSION_CHECK_PROMPT = (
    "Answer YES only if the text below is a recognizable job title or career field "
    "a person could build a career plan for. Answer NO if it is gibberish, random "
    "keyboard text, or something that is not a profession at all. "
    "Reply with a single word: YES or NO.\n\nText: {name}"
)


def _is_valid_profession(value: str) -> bool:
    """Shape gate: cheap, deterministic rejection of obviously broken input.

    Catches empties, symbol/number soup, and single-letter repeats without
    spending an LLM call. Deeper judgment ("asdf", "hello world") happens in
    ``_profession_looks_real``.
    """
    s = value.strip()
    letters = [c for c in s.lower() if c.isalpha()]
    if len(letters) < 2:
        return False
    compact = s.replace(" ", "")
    if not compact or len(letters) < 0.5 * len(compact):
        return False
    if len(set(letters)) == 1:
        return False
    return True


async def _profession_looks_real(name: str) -> bool:
    """LLM yes/no judgment for understandable profession names. Fails open."""
    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": _PROFESSION_CHECK_PROMPT.format(name=name)}],
            category=TaskCategory.CHAT,
            temperature=0.0,
            max_tokens=5,
        )
        return str(result).strip().upper().startswith("YES")
    except Exception as exc:
        # Never block a real user because the validator hiccuped.
        logger.warning("Profession validation failed, allowing %r: %s", name, exc)
        return True


@router.post("/plan")
async def generate_plan(body: _PlanBody, user: UserProfile = Depends(get_current_user)):
    """Generate a career plan either from a described field or from a resume."""
    target = (body.target_role or body.career_field or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Provide a target_role or career_field")
    if not _is_valid_profession(target) or not await _profession_looks_real(target):
        raise HTTPException(status_code=400, detail=_INVALID_PROFESSION_MSG)

    resume_id = uuid.UUID(body.resume_id) if body.resume_id else None
    resume_profile = None
    if resume_id:
        resume = get_resume(resume_id)
        if resume is not None:
            resume_profile = resume.parsed_profile

    try:
        result = await career_pipeline.ainvoke(
            {
                "user_id": user.id,
                "resume_id": resume_id or uuid.UUID("00000000-0000-0000-0000-000000000000"),
                "target_role": target,
                "resume_profile": resume_profile or {},
                "skill_gaps": [],
                "market_data": {},
                "plan": {},
            }
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