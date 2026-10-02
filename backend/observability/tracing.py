"""Request tracing, structured logging, and LLM call logging."""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.observability.metrics import metrics

# Paths excluded from request metrics (health checks, docs).
SKIP_PATHS = frozenset({"/api/health", "/docs", "/openapi.json", "/redoc"})

# ── Context variables ────────────────────────────────────────────────────────

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# ── Structured logger ────────────────────────────────────────────────────────

logger = logging.getLogger("careercopilot.observability")

_SENSITIVE_KEYS = frozenset({
    "password", "hashed_password", "token", "secret",
    "api_key", "authorization", "resume_text", "raw_text",
})


def _redact(obj: Any) -> Any:
    """Recursively redact sensitive values from dicts/lists."""
    if isinstance(obj, dict):
        return {
            k: "***" if k.lower() in _SENSITIVE_KEYS else _redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(i) for i in obj]
    return obj


def log_event(event: str, **kwargs: Any) -> None:
    """Emit a structured log line, redacting sensitive data."""
    payload = {"event": event, "request_id": request_id_var.get(""), **_redact(kwargs)}
    logger.info("%s", payload)


def log_llm_call(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    cost_usd: float = 0.0,
) -> None:
    """Log a completed LLM invocation and record it in the metrics store."""
    metrics.inc("total_llm_calls")
    metrics.inc("total_tokens", prompt_tokens + completion_tokens)
    metrics.inc("total_cost_usd", cost_usd)
    metrics.observe("llm_latency_ms", latency_ms)

    logger.info(
        "llm_call",
        extra={
            "event": "llm_call",
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": round(latency_ms, 2),
            "cost_usd": round(cost_usd, 6),
            "request_id": request_id_var.get(""),
        },
    )


# ── ASGI middleware ──────────────────────────────────────────────────────────


class TracingMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID and timing to every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = str(uuid.uuid4())
        request_id_var.set(rid)
        request.state.request_id = rid

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = rid
        response.headers["X-Response-Time-Ms"] = str(round(elapsed_ms, 2))

        if request.url.path not in SKIP_PATHS:
            metrics.inc("total_requests")
            metrics.observe("request_latency_ms", elapsed_ms)

            log_event(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                latency_ms=round(elapsed_ms, 2),
                client=request.client.host if request.client else "unknown",
            )

        return response
