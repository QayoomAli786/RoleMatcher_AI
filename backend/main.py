"""RoleMatcherAi
 — FastAPI application entry point."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api.router import api_router
from backend.core.config import get_settings
from backend.observability.tracing import TracingMiddleware
from backend.security.rate_limit import RateLimitMiddleware
from backend.services.llm_service import (
    reset_request_api_key,
    reset_request_model,
    set_request_api_key,
    set_request_model,
)

logger = logging.getLogger(__name__)
settings = get_settings()


def _configure_litellm_keys() -> None:
    """Map our CC_-prefixed env vars to the litellm-expected env vars."""
    env_map = {
        "CC_GEMINI_API_KEY": "GEMINI_API_KEY",
        "CC_GROQ_API_KEY": "GROQ_API_KEY",
        "CC_OPENAI_API_KEY": "OPENAI_API_KEY",
        "CC_DEEPSEEK_API_KEY": "DEEPSEEK_API_KEY",
        "CC_QWEN_API_KEY": "QWEN_API_KEY",
    }
    for cc_key, litellm_key in env_map.items():
        val = getattr(settings, cc_key.lower(), "") or ""
        if val:
            os.environ.setdefault(litellm_key, val)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    _configure_litellm_keys()
    logger.info("Starting %s v%s (in-memory mode)", settings.app_name, settings.app_version)
    yield
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="LangGraph-powered career intelligence platform.",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    origins = [
        "https://career-copilot-ai-five.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:3000",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Custom middleware ─────────────────────────────────────────────────
    # Order matters: Starlette executes middleware in reverse order of addition.
    # RateLimitMiddleware wraps the app first, then TracingMiddleware wraps that,
    # so every request gets traced even if rate-limited.
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(TracingMiddleware)

    # ── Per-request API key + model from headers ──────────────────────────
    @app.middleware("http")
    async def _request_context_middleware(request: Request, call_next):
        api_key = request.headers.get("x-api-key", "").strip()
        model = request.headers.get("x-model", "").strip()
        key_token = set_request_api_key(api_key) if api_key else None
        model_token = set_request_model(model) if model else None
        try:
            return await call_next(request)
        finally:
            if key_token is not None:
                reset_request_api_key(key_token)
            if model_token is not None:
                reset_request_model(model_token)

    # ── Routes ────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ── Backward-compatible legacy endpoints ──────────────────────────────
    @app.post("/api/upload-resume", tags=["Legacy"])
    async def _legacy_upload_resume():
        return JSONResponse(
            status_code=301,
            content={"detail": "Use POST /api/resumes instead."},
            headers={"Location": "/api/resumes"},
        )

    @app.post("/api/run-crew", tags=["Legacy"])
    async def _legacy_run_crew():
        return JSONResponse(
            status_code=301,
            content={"detail": "Use POST /api/jobs/search instead."},
            headers={"Location": "/api/jobs/search"},
        )

    @app.delete("/api/session", tags=["Legacy"])
    async def _legacy_clear_session():
        return JSONResponse(
            status_code=301,
            content={"detail": "Use DELETE /api/resumes/{id} instead."},
        )

    # ── Global exception handler ─────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.exception("Unhandled exception [request_id=%s]", request_id)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": request_id,
            },
        )

    # ── Catch-all: serve frontend files & SPA fallback ─────────────────
    from fastapi.responses import FileResponse
    _frontend_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
    # Always revalidate — otherwise the browser keeps serving stale JS/CSS
    _NO_CACHE = {"Cache-Control": "no-cache, must-revalidate", "Pragma": "no-cache"}

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        # Serve actual frontend files (CSS, JS, images, etc.)
        if full_path:
            file_path = os.path.realpath(os.path.join(_frontend_dir, full_path))
            if file_path.startswith(_frontend_dir + os.sep) and os.path.isfile(file_path):
                return FileResponse(file_path, headers=_NO_CACHE)
        # Fallback to index.html for SPA client-side routing
        index = os.path.join(_frontend_dir, "index.html")
        if os.path.isfile(index):
            return FileResponse(index, headers=_NO_CACHE)
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
