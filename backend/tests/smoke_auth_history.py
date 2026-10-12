"""Self-check for sign up (OTP) / sign in, password reset, per-user SQLite
persistence and history.

Run from anywhere:  python backend/tests/smoke_auth_history.py
Uses a throwaway SQLite file so it never touches the real data store.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

_db = Path(tempfile.gettempdir()) / f"rolematcher_check_{uuid.uuid4().hex}.db"
os.environ["CC_SQLITE_PATH"] = str(_db)

from fastapi.testclient import TestClient  # noqa: E402
from backend.main import app  # noqa: E402


def _code(email: str, purpose: str = "signup") -> str | None:
    """Read the OTP that would normally be emailed (here it prints to the terminal)."""
    conn = sqlite3.connect(str(_db))
    try:
        row = conn.execute(
            "SELECT code FROM otp_codes WHERE email=? AND purpose=?", (email, purpose)
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _signup(client: TestClient, email: str, password: str, name: str = "") -> dict:
    """Sign up + verify, returning the Authorization header."""
    res = client.post("/api/auth/signup", json={"email": email, "password": password, "name": name})
    assert res.status_code == 200, res.text
    assert res.json()["otp_required"] is True
    code = _code(email.lower())
    assert code, f"no signup code stored for {email}"
    res = client.post("/api/auth/verify-otp", json={"email": email, "otp": code})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def _run() -> None:
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

        # Everything is gated behind a session
        assert client.get("/api/auth/me").status_code == 401
        assert client.get("/api/history").status_code == 401

        # Sign up is Gmail-only and needs a strong password
        assert client.post("/api/auth/signup", json={"email": "nope", "password": "Secret1!"}).status_code == 400
        assert client.post("/api/auth/signup", json={"email": "x@yahoo.com", "password": "Secret1!"}).status_code == 400
        assert client.post("/api/auth/signup", json={"email": "weak@gmail.com", "password": "secret1"}).status_code == 400
        assert client.post("/api/auth/signup", json={"email": "weak@gmail.com", "password": "short1!"}).status_code == 400

        # Sign up stores a code; only the correct code creates the account
        assert client.post(
            "/api/auth/signup", json={"email": "Ali@Gmail.com", "password": "Secret1!", "name": "Ali"}
        ).status_code == 200
        assert client.post(
            "/api/auth/verify-otp", json={"email": "ali@gmail.com", "otp": "000000"}
        ).status_code == 400
        code = _code("ali@gmail.com")
        assert code
        res = client.post("/api/auth/verify-otp", json={"email": "ali@gmail.com", "otp": code})
        assert res.status_code == 200, res.text
        headers = {"Authorization": f"Bearer {res.json()['token']}"}
        assert client.get("/api/auth/me", headers=headers).json()["email"] == "ali@gmail.com"

        # The code is single-use; re-signing up for a taken email is rejected
        assert client.post(
            "/api/auth/verify-otp", json={"email": "ali@gmail.com", "otp": code}
        ).status_code == 400
        assert client.post(
            "/api/auth/signup", json={"email": "ali@gmail.com", "password": "Secret1!"}
        ).status_code == 400

        # Wrong password rejected, correct one issues a working token
        assert client.post("/api/auth/login", json={"email": "ali@gmail.com", "password": "nope"}).status_code == 401
        res = client.post("/api/auth/login", json={"email": "ali@gmail.com", "password": "Secret1!"})
        headers = {"Authorization": f"Bearer {res.json()['token']}"}

        assert client.get("/api/history", headers=headers).json()["items"] == []

        # A resume and a chat both show up in history
        res = client.post(
            "/api/resumes",
            headers=headers,
            files={"file": ("my_resume.txt", b"Software Engineer\nSkills: Python, FastAPI\n", "text/plain")},
        )
        assert res.status_code == 201, res.text
        res = client.post("/api/chat", headers=headers, json={"message": "hello there"})
        assert res.status_code == 200, res.text
        conv_id = res.json()["conversation_id"]
        client.post("/api/chat", headers=headers, json={"message": "again", "conversation_id": conv_id})

        items = client.get("/api/history", headers=headers).json()["items"]
        types = {item["type"] for item in items}
        assert "resume" in types and "conversation" in types, items
        assert len([i for i in items if i["type"] == "conversation"]) == 1, items

        # History is per-user
        bob = _signup(client, "bob@gmail.com", "Secret2!", "Bob")
        assert client.get("/api/history", headers=bob).json()["items"] == []

        # Sign out revokes the token
        assert client.post("/api/auth/logout", headers=headers).status_code == 200
        assert client.get("/api/auth/me", headers=headers).status_code == 401

        # Password reset: unknown emails stay silent, known ones get a code
        assert client.post("/api/auth/forgot-password", json={"email": "ghost@example.com"}).status_code == 200
        assert client.post("/api/auth/forgot-password", json={"email": "ali@gmail.com"}).status_code == 200
        reset_code = _code("ali@gmail.com", "reset")
        assert reset_code
        assert client.post(
            "/api/auth/reset-password",
            json={"email": "ali@gmail.com", "otp": "999999", "new_password": "secret2"},
        ).status_code == 400
        assert client.post(
            "/api/auth/reset-password",
            json={"email": "ali@gmail.com", "otp": reset_code, "new_password": "secret2"},
        ).status_code == 200
        assert client.post("/api/auth/login", json={"email": "ali@gmail.com", "password": "Secret1!"}).status_code == 401
        assert client.post("/api/auth/login", json={"email": "ali@gmail.com", "password": "secret2"}).status_code == 200

    # Rows really landed on disk
    conn = sqlite3.connect(str(_db))
    kinds = {row[0] for row in conn.execute("SELECT DISTINCT kind FROM objects")}
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM otp_codes").fetchone()[0]
    conn.close()
    assert {"resume", "conversation"} <= kinds, kinds
    assert user_count == 2, user_count
    assert pending == 0, pending


if __name__ == "__main__":
    try:
        _run()
        print("OK: auth (OTP) + reset + persistence + history")
    finally:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(str(_db) + suffix)
            except OSError:
                pass
