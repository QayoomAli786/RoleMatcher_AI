"""Auth endpoints — sign up, sign in, sign out, current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from backend.core.schemas import UserProfile
from backend.security import auth as auth_service
from backend.security.auth import get_current_user

router = APIRouter(prefix="/auth")


class _SignupBody(BaseModel):
    email: str
    password: str
    name: str = ""


class _LoginBody(BaseModel):
    email: str
    password: str


class _VerifyBody(BaseModel):
    email: str
    otp: str


class _ResendBody(BaseModel):
    email: str
    purpose: str = "signup"


class _ForgotBody(BaseModel):
    email: str


class _ResetBody(BaseModel):
    email: str
    otp: str
    new_password: str


def _public(user: UserProfile) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "created_at": user.created_at.isoformat(),
    }


@router.post("/signup")
async def signup(body: _SignupBody):
    """Start sign up — sends a verification code (printed in the terminal)."""
    try:
        email = auth_service.start_signup(body.email, body.password, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"otp_required": True, "email": email}


@router.post("/verify-otp")
async def verify_otp(body: _VerifyBody):
    """Finish sign up — check the code and create the account."""
    try:
        user = auth_service.verify_signup(body.email, body.otp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"token": auth_service.create_token(user.id), "user": _public(user)}


@router.post("/resend-otp")
async def resend_otp(body: _ResendBody):
    """Re-issue the sign up or password reset code."""
    try:
        auth_service.resend_code(body.email, body.purpose)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/forgot-password")
async def forgot_password(body: _ForgotBody):
    """Send a password reset code (no-op when the email is unknown)."""
    auth_service.start_password_reset(body.email)
    return {"ok": True}


@router.post("/reset-password")
async def reset_password(body: _ResetBody):
    """Set a new password using a reset code."""
    try:
        auth_service.reset_password(body.email, body.otp, body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/login")
async def login(body: _LoginBody):
    user = auth_service.authenticate(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return {"token": auth_service.create_token(user.id), "user": _public(user)}


@router.post("/logout")
async def logout(authorization: str = Header(default="")):
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if token:
        auth_service.revoke_token(token)
    return {"ok": True}


@router.get("/me")
async def me(user: UserProfile = Depends(get_current_user)):
    return _public(user)
