"""Persistence layer — SQLite locally, Neon/Postgres when ``DATABASE_URL`` is set.

One connection (guarded by a lock) shared by the whole process. Feature data is
stored as JSON in a generic ``objects`` table keyed by ``(kind, id)``; users and
session tokens get their own tables. The public API is identical for both
backends, so the rest of the application does not need to know which is in use.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from backend.core.config import get_settings

_lock = threading.RLock()
_conn = None


# ── Backend selection / connection handling ────────────────────────────────────


def _postgres() -> bool:
    return bool(get_settings().database_url)


def uses_postgres() -> bool:
    """Public helper: True when Neon/Postgres backs the store."""
    return _postgres()


def _db_file() -> Path:
    path = Path(get_settings().sqlite_path)
    if not path.is_absolute():
        # backend/core/db.py -> repo root
        path = Path(__file__).resolve().parents[2] / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _get_conn():
    global _conn
    if _conn is not None:
        return _conn
    with _lock:
        if _conn is None:
            if _postgres():
                import psycopg
                from psycopg.rows import dict_row

                _conn = psycopg.connect(
                    get_settings().database_url,
                    autocommit=True,
                    row_factory=dict_row,
                    # Neon's pooled connections are transaction-mode; psycopg's
                    # automatic prepared statements are disabled for safety.
                    prepare_threshold=0,
                    connect_timeout=10,
                )
            else:
                _conn = sqlite3.connect(str(_db_file()), check_same_thread=False)
                _conn.row_factory = sqlite3.Row
                _conn.execute("PRAGMA journal_mode=WAL")
        return _conn


def _reset_conn() -> None:
    """Drop a stale connection so the next query opens a fresh one."""
    global _conn
    with _lock:
        old, _conn = _conn, None
        if old is not None:
            try:
                old.close()
            except Exception:
                pass


def _sql(query: str) -> str:
    return query.replace("?", "%s") if _postgres() else query


def _connection_error(exc: Exception) -> bool:
    if not _postgres():
        return False
    from psycopg import InterfaceError, OperationalError

    return isinstance(exc, (OperationalError, InterfaceError))


def _unique_violation(exc: Exception) -> bool:
    if not _postgres():
        return isinstance(exc, sqlite3.IntegrityError)
    from psycopg.errors import UniqueViolation

    return isinstance(exc, UniqueViolation)


def _query(query: str, params: tuple = (), *, fetch: str = "one"):
    """Run a statement. ``fetch`` is ``one``, ``all`` or ``none`` (writes)."""
    with _lock:
        for attempt in range(2):
            conn = _get_conn()
            cur = None
            try:
                cur = conn.cursor()
                cur.execute(_sql(query), tuple(params))
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return cur.fetchall()
                result = cur.rowcount
                if not _postgres():
                    conn.commit()
                return result
            except Exception as exc:
                if attempt == 0 and _connection_error(exc):
                    _reset_conn()
                    continue
                raise
            finally:
                if cur is not None:
                    cur.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Schema (compatible with both SQLite and Postgres) ─────────────────────────

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id            TEXT PRIMARY KEY,
        email         TEXT UNIQUE NOT NULL,
        name          TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at    TEXT NOT NULL,
        preferences   TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token      TEXT PRIMARY KEY,
        user_id    TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS otp_codes (
        email      TEXT NOT NULL,
        purpose    TEXT NOT NULL,
        code       TEXT NOT NULL,
        payload    TEXT NOT NULL DEFAULT '{}',
        expires_at TEXT NOT NULL,
        PRIMARY KEY (email, purpose)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS objects (
        kind       TEXT NOT NULL,
        id         TEXT NOT NULL,
        user_id    TEXT,
        created_at TEXT NOT NULL,
        data       TEXT NOT NULL,
        PRIMARY KEY (kind, id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_objects_kind_user ON objects (kind, user_id)",
)


def init_db() -> None:
    with _lock:
        for statement in _DDL:
            _query(statement, fetch="none")


# ── Generic objects ───────────────────────────────────────────────────────────


def put_object(
    kind: str,
    obj_id: str | UUID,
    data: dict,
    user_id: str | UUID | None = None,
    created_at: str | None = None,
) -> str:
    """Upsert one object. Returns the row's creation timestamp."""
    created_at = created_at or now_iso()
    _query(
        "INSERT INTO objects (kind, id, user_id, created_at, data) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(kind, id) DO UPDATE SET user_id=excluded.user_id, data=excluded.data",
        (
            kind,
            str(obj_id),
            str(user_id) if user_id is not None else None,
            created_at,
            json.dumps(data, default=str),
        ),
        fetch="none",
    )
    return created_at


def get_object(kind: str, obj_id: str | UUID) -> dict | None:
    row = _query("SELECT * FROM objects WHERE kind=? AND id=?", (kind, str(obj_id)))
    return _row_to_object(row) if row else None


def list_objects(kind: str, user_id: str | UUID | None = None) -> list[dict]:
    if user_id is None:
        rows = _query(
            "SELECT * FROM objects WHERE kind=? ORDER BY created_at DESC", (kind,), fetch="all"
        )
    else:
        rows = _query(
            "SELECT * FROM objects WHERE kind=? AND user_id=? ORDER BY created_at DESC",
            (kind, str(user_id)),
            fetch="all",
        )
    return [_row_to_object(r) for r in rows]


def delete_object(kind: str, obj_id: str | UUID) -> bool:
    return _query("DELETE FROM objects WHERE kind=? AND id=?", (kind, str(obj_id)), fetch="none") > 0


def _row_to_object(row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "created_at": row["created_at"],
        "data": json.loads(row["data"]),
    }


# ── Users ─────────────────────────────────────────────────────────────────────


def create_user_row(
    user_id: UUID, email: str, name: str, password_hash: str, created_at: str, preferences: str = "{}"
) -> bool:
    """Insert a user. Returns False when the email is already registered."""
    try:
        _query(
            "INSERT INTO users (id, email, name, password_hash, created_at, preferences) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(user_id), email, name, password_hash, created_at, preferences),
            fetch="none",
        )
    except Exception as exc:
        if _unique_violation(exc):
            return False
        raise
    return True


def get_user_row_by_email(email: str) -> dict | None:
    row = _query("SELECT * FROM users WHERE email=?", (email,))
    return dict(row) if row else None


def get_user_row(user_id: str | UUID) -> dict | None:
    row = _query("SELECT * FROM users WHERE id=?", (str(user_id),))
    return dict(row) if row else None


# ── Sessions ──────────────────────────────────────────────────────────────────


def create_session(token: str, user_id: str | UUID, created_at: str) -> None:
    _query(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(token) DO UPDATE SET user_id=excluded.user_id, created_at=excluded.created_at",
        (token, str(user_id), created_at),
        fetch="none",
    )


def get_session_user_id(token: str) -> str | None:
    row = _query("SELECT user_id FROM sessions WHERE token=?", (token,))
    return row["user_id"] if row else None


def delete_session(token: str) -> None:
    _query("DELETE FROM sessions WHERE token=?", (token,), fetch="none")


def delete_sessions_for_user(user_id: str | UUID) -> None:
    """Sign the user out of every device (used after a password reset)."""
    _query("DELETE FROM sessions WHERE user_id=?", (str(user_id),), fetch="none")


# ── One-time codes (sign up verification / password reset) ────────────────────


def upsert_otp(email: str, purpose: str, code: str, expires_at: str, payload: str = "{}") -> None:
    _query(
        "INSERT INTO otp_codes (email, purpose, code, payload, expires_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(email, purpose) DO UPDATE SET code=excluded.code, "
        "payload=excluded.payload, expires_at=excluded.expires_at",
        (email, purpose, code, payload, expires_at),
        fetch="none",
    )


def get_otp(email: str, purpose: str) -> dict | None:
    row = _query("SELECT * FROM otp_codes WHERE email=? AND purpose=?", (email, purpose))
    return dict(row) if row else None


def delete_otp(email: str, purpose: str) -> None:
    _query("DELETE FROM otp_codes WHERE email=? AND purpose=?", (email, purpose), fetch="none")


# ── Password maintenance ──────────────────────────────────────────────────────


def update_user_password(user_id: str | UUID, password_hash: str) -> None:
    _query("UPDATE users SET password_hash=? WHERE id=?", (password_hash, str(user_id)), fetch="none")
