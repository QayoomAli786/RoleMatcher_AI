"""Multi-layer caching: in-memory LRU, Redis, PostgreSQL (async)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import pickle
import time
from collections import OrderedDict
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── L1: In-Memory LRU ────────────────────────────────────────────────────────


class LRUCache:
    """Thread-safe-ish in-memory LRU cache with TTL support."""

    def __init__(self, max_size: int = 2048, default_ttl: int = 600) -> None:
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (time.time() + (ttl or self._default_ttl), value)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


# ── L2: Redis Cache ───────────────────────────────────────────────────────────


class RedisCache:
    """Redis-backed cache with graceful fallback."""

    def __init__(self, redis_url: str, default_ttl: int = 3600) -> None:
        self._redis_url = redis_url
        self._default_ttl = default_ttl
        self._client = None
        self._available = False
        self._connect()

    def _connect(self) -> None:
        try:
            import redis as _redis_mod  # type: ignore[import-untyped]

            self._client = _redis_mod.from_url(
                self._redis_url,
                decode_responses=False,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._client.ping()
            self._available = True
        except Exception:
            logger.warning("Redis unavailable – L2 cache disabled")
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def get(self, key: str) -> Any | None:
        if not self._available:
            return None
        try:
            raw = self._client.get(key)  # type: ignore[union-attr]
            if raw is None:
                return None
            return pickle.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if not self._available:
            return
        try:
            self._client.setex(  # type: ignore[union-attr]
                key, ttl or self._default_ttl, pickle.dumps(value)
            )
        except Exception:
            pass

    def delete(self, key: str) -> None:
        if not self._available:
            return
        try:
            self._client.delete(key)  # type: ignore[union-attr]
        except Exception:
            pass

    def clear(self) -> None:
        if not self._available:
            return
        try:
            self._client.flushdb()  # type: ignore[union-attr]
        except Exception:
            pass


# ── L3: PostgreSQL Cache (async via asyncpg) ──────────────────────────────────


class PostgresCache:
    """Persistent PostgreSQL cache using async driver (asyncpg).

    Connection pool is lazily initialised on first async call.
    """

    def __init__(self, dsn: str, default_ttl: int = 86400) -> None:
        self._dsn = dsn
        self._default_ttl = default_ttl
        self._available = False
        self._pool: Any = None

    async def _connect(self) -> None:
        """Lazy async connection pool initialization."""
        if self._pool is not None:
            return
        try:
            import asyncpg  # type: ignore[import-untyped]

            # Disable prepared statements for pgbouncer compatibility (Supabase pooler)
            is_pooler = "pooler.supabase.com" in self._dsn
            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=1,
                max_size=5,
                command_timeout=5,
                **({"statement_cache_size": 0} if is_pooler else {}),
            )
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cache_store (
                        key TEXT PRIMARY KEY,
                        value BYTEA NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            self._available = True
        except Exception:
            logger.warning("PostgreSQL unavailable – L3 cache disabled")
            self._available = False

    async def get(self, key: str) -> Any | None:
        if not self._available:
            await self._connect()
        if not self._available or self._pool is None:
            return None
        try:
            from datetime import datetime, timezone

            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT value, expires_at FROM cache_store WHERE key = $1",
                    key,
                )
                if row is None:
                    return None
                expires = row["expires_at"]
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires < datetime.now(timezone.utc):
                    await conn.execute("DELETE FROM cache_store WHERE key = $1", key)
                    return None
                return pickle.loads(row["value"])
        except Exception:
            self._available = False
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if not self._available:
            await self._connect()
        if not self._available or self._pool is None:
            return
        try:
            from datetime import datetime, timedelta, timezone

            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl or self._default_ttl)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO cache_store (key, value, expires_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at
                    """,
                    key,
                    pickle.dumps(value),
                    expires_at,
                )
        except Exception:
            self._available = False

    async def delete(self, key: str) -> None:
        if not self._available:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("DELETE FROM cache_store WHERE key = $1", key)
        except Exception:
            pass

    async def clear(self) -> None:
        if not self._available:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("DELETE FROM cache_store")
        except Exception:
            pass


# ── Unified Cache ──────────────────────────────────────────────────────────────


def content_hash(data: str | bytes) -> str:
    """SHA-256 hash for cache keys."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class MultiLayerCache:
    """Unified cache writing through L1 -> L2 -> L3 on set and reading from L1 -> L2 -> L3 on get.

    L1 (LRU) and L2 (Redis) are synchronous; L3 (Postgres) is async.
    Async methods are provided for use in async contexts.
    """

    def __init__(
        self,
        redis_url: str = "",
        postgres_dsn: str = "",
        l1_max: int = 2048,
        l1_ttl: int = 600,
        l2_ttl: int = 3600,
        l3_ttl: int = 86400,
    ) -> None:
        self.l1 = LRUCache(max_size=l1_max, default_ttl=l1_ttl)
        self.l2 = RedisCache(redis_url=redis_url, default_ttl=l2_ttl) if redis_url else None
        self.l3 = PostgresCache(dsn=postgres_dsn, default_ttl=l3_ttl) if postgres_dsn else None

    # ── Synchronous interface (L1 + L2 only) ──────────────────────────────

    def get(self, key: str) -> Any | None:
        val = self.l1.get(key)
        if val is not None:
            return val
        if self.l2 is not None:
            val = self.l2.get(key)
            if val is not None:
                self.l1.set(key, val)
                return val
        return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self.l1.set(key, value, ttl)
        if self.l2 is not None:
            self.l2.set(key, value, ttl)

    def delete(self, key: str) -> None:
        self.l1.delete(key)
        if self.l2 is not None:
            self.l2.delete(key)

    def invalidate(self, pattern: str) -> None:
        """Best-effort pattern invalidation (L1 only; L2/L3 require explicit keys)."""
        self.l1.clear()

    # ── Async interface (full L1 + L2 + L3) ───────────────────────────────

    async def aget(self, key: str) -> Any | None:
        """Async get that includes L3 (PostgreSQL)."""
        val = self.get(key)
        if val is not None:
            return val
        if self.l3 is not None:
            val = await self.l3.get(key)
            if val is not None:
                self.l1.set(key, val)
                return val
        return None

    async def aset(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Async set that includes L3 (PostgreSQL)."""
        self.set(key, value, ttl)
        if self.l3 is not None:
            await self.l3.set(key, value, ttl)

    async def adelete(self, key: str) -> None:
        """Async delete that includes L3 (PostgreSQL)."""
        self.delete(key)
        if self.l3 is not None:
            await self.l3.delete(key)

    # ── Decorator ─────────────────────────────────────────────────────────

    def cached(
        self, ttl: int | None = None, prefix: str = ""
    ) -> Callable:
        """Decorator that caches function results by arguments."""

        def decorator(func: Callable) -> Callable:
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                raw_key = f"{prefix}:{func.__module__}.{func.__qualname__}:{args}:{sorted(kwargs.items())}"
                key = content_hash(raw_key)
                result = self.get(key)
                if result is not None:
                    return result
                result = func(*args, **kwargs)
                self.set(key, result, ttl)
                return result

            wrapper.__wrapped__ = func  # type: ignore[attr-defined]
            return wrapper

        return decorator
