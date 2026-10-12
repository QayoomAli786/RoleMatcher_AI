"""Authentication — email + password accounts with SQLite-backed session tokens.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib only). Login issues an
opaque bearer token stored in the ``sessions`` table.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException, status

from backend.core import db
from backend.core.schemas import UserProfile

_PBKDF2_ITERATIONS = 200_000
_OTP_TTL_MINUTES = 10
_SIGNUP = "signup"
_RESET = "reset"

logger = logging.getLogger(__name__)


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)


def _row_to_profile(row: dict) -> UserProfile:
    try:
        preferences = json.loads(row.get("preferences") or "{}")
    except json.JSONDecodeError:
        preferences = {}
    return UserProfile(
        id=uuid.UUID(row["id"]),
        email=row["email"],
        name=row["name"],
        created_at=datetime.fromisoformat(row["created_at"]),
        preferences=preferences,
    )


def _valid_email(email: str) -> bool:
    """Sign up is Gmail-only: a single ``name@gmail.com`` address (lowercased first)."""
    if email.count("@") != 1:
        return False
    local, domain = email.split("@")
    return bool(local) and domain == "gmail.com"


def _strong_password(password: str) -> bool:
    """8+ characters mixing upper, lower, digit and a symbol."""
    return (
        len(password) >= 8
        and any(c.isupper() for c in password)
        and any(c.islower() for c in password)
        and any(c.isdigit() for c in password)
        and any(not c.isalnum() for c in password)
    )


def _deliver_code(email: str, purpose: str, code: str) -> None:
    """No email provider here — print the code so it shows up in the server terminal."""
    label = "Sign up verification" if purpose == _SIGNUP else "Password reset"
    line = "=" * 56
    print(
        f"\n{line}\n  RoleMatcherAi {label} code for {email}\n\n      {code}\n\n"
        f"  (valid for {_OTP_TTL_MINUTES} minutes)\n{line}\n",
        flush=True,
    )


def _store_code(email: str, purpose: str, payload: dict) -> None:
    # shortcut: codes are stored in plaintext — fine for a single-user local demo;
    # hash them (and add attempt limits) before this ever goes multi-tenant.
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = (datetime.now(timezone.utc) + timedelta(minutes=_OTP_TTL_MINUTES)).isoformat()
    db.upsert_otp(email, purpose, code, expires, json.dumps(payload))
    _deliver_code(email, purpose, code)


def _consume_code(email: str, purpose: str, code: str) -> dict:
    row = db.get_otp(email, purpose)
    if row is None:
        logger.info("No pending %s code for %s", purpose, email or "<empty>")
        raise ValueError("No pending code — start again or tap 'Resend code'")
    if not _same_code(row["code"], code):
        logger.info("Wrong %s code for %s", purpose, email)
        raise ValueError("Incorrect code — check the server terminal, or tap 'Resend code'")
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        db.delete_otp(email, purpose)
        logger.info("Expired %s code for %s", purpose, email)
        raise ValueError("This code has expired — tap 'Resend code' for a new one")
    db.delete_otp(email, purpose)
    try:
        return json.loads(row["payload"] or "{}")
    except json.JSONDecodeError:
        return {}


def _same_code(stored: str, entered: str) -> bool:
    entered = (entered or "").strip()
    if not entered:
        return False
    if entered == stored:
        return True
    # A user may drop a leading zero the terminal printed (e.g. 040613 → 40613).
    return entered.isdigit() and stored.isdigit() and int(entered) == int(stored)


def _insert_user(email: str, name: str, password_hash: str) -> UserProfile:
    user_id = uuid.uuid4()
    if not db.create_user_row(user_id, email, name, password_hash, db.now_iso()):
        raise ValueError("An account with this email already exists")
    return _row_to_profile(db.get_user_row(user_id))


def start_signup(email: str, password: str, name: str) -> str:
    """Validate the details and send a verification code. Returns the normalized email."""
    email = email.strip().lower()
    if not _valid_email(email):
        raise ValueError("Sign up requires a Gmail address (@gmail.com)")
    if not _strong_password(password):
        raise ValueError(
            "Password too weak — use 8+ characters with uppercase, lowercase, a number and a symbol"
        )
    if db.get_user_row_by_email(email) is not None:
        raise ValueError("An account with this email already exists")
    display_name = name.strip() or email.split("@")[0]
    _store_code(email, _SIGNUP, {"name": display_name, "password_hash": _hash_password(password)})
    return email


def verify_signup(email: str, code: str) -> UserProfile:
    """Consume a sign up code and create the account."""
    email = email.strip().lower()
    payload = _consume_code(email, _SIGNUP, code)
    return _insert_user(email, payload.get("name") or email.split("@")[0], payload["password_hash"])


def resend_code(email: str, purpose: str) -> None:
    email = email.strip().lower()
    row = db.get_otp(email, purpose)
    if row is None:
        raise ValueError("This request has expired — please start again")
    try:
        payload = json.loads(row["payload"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    _store_code(email, purpose, payload)


def start_password_reset(email: str) -> None:
    email = email.strip().lower()
    if db.get_user_row_by_email(email) is None:
        return  # never reveal whether the email is registered
    _store_code(email, _RESET, {})


def reset_password(email: str, code: str, new_password: str) -> None:
    if len(new_password) < 6:
        raise ValueError("Password must be at least 6 characters")
    email = email.strip().lower()
    _consume_code(email, _RESET, code)
    row = db.get_user_row_by_email(email)
    if row is None:
        raise ValueError("Account not found")
    db.update_user_password(row["id"], _hash_password(new_password))
    db.delete_sessions_for_user(row["id"])


def authenticate(email: str, password: str) -> UserProfile | None:
    row = db.get_user_row_by_email(email.strip().lower())
    if row is None or not _verify_password(password, row["password_hash"]):
        return None
    return _row_to_profile(row)


def create_token(user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    db.create_session(token, user_id, db.now_iso())
    return token


def revoke_token(token: str) -> None:
    db.delete_session(token)


def _bearer_token(authorization: str) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


async def get_current_user(authorization: str = Header(default="")) -> UserProfile:
    """FastAPI dependency — resolves the bearer token to the signed-in user."""
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = db.get_session_user_id(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    row = db.get_user_row(user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account no longer exists")
    return _row_to_profile(row)
