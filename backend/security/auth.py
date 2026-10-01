"""Simple auth — always returns guest user (no authentication)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header

from backend.core.config import get_settings
from backend.core.schemas import UserProfile
from backend.core.store import ensure_user

settings = get_settings()

GUEST_USER = UserProfile(
    id=UUID("00000000-0000-0000-0000-000000000001"),
    email="guest@careercopilot.local",
    name="Guest User",
    created_at=datetime.now(timezone.utc),
    preferences={},
)


async def get_current_user() -> UserProfile:
    """Always returns the guest user — no authentication required."""
    ensure_user(GUEST_USER.id, GUEST_USER.email, GUEST_USER.name)
    return GUEST_USER


get_current_user_dependency = Depends(get_current_user)
