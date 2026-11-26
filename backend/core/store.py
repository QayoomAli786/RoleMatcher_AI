"""Session store — SQLite-backed with an in-memory cache.

Public functions keep the same signatures they had when this was a pure
in-memory dict, so callers do not change. Every write goes through to SQLite;
``init_store()`` loads persisted rows back into the caches at startup.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field

from backend.core import db


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
    db.put_object("resume", resume.id, asdict(resume), user_id=resume.user_id, created_at=resume.created_at or None)


def get_resume(rid: uuid.UUID) -> _Resume | None:
    resume = _resumes.get(rid)
    if resume is None:
        # Another serverless instance may have created it — check the database.
        record = db.get_object("resume", rid)
        if record:
            resume = _row_to_resume(record)
            _resumes[rid] = resume
    return resume


def list_resumes(user_id: uuid.UUID) -> list[_Resume]:
    for record in db.list_objects("resume", user_id):
        resume = _row_to_resume(record)
        _resumes[resume.id] = resume
    return sorted(
        [r for r in _resumes.values() if r.user_id == user_id],
        key=lambda r: r.created_at,
        reverse=True,
    )


def delete_resume(rid: uuid.UUID) -> bool:
    deleted = db.delete_object("resume", rid)
    cached = _resumes.pop(rid, None) is not None
    return deleted or cached


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
    db.put_object("application", app.id, asdict(app), user_id=app.user_id)


def get_application(aid: uuid.UUID) -> _Application | None:
    application = _applications.get(aid)
    if application is None:
        record = db.get_object("application", aid)
        if record:
            application = _row_to_application(record)
            _applications[aid] = application
    return application


def list_applications(user_id: uuid.UUID) -> list[_Application]:
    for record in db.list_objects("application", user_id):
        application = _row_to_application(record)
        _applications[application.id] = application
    return [a for a in _applications.values() if a.user_id == user_id]


def delete_application(aid: uuid.UUID) -> bool:
    deleted = db.delete_object("application", aid)
    cached = _applications.pop(aid, None) is not None
    return deleted or cached


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
    db.put_object("conversation", conv.id, asdict(conv), user_id=conv.user_id)


def get_conversation(cid: uuid.UUID) -> _Conversation | None:
    conversation = _conversations.get(cid)
    if conversation is None:
        record = db.get_object("conversation", cid)
        if record:
            conversation = _row_to_conversation(record)
            _conversations[cid] = conversation
    return conversation


def list_conversations(user_id: uuid.UUID) -> list[_Conversation]:
    for record in db.list_objects("conversation", user_id):
        conversation = _row_to_conversation(record)
        _conversations[conversation.id] = conversation
    return sorted(
        [c for c in _conversations.values() if c.user_id == user_id],
        key=lambda c: c.id,
        reverse=True,
    )


def delete_conversation(cid: uuid.UUID) -> bool:
    deleted = db.delete_object("conversation", cid)
    cached = _conversations.pop(cid, None) is not None
    return deleted or cached


# ── Generic Stores for Other Features ─────────────────────────────────────────

class _GenericStore(dict):
    """A dict that knows its persistence ``kind`` for write-through."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind


_interviews = _GenericStore("interview")
_cover_letters = _GenericStore("cover_letter")
_ats_reports = _GenericStore("ats_report")
_career_plans = _GenericStore("career_plan")
_job_matches = _GenericStore("job_match")
_reviews = _GenericStore("review")
_optimized_resumes = _GenericStore("optimized_resume")

_GENERIC_STORES: dict[str, _GenericStore] = {
    s.kind: s for s in (
        _interviews, _cover_letters, _ats_reports, _career_plans,
        _job_matches, _reviews, _optimized_resumes,
    )
}


def store_generic(store: dict, key: uuid.UUID, value: dict) -> None:
    store[key] = value
    kind = getattr(store, "kind", None)
    if kind:
        db.put_object(kind, key, value, user_id=value.get("user_id"))


def get_generic(store: dict, key: uuid.UUID) -> dict | None:
    result = store.get(key)
    if result is None:
        kind = getattr(store, "kind", None)
        if kind:
            record = db.get_object(kind, key)
            if record:
                result = record["data"]
                store[key] = result
    return result


def list_generic(store: dict, user_id: uuid.UUID) -> list[dict]:
    kind = getattr(store, "kind", None)
    if kind:
        for record in db.list_objects(kind, user_id):
            try:
                store[uuid.UUID(record["id"])] = record["data"]
            except ValueError:
                continue
    # user_id may be a UUID or a str (depends on whether the entry was loaded
    # from SQLite after a restart), hence the str() normalization.
    return [v for v in store.values() if str(v.get("user_id")) == str(user_id)]


def list_all_generic(store: dict) -> list[dict]:
    """Return all entries in a generic store (for shared/public data)."""
    kind = getattr(store, "kind", None)
    if kind:
        for record in db.list_objects(kind):
            try:
                store[uuid.UUID(record["id"])] = record["data"]
            except ValueError:
                continue
    return list(store.values())


# ── Startup load ──────────────────────────────────────────────────────────────


def _revive_user_id(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return value


def _row_to_resume(rec: dict) -> _Resume:
    d = rec["data"]
    return _Resume(
        id=uuid.UUID(rec["id"]),
        user_id=uuid.UUID(rec["user_id"]),
        original_filename=d.get("original_filename", ""),
        raw_text=d.get("raw_text", ""),
        parsed_profile=d.get("parsed_profile") or {},
        parsing_status=d.get("parsing_status", "pending"),
        created_at=rec["created_at"],
        versions=d.get("versions") or [],
    )


def _row_to_application(rec: dict) -> _Application:
    d = rec["data"]
    return _Application(
        id=uuid.UUID(rec["id"]),
        user_id=uuid.UUID(rec["user_id"]),
        job_id=_revive_user_id(d["job_id"]) if d.get("job_id") else None,
        resume_id=_revive_user_id(d["resume_id"]) if d.get("resume_id") else None,
        status=d.get("status", "saved"),
        notes=d.get("notes", ""),
    )


def _row_to_conversation(rec: dict) -> _Conversation:
    d = rec["data"]
    return _Conversation(
        id=uuid.UUID(rec["id"]),
        user_id=uuid.UUID(rec["user_id"]),
        title=d.get("title", "New Chat"),
        messages=d.get("messages") or [],
    )


def init_store() -> None:
    """Create the schema and warm the in-memory caches.

    With Postgres the caches are hydrated on demand by the get/list helpers,
    so a cold start only needs the schema check — not a full table scan.
    """
    db.init_db()
    if db.uses_postgres():
        return

    for rec in db.list_objects("resume"):
        r = _row_to_resume(rec)
        _resumes[r.id] = r
    for rec in db.list_objects("application"):
        a = _row_to_application(rec)
        _applications[a.id] = a
    for rec in db.list_objects("conversation"):
        c = _row_to_conversation(rec)
        _conversations[c.id] = c

    for kind, store in _GENERIC_STORES.items():
        for rec in db.list_objects(kind):
            try:
                store[uuid.UUID(rec["id"])] = rec["data"]
            except ValueError:
                continue
