"""Abstract base class for job source connectors."""

from __future__ import annotations

import abc
import asyncio
import logging
import time
from dataclasses import dataclass, field

from backend.core.schemas import Job

logger = logging.getLogger(__name__)


@dataclass
class SourceConfig:
    """Configuration for a job source connector."""

    name: str
    enabled: bool = True
    priority: int = 0
    rate_limit: float = 0.0
    timeout_seconds: float = 30.0
    max_retries: int = 3
    max_concurrency: int = 5


class SourceError(Exception):
    """Raised when a job source fails."""

    def __init__(self, source_name: str, message: str, cause: Exception | None = None):
        self.source_name = source_name
        self.cause = cause
        super().__init__(f"[{source_name}] {message}")


class AbstractJobSource(abc.ABC):
    """Base class all job source connectors must implement.

    Provides retry logic with exponential backoff, timeout handling,
    per-source failure isolation, and configurable rate limiting.
    """

    def __init__(self, config: SourceConfig | None = None):
        self.config = config or SourceConfig(name=self.__class__.__name__)
        self._last_request_time: float = 0.0
        self._failure_count: int = 0
        self._consecutive_failures: int = 0

    # ── Public API ─────────────────────────────────────────────────────────

    async def fetch(self, query: str, limit: int = 25) -> list[Job]:
        """Fetch jobs with retry, timeout, and rate-limit handling.

        Delegates to `_fetch_raw` for the actual HTTP call, then runs
        the source-specific normaliser.
        """
        if not self.config.enabled:
            logger.info("%s is disabled — skipping", self.config.name)
            return []

        last_exc: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                await self._apply_rate_limit()
                result = await asyncio.wait_for(
                    self._fetch_raw(query, limit),
                    timeout=self.config.timeout_seconds,
                )
                self._consecutive_failures = 0
                return result
            except asyncio.TimeoutError:
                last_exc = TimeoutError(f"timed out after {self.config.timeout_seconds}s")
                logger.warning(
                    "%s attempt %d/%d timed out",
                    self.config.name,
                    attempt,
                    self.config.max_retries,
                )
            except Exception as exc:
                last_exc = exc
                self._consecutive_failures += 1
                logger.warning(
                    "%s attempt %d/%d failed: %s",
                    self.config.name,
                    attempt,
                    self.config.max_retries,
                    exc,
                )
            # exponential backoff: 0.5, 1.0, 2.0, …
            delay = min(0.5 * (2 ** (attempt - 1)), 10.0)
            await asyncio.sleep(delay)

        self._failure_count += 1
        raise SourceError(
            self.config.name,
            f"failed after {self.config.max_retries} attempts",
            cause=last_exc,
        )

    async def health_check(self) -> bool:
        """Return True if the source responds to a lightweight probe."""
        try:
            await self.fetch("test", limit=1)
            return True
        except Exception:
            return False

    # ── Subclass hooks ─────────────────────────────────────────────────────

    @abc.abstractmethod
    async def _fetch_raw(self, query: str, limit: int) -> list[Job]:
        """Perform the actual HTTP call and return normalised Job objects."""
        ...

    # ── Internals ──────────────────────────────────────────────────────────

    async def _apply_rate_limit(self) -> None:
        """Sleep if necessary to respect the per-second rate limit."""
        if self.config.rate_limit <= 0:
            return
        min_interval = 1.0 / self.config.rate_limit
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_request_time = time.monotonic()
