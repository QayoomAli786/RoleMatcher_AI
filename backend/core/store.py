"""In-memory session store — data lives until the process restarts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


# ── User Store ────────────────────────────────────────────────────────────────

@dataclass
class _User:
    id: uuid.UUID
    email: str
    name: str
    hashed_password: str = ""


_users_by_email: dict[str, _User] = {}
_users_by_id: dict[uuid.UUID, _User] = {}


def create_user(email: str, name: str, hashed_password: str = "") -> _User:
    uid = uuid.uuid4()
    user = _User(id=uid, email=email, name=name, hashed_password=hashed_password)
    _users_by_email[email] = user
    _users_by_id[uid] = user
    return user


def get_user_by_email(email: str) -> _User | None:
    return _users_by_email.get(email)


def get_user_by_id(uid: uuid.UUID) -> _User | None:
    return _users_by_id.get(uid)


def ensure_user(uid: uuid.UUID, email: str, name: str) -> _User:
    if uid in _users_by_id:
        return _users_by_id[uid]
    user = _User(id=uid, email=email, name=name)
    _users_by_id[uid] = user
    _users_by_email[email] = user
    return user


# ── Resume Store ──────────────────────────────────────────────────────────────

@dataclass
class _Resume:
    id: uuid.UUID
    user_id: uuid.UUID
    original_filename: str
    raw_text: str
    parsed_profile: dict = field(default_factory=dict)
    parsing_status: str = "pending"
    created_at: str = ""
    versions: list[dict] = field(default_factory=list)


_resumes: dict[uuid.UUID, _Resume] = {}


def save_resume(resume: _Resume) -> None:
    _resumes[resume.id] = resume


def get_resume(rid: uuid.UUID) -> _Resume | None:
    return _resumes.get(rid)


def list_resumes(user_id: uuid.UUID) -> list[_Resume]:
    return sorted(
        [r for r in _resumes.values() if r.user_id == user_id],
        key=lambda r: r.created_at,
        reverse=True,
    )


def delete_resume(rid: uuid.UUID) -> bool:
    return _resumes.pop(rid, None) is not None


# ── Application Store ─────────────────────────────────────────────────────────

@dataclass
class _Application:
    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID | None = None
    resume_id: uuid.UUID | None = None
    status: str = "saved"
    notes: str = ""


_applications: dict[uuid.UUID, _Application] = {}


def save_application(app: _Application) -> None:
    _applications[app.id] = app


def get_application(aid: uuid.UUID) -> _Application | None:
    return _applications.get(aid)


def list_applications(user_id: uuid.UUID) -> list[_Application]:
    return [a for a in _applications.values() if a.user_id == user_id]


def delete_application(aid: uuid.UUID) -> bool:
    return _applications.pop(aid, None) is not None


# ── Conversation Store ────────────────────────────────────────────────────────

@dataclass
class _Conversation:
    id: uuid.UUID
    user_id: uuid.UUID
    title: str = "New Chat"
    messages: list[dict] = field(default_factory=list)


_conversations: dict[uuid.UUID, _Conversation] = {}


def save_conversation(conv: _Conversation) -> None:
    _conversations[conv.id] = conv


def get_conversation(cid: uuid.UUID) -> _Conversation | None:
    return _conversations.get(cid)


def list_conversations(user_id: uuid.UUID) -> list[_Conversation]:
    return sorted(
        [c for c in _conversations.values() if c.user_id == user_id],
        key=lambda c: c.id,
        reverse=True,
    )


def delete_conversation(cid: uuid.UUID) -> bool:
    return _conversations.pop(cid, None) is not None


# ── Generic Stores for Other Features ─────────────────────────────────────────

_interviews: dict[uuid.UUID, dict] = {}
_cover_letters: dict[uuid.UUID, dict] = {}
_ats_reports: dict[uuid.UUID, dict] = {}
_career_plans: dict[uuid.UUID, dict] = {}
_job_matches: dict[uuid.UUID, dict] = {}
_reviews: dict[uuid.UUID, dict] = {}
_optimized_resumes: dict[uuid.UUID, dict] = {}


def store_generic(store: dict, key: uuid.UUID, value: dict) -> None:
    store[key] = value


def get_generic(store: dict, key: uuid.UUID) -> dict | None:
    return store.get(key)


def list_generic(store: dict, user_id: uuid.UUID) -> list[dict]:
    return [v for v in store.values() if v.get("user_id") == user_id]


def list_all_generic(store: dict) -> list[dict]:
    """Return all entries in a generic store (for shared/public data)."""
    return list(store.values())


def delete_generic(store: dict, key: uuid.UUID) -> bool:
    return store.pop(key, None) is not None
