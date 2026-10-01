"""In-memory and Redis-backed rate limiting with FastAPI integration."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Callable

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── In-memory sliding-window store ───────────────────────────────────────────


class InMemoryRateLimiter:
    """Per-key sliding window counter.  Good enough for single-process dev."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        hits = self._hits[key]
        self._hits[key] = [t for t in hits if t > cutoff]
        if len(self._hits[key]) >= self.max_requests:
            return False
        self._hits[key].append(now)
        return True

    def remaining(self, key: str) -> int:
        now = time.time()
        cutoff = now - self.window
        hits = [t for t in self._hits[key] if t > cutoff]
        return max(0, self.max_requests - len(hits))

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


# ── Redis-backed limiter ─────────────────────────────────────────────────────


class RedisRateLimiter:
    """Sliding window via Redis sorted sets with automatic fallback."""

    def __init__(self, redis_url: str, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._client: Any = None
        self._available = False
        try:
            import redis as _redis

            self._client = _redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._client.ping()
            self._available = True
        except Exception:
            logger.warning("Redis unavailable – falling back to in-memory rate limiter")

    def is_allowed(self, key: str) -> bool:
        if not self._available:
            return False  # caller should fall back
        now = time.time()
        pipe = self._client.pipeline()  # type: ignore[union-attr]
        pipe.zremrangebyscore(key, 0, now - self.window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, self.window)
        results = pipe.execute()
        return results[2] <= self.max_requests

    def remaining(self, key: str) -> int:
        if not self._available:
            return self.max_requests
        now = time.time()
        count = self._client.zcount(key, now - self.window, now)  # type: ignore[union-attr]
        return max(0, self.max_requests - count)

    def reset(self, key: str) -> None:
        if self._available:
            self._client.delete(key)  # type: ignore[union-attr]


# ── Unified limiter ──────────────────────────────────────────────────────────


class RateLimiter:
    """Tries Redis first; falls back to in-memory when Redis is unavailable."""

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int | None = None,
        redis_url: str = "",
    ) -> None:
        self.max_requests = max_requests or settings.rate_limit_requests
        self.window = window_seconds or settings.rate_limit_window_seconds

        self._mem = InMemoryRateLimiter(self.max_requests, self.window)
        self._redis = RedisRateLimiter(redis_url, self.max_requests, self.window) if redis_url else None

    def _make_key(self, request: Request, user_id: str | None = None) -> str:
        ip = request.client.host if request.client else "unknown"
        if user_id:
            return f"rl:{user_id}:{request.url.path}"
        return f"rl:{ip}:{request.url.path}"

    def check(self, request: Request, user_id: str | None = None) -> None:
        key = self._make_key(request, user_id)
        allowed = False
        if self._redis and self._redis._available:
            allowed = self._redis.is_allowed(key)
            remaining = self._redis.remaining(key)
        else:
            allowed = self._mem.is_allowed(key)
            remaining = self._mem.remaining(key)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {self.window}s.",
                headers={"X-RateLimit-Limit": str(self.max_requests), "X-RateLimit-Remaining": "0"},
            )

    def reset(self, request: Request, user_id: str | None = None) -> None:
        key = self._make_key(request, user_id)
        self._mem.reset(key)
        if self._redis:
            self._redis.reset(key)


# ── Global instance ──────────────────────────────────────────────────────────

rate_limiter = RateLimiter(redis_url=settings.redis_url)


# ── FastAPI middleware ────────────────────────────────────────────────────────


async def rate_limit_middleware(request: Request, call_next: Any) -> Response:
    """ASGI middleware that applies rate limiting to every request."""
    if request.url.path in ("/api/health", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)

    rate_limiter.check(request)
    response = await call_next(request)
    key = rate_limiter._make_key(request)
    remaining = rate_limiter._mem.remaining(key)
    response.headers["X-RateLimit-Limit"] = str(rate_limiter.max_requests)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Class-based middleware wrapper for use with app.add_middleware()."""

    SKIP_PATHS = frozenset({"/api/health", "/docs", "/openapi.json", "/redoc"})

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        rate_limiter.check(request)
        response = await call_next(request)
        key = rate_limiter._make_key(request)
        remaining = rate_limiter._mem.remaining(key)
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


# ── Per-endpoint decorator ───────────────────────────────────────────────────


def rate_limit(max_requests: int | None = None, window_seconds: int | None = None) -> Callable:
    """Decorator that applies tighter limits on specific route functions."""

    def decorator(func: Callable) -> Callable:
        limiter = RateLimiter(
            max_requests=max_requests or settings.rate_limit_requests,
            window_seconds=window_seconds or settings.rate_limit_window_seconds,
        )

        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            limiter.check(request)
            return await func(request, *args, **kwargs)

        wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        return wrapper

    return decorator
