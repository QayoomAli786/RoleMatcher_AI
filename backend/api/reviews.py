"""Review endpoints — public user reviews shared across all visitors."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.schemas import UserProfile
from backend.core.store import _reviews, list_all_generic, store_generic
from backend.security.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews")


class _ReviewBody(BaseModel):
    name: str
    email: str
    review: str
    profession: str = ""


def _review_dict(rid: uuid.UUID, body: _ReviewBody, user_id: uuid.UUID) -> dict:
    return {
        "review_id": str(rid),
        "user_id": user_id,
        "name": body.name.strip(),
        "email": body.email.strip(),
        "review": body.review.strip(),
        "profession": body.profession.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("", status_code=201)
async def create_review(body: _ReviewBody, user: UserProfile = Depends(get_current_user)):
    """Add a new public review."""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if not body.email.strip() or "@" not in body.email:
        raise HTTPException(status_code=400, detail="A valid email is required")
    if not body.review.strip():
        raise HTTPException(status_code=400, detail="Review text is required")

    rid = uuid.uuid4()
    review = _review_dict(rid, body, user.id)
    store_generic(_reviews, rid, review)
    return review


@router.get("")
async def list_reviews(user: UserProfile = Depends(get_current_user)):
    """List all public reviews, newest first."""
    reviews = list_all_generic(_reviews)
    reviews.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return {"reviews": reviews}