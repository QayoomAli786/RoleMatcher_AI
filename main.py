"""Vercel / ASGI entrypoint for RoleMatcher AI.

Vercel's Python runtime looks for a top-level ``app`` object in a supported
entrypoint such as ``main.py`` at the repository root. The real FastAPI
application lives in ``backend/main.py``; re-exporting it here keeps local
development (``uvicorn main:app``) and Vercel deployments identical.

The FastAPI app also owns the frontend catch-all route, so a single Vercel
Function serves both the UI and the ``/api/*`` backend.
"""

from backend.main import app

__all__ = ["app"]
