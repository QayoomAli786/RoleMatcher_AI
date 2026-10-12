"""SQLite persistence layer.

One connection (guarded by a lock) shared by the whole process. Feature data is
stored as JSON in a generic ``objects`` table keyed by ``(kind, id)``; users and
session tokens get their own tables.
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
_conn: sqlite3.Connection | None = None


def _db_file() -> Path:
    path = Path(get_settings().sqlite_path)
    if not path.is_absolute():
        # backend/core/db.py -> repo root
        path = Path(__file__).resolve().parents[2] / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(_db_file()), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
    return _conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with _lock:
        conn = get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                email         TEXT UNIQUE NOT NULL,
                name          TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                preferences   TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS otp_codes (
                email      TEXT NOT NULL,
                purpose    TEXT NOT NULL,
                code       TEXT NOT NULL,
                payload    TEXT NOT NULL DEFAULT '{}',
                expires_at TEXT NOT NULL,
                PRIMARY KEY (email, purpose)
            );
            CREATE TABLE IF NOT EXISTS objects (
                kind       TEXT NOT NULL,
                id         TEXT NOT NULL,
                user_id    TEXT,
                created_at TEXT NOT NULL,
                data       TEXT NOT NULL,
                PRIMARY KEY (kind, id)
            );
            CREATE INDEX IF NOT EXISTS idx_objects_kind_user ON objects (kind, user_id);
            """
        )
        conn.commit()


# ── Generic objects ───────────────────────────────────────────────────────────


def put_object(
    kind: str,
    obj_id: str | UUID,
    data: dict,
    user_id: str | UUID | None = None,
    created_at: str | None = None,
) -> str:
    """Upsert one object. Returns the row's creation timestamp."""
    with _lock:
        conn = get_conn()
        created_at = created_at or now_iso()
        conn.execute(
            "INSERT INTO objects (kind, id, user_id, created_at, data) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(kind, id) DO UPDATE SET user_id=excluded.user_id, data=excluded.data",
            (kind, str(obj_id), str(user_id) if user_id is not None else None, created_at, json.dumps(data, default=str)),
        )
        conn.commit()
    return created_at


def get_object(kind: str, obj_id: str | UUID) -> dict | None:
    row = get_conn().execute("SELECT * FROM objects WHERE kind=? AND id=?", (kind, str(obj_id))).fetchone()
    return _row_to_object(row) if row else None


def list_objects(kind: str, user_id: str | UUID | None = None) -> list[dict]:
    conn = get_conn()
    if user_id is None:
        rows = conn.execute("SELECT * FROM objects WHERE kind=? ORDER BY created_at DESC", (kind,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM objects WHERE kind=? AND user_id=? ORDER BY created_at DESC",
            (kind, str(user_id)),
        ).fetchall()
    return [_row_to_object(r) for r in rows]


def delete_object(kind: str, obj_id: str | UUID) -> bool:
    with _lock:
        conn = get_conn()
        cur = conn.execute("DELETE FROM objects WHERE kind=? AND id=?", (kind, str(obj_id)))
        conn.commit()
    return cur.rowcount > 0


def _row_to_object(row: sqlite3.Row) -> dict:
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
    with _lock:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO users (id, email, name, password_hash, created_at, preferences) VALUES (?, ?, ?, ?, ?, ?)",
                (str(user_id), email, name, password_hash, created_at, preferences),
            )
        except sqlite3.IntegrityError:
            return False
        conn.commit()
    return True


def get_user_row_by_email(email: str) -> dict | None:
    row = get_conn().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    return dict(row) if row else None


def get_user_row(user_id: str | UUID) -> dict | None:
    row = get_conn().execute("SELECT * FROM users WHERE id=?", (str(user_id),)).fetchone()
    return dict(row) if row else None


# ── Sessions ──────────────────────────────────────────────────────────────────


def create_session(token: str, user_id: str | UUID, created_at: str) -> None:
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, str(user_id), created_at),
        )
        conn.commit()


def get_session_user_id(token: str) -> str | None:
    row = get_conn().execute("SELECT user_id FROM sessions WHERE token=?", (token,)).fetchone()
    return row["user_id"] if row else None


def delete_session(token: str) -> None:
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()


def delete_sessions_for_user(user_id: str | UUID) -> None:
    """Sign the user out of every device (used after a password reset)."""
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM sessions WHERE user_id=?", (str(user_id),))
        conn.commit()


# ── One-time codes (sign up verification / password reset) ────────────────────


def upsert_otp(email: str, purpose: str, code: str, expires_at: str, payload: str = "{}") -> None:
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT INTO otp_codes (email, purpose, code, payload, expires_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(email, purpose) DO UPDATE SET code=excluded.code, "
            "payload=excluded.payload, expires_at=excluded.expires_at",
            (email, purpose, code, payload, expires_at),
        )
        conn.commit()


def get_otp(email: str, purpose: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM otp_codes WHERE email=? AND purpose=?", (email, purpose)
    ).fetchone()
    return dict(row) if row else None


def delete_otp(email: str, purpose: str) -> None:
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM otp_codes WHERE email=? AND purpose=?", (email, purpose))
        conn.commit()


# ── Password maintenance ──────────────────────────────────────────────────────


def update_user_password(user_id: str | UUID, password_hash: str) -> None:
    with _lock:
        conn = get_conn()
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, str(user_id)))
        conn.commit()
