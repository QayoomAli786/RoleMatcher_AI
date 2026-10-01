"""Applications endpoints — in-memory storage."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.schemas import UserProfile
from backend.core.store import (
    _Application,
    get_application,
    list_applications,
    save_application,
    delete_application as _del_application,
)
from backend.security.auth import get_current_user

router = APIRouter(prefix="/applications")


class _AppBody(BaseModel):
    job_id: str | None = None
    resume_id: str | None = None


@router.post("", status_code=201)
async def create_application(body: _AppBody, user: UserProfile = Depends(get_current_user)):
    app_id = uuid.uuid4()
    app = _Application(
        id=app_id,
        user_id=user.id,
        job_id=uuid.UUID(body.job_id) if body.job_id else None,
        resume_id=uuid.UUID(body.resume_id) if body.resume_id else None,
    )
    save_application(app)
    return {"id": str(app_id), "status": app.status}


@router.get("")
async def list_user_applications(user: UserProfile = Depends(get_current_user)):
    apps = list_applications(user.id)
    return {"applications": [{"id": str(a.id), "status": a.status} for a in apps]}


@router.patch("/{app_id}")
async def update_application(app_id: uuid.UUID, user: UserProfile = Depends(get_current_user)):
    app = get_application(app_id)
    if app is None or app.user_id != user.id:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"id": str(app.id), "status": app.status}


@router.get("/analytics")
async def get_analytics(user: UserProfile = Depends(get_current_user)):
    return {"total": 0, "by_status": {}}
