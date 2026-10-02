"""Simple auth — always returns guest user (no authentication)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from backend.core.schemas import UserProfile

GUEST_USER = UserProfile(
    id=UUID("00000000-0000-0000-0000-000000000001"),
    email="guest@careercopilot.local",
    name="Guest User",
    created_at=datetime.now(timezone.utc),
    preferences={},
)


async def get_current_user() -> UserProfile:
    """Always returns the guest user — no authentication required."""
    return GUEST_USER
