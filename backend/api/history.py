"""History endpoint — combined recent activity for the signed-in user."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core import db
from backend.core.schemas import UserProfile
from backend.security.auth import get_current_user

router = APIRouter(prefix="/history")

# kind -> (label, font-awesome icon)
_KINDS = {
    "resume": ("Resume", "fa-file-alt"),
    "cover_letter": ("Cover Letter", "fa-pen-fancy"),
    "career_plan": ("Career Plan", "fa-chart-line"),
    "job_match": ("Job Match", "fa-briefcase"),
    "interview": ("Interview", "fa-comments"),
    "optimized_resume": ("Tailored Resume", "fa-wand-magic-sparkles"),
    "application": ("Application", "fa-paper-plane"),
    "conversation": ("Chat", "fa-robot"),
}


def _title(kind: str, data: dict) -> str:
    if kind == "resume":
        return data.get("original_filename") or "Resume"
    if kind == "cover_letter":
        parts = [data.get("company_name"), data.get("job_title")]
        return " — ".join(p for p in parts if p) or "Cover Letter"
    if kind == "career_plan":
        return data.get("target_role") or "Career Plan"
    if kind == "job_match":
        role = data.get("target_role") or "Job search"
        count = len(data.get("jobs") or [])
        return f"{role} — {count} match{'' if count == 1 else 'es'}"
    if kind == "interview":
        return data.get("job_role") or "Interview session"
    if kind == "optimized_resume":
        parts = [data.get("company_name"), data.get("job_title")]
        return " — ".join(p for p in parts if p) or "Tailored resume"
    if kind == "conversation":
        return data.get("title") or "Chat"
    if kind == "application":
        return data.get("status") or "Application"
    return kind


@router.get("")
async def get_history(user: UserProfile = Depends(get_current_user)):
    items = []
    for kind, (label, icon) in _KINDS.items():
        for rec in db.list_objects(kind, user.id):
            items.append(
                {
                    "type": kind,
                    "label": label,
                    "icon": icon,
                    "id": rec["id"],
                    "title": _title(kind, rec["data"]),
                    "created_at": rec["created_at"],
                }
            )
    items.sort(key=lambda item: item["created_at"] or "", reverse=True)
    return {"items": items[:100]}
