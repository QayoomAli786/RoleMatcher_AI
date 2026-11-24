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
import smtplib
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import Header, HTTPException, status

from backend.core import db
from backend.core.config import get_settings
from backend.core.schemas import UserProfile

_PBKDF2_ITERATIONS = 200_000
_OTP_TTL_MINUTES = 10
_SIGNUP = "signup"
_RESET = "reset"

logger = logging.getLogger(__name__)
settings = get_settings()


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


def _send_email_smtp(to_email: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """Send email via SMTP. Returns True on success, False on failure."""
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        logger.warning("SMTP not configured — email not sent")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email or settings.smtp_user}>"
        msg["To"] = to_email

        part_text = MIMEText(body_text, "plain", "utf-8")
        msg.attach(part_text)

        if body_html:
            part_html = MIMEText(body_html, "html", "utf-8")
            msg.attach(part_html)

        context = ssl.create_default_context()

        # Port 465 = implicit TLS (SSL), Port 587 = explicit TLS (STARTTLS)
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context) as server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                if settings.smtp_use_tls:
                    server.starttls(context=context)
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)

        logger.info("Email sent successfully to %s", to_email)
        return True

    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return False


def _deliver_code(email: str, purpose: str, code: str) -> None:
    """Send the verification code via SMTP. Falls back to terminal print if SMTP not configured."""
    label = "Sign up verification" if purpose == _SIGNUP else "Password reset"
    subject = f"RoleMatcherAI — {label} code"
    body_text = (
        f"Your {label.lower()} code is:\n\n"
        f"    {code}\n\n"
        f"This code is valid for {_OTP_TTL_MINUTES} minutes.\n\n"
        f"If you didn't request this, please ignore this email.\n"
        f"— RoleMatcherAI"
    )
    # Pre-header text for email clients
    preheader = f"Your {label.lower()} code: {code} — valid for {_OTP_TTL_MINUTES} minutes"
    
    body_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>{subject}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap');
    {{ 
      body {{ margin:0; padding:0; background:#f8fafc; }}
      .wrapper {{ min-height:100vh; padding:40px 20px; }}
      .card {{ background:#ffffff; border-radius:16px; box-shadow:0 4px 24px rgba(15,23,42,0.08); overflow:hidden; max-width:480px; margin:0 auto; }}
      .header {{ background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%); padding:32px; text-align:center; position:relative; }}
      .header::after {{ content:''; position:absolute; bottom:0; left:0; right:0; height:4px; background:linear-gradient(90deg,#22c55e,#16a34a); }}
      .logo {{ font-family:'Outfit',sans-serif; font-weight:700; font-size:24px; color:#fff; letter-spacing:-0.5px; }}
      .logo span {{ color:#22c55e; }}
      .content {{ padding:40px 32px; text-align:center; }}
      .greeting {{ font-family:'Inter',sans-serif; font-size:16px; color:#64748b; margin:0 0 8px; }}
      .title {{ font-family:'Outfit',sans-serif; font-weight:700; font-size:24px; color:#0f172a; margin:0 0 16px; letter-spacing:-0.5px; }}
      .code-box {{ background:linear-gradient(135deg,#f0fdf4 0%,#dcfce7 100%); border:2px solid #bbf7d0; border-radius:12px; padding:24px; margin:24px 0; position:relative; overflow:hidden; }}
      .code-box::before {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg,#22c55e,#16a34a); }}
      .code-label {{ font-family:'Inter',sans-serif; font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:1.5px; color:#166534; margin-bottom:8px; }}
      .code {{ font-family:'JetBrains Mono','Fira Code',monospace; font-size:36px; font-weight:700; letter-spacing:8px; color:#166534; word-break:break-all; }}
      .meta {{ font-family:'Inter',sans-serif; font-size:14px; color:#64748b; margin:24px 0 0; line-height:1.6; }}
      .meta strong {{ color:#334155; }}
      .divider {{ border:none; border-top:1px solid #e2e8f0; margin:32px 0; }}
      .footer {{ font-family:'Inter',sans-serif; font-size:12px; color:#94a3b8; text-align:center; padding:0 32px 32px; line-height:1.6; }}
      .footer a {{ color:#22c55e; text-decoration:none; }}
      .security-note {{ background:#fef3c7; border:1px solid #fde68a; border-radius:8px; padding:12px 16px; margin:16px 0; font-size:13px; color:#92400e; }}
      @media (max-width:480px) {{
        .card {{ border-radius:12px; }}
        .content {{ padding:32px 24px; }}
        .code {{ font-size:28px; letter-spacing:4px; }}
        .title {{ font-size:20px; }}
      }}
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="card">
      <div class="header">
        <div class="logo">RoleMatcher<span>AI</span></div>
      </div>
      <div class="content">
        <p class="greeting">Hi there,</p>
        <h1 class="title">Your {label.lower()} code</h1>
        
        <div class="code-box">
          <p class="code-label">Verification Code</p>
          <p class="code">{code}</p>
        </div>
        
        <p class="meta">This code is valid for <strong>{_OTP_TTL_MINUTES} minutes</strong>.</p>
        
        <div class="security-note">
          <strong>🔒 Security tip:</strong> Never share this code with anyone. RoleMatcherAI will never ask for it via phone, email, or chat.
        </div>
        
        <hr class="divider">
        
        <p class="footer">
          If you didn't request this, please ignore this email or 
          <a href="mailto:support@rolematcher.ai">contact support</a>.<br>
          — The RoleMatcherAI Team
        </p>
      </div>
    </div>
  </div>
</body>
</html>"""

    sent = _send_email_smtp(email, subject, body_text, body_html)

    # Always log to terminal as fallback/backup
    line = "=" * 56
    print(
        f"\n{line}\n  RoleMatcherAI {label} code for {email}\n\n      {code}\n\n"
        f"  (valid for {_OTP_TTL_MINUTES} minutes)\n  SMTP sent: {sent}\n{line}\n",
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
