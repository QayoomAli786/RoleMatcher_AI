"""Auth endpoints — disabled (no authentication required)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/auth")


@router.get("/me")
async def me():
    return {"id": "00000000-0000-0000-0000-000000000001", "email": "guest@careercopilot.local", "name": "Guest User"}
