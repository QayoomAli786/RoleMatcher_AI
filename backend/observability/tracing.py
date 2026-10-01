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

# ── Context variables ────────────────────────────────────────────────────────

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")

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
    """Log a completed LLM invocation."""
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
            "user_id": user_id_var.get(""),
        },
    )


def log_graph_execution(graph_name: str, latency_ms: float, state_keys: list[str]) -> None:
    """Log completion of a LangGraph graph execution."""
    metrics.inc(f"graph_{graph_name}_executions")
    metrics.observe(f"graph_{graph_name}_latency_ms", latency_ms)

    logger.info(
        "graph_execution",
        extra={
            "event": "graph_execution",
            "graph": graph_name,
            "latency_ms": round(latency_ms, 2),
            "state_keys": state_keys,
            "request_id": request_id_var.get(""),
            "user_id": user_id_var.get(""),
        },
    )


# ── ASGI middleware ──────────────────────────────────────────────────────────


class TracingMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID and timing to every request."""

    SKIP_PATHS = frozenset({"/api/health", "/docs", "/openapi.json", "/redoc"})

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = str(uuid.uuid4())
        request_id_var.set(rid)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = rid
        response.headers["X-Response-Time-Ms"] = str(round(elapsed_ms, 2))

        if request.url.path not in self.SKIP_PATHS:
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


# ── Function-level tracing decorator ─────────────────────────────────────────


def trace_function(name: str | None = None):
    """Decorator that logs start/end and timing for any async function."""

    def decorator(func):
        func_name = name or f"{func.__module__}.{func.__qualname__}"

        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                log_event("function_end", function=func_name, latency_ms=round(elapsed, 2), success=True)
                return result
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000
                log_event("function_end", function=func_name, latency_ms=round(elapsed, 2), success=False, error=str(exc))
                raise

        wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        return wrapper

    return decorator
