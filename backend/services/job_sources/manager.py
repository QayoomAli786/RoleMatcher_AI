"""Job source manager — parallel collection with failure isolation."""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from backend.core.schemas import Job
from backend.services.job_deduplicator import deduplicate as deduplicate_jobs
from backend.services.job_sources.base import AbstractJobSource, SourceConfig, SourceError
from backend.services.job_sources.adzuna import AdzunaSource
from backend.services.job_sources.generic_scraper import GenericScraperSource
from backend.services.job_sources.linkedin import LinkedInSource
from backend.services.job_sources.remoteok import RemoteOKSource

logger = logging.getLogger(__name__)


class JobSourceManager:
    """Register, query, and merge results from multiple job sources.

    Runs sources concurrently via ``asyncio.gather`` with
    ``return_exceptions=True`` so one failure never blocks the rest.
    """

    def __init__(self) -> None:
        self._sources: dict[str, AbstractJobSource] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    # ── Registration ────────────────────────────────────────────────────────

    def register(self, source: AbstractJobSource) -> None:
        name = source.config.name
        self._sources[name] = source
        self._semaphores[name] = asyncio.Semaphore(source.config.max_concurrency)
        logger.info("Registered source: %s (priority=%d)", name, source.config.priority)

    def register_default_sources(self) -> None:
        """Register all built-in sources: LinkedIn (broadest), RemoteOK (free), Adzuna (UK/EU)."""
        self.register(LinkedInSource())
        self.register(RemoteOKSource())
        self.register(AdzunaSource())

    def add_custom_scraper(self, url: str) -> None:
        source = GenericScraperSource(target_url=url)
        self.register(source)

    # ── Collection ─────────────────────────────────────────────────────────

    async def collect_jobs(
        self,
        query: str,
        sources: Sequence[str] | None = None,
        limit: int = 50,
    ) -> list[Job]:
        """Query the requested sources in parallel and merge deduplicated results.

        Parameters
        ----------
        query : str
            Search keywords.
        sources : Sequence[str] | None
            Source names to query. ``None`` = all registered sources.
        limit : int
            Max jobs *per source*.
        """
        requested = sources or list(self._sources.keys())

        # Filter to enabled + registered, sort by priority descending
        active = sorted(
            [s for name, s in self._sources.items() if name in requested and s.config.enabled],
            key=lambda s: s.config.priority,
            reverse=True,
        )

        if not active:
            logger.warning("No active sources matched for query=%r", query)
            return []

        logger.info(
            "Collecting jobs from %d source(s): %s",
            len(active),
            [s.config.name for s in active],
        )

        tasks = [
            self._guarded_fetch(source, query, limit) for source in active
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_jobs: list[Job] = []
        succeeded = 0
        for source, result in zip(active, results):
            if isinstance(result, Exception):
                logger.error(
                    "Source %s failed: %s", source.config.name, result
                )
            elif isinstance(result, list):
                succeeded += 1
                all_jobs.extend(result)

        logger.info(
            "Collection complete: %d jobs from %d/%d sources",
            len(all_jobs),
            succeeded,
            len(active),
        )

        deduped = deduplicate_jobs(all_jobs)
        logger.info("After deduplication: %d jobs", len(deduped))
        return deduped

    async def _guarded_fetch(
        self, source: AbstractJobSource, query: str, limit: int
    ) -> list[Job]:
        sem = self._semaphores[source.config.name]
        async with sem:
            return await source.fetch(query, limit)

    # ── Health ─────────────────────────────────────────────────────────────

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of every registered source concurrently."""
        tasks = {
            name: source.health_check() for name, source in self._sources.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        return {
            name: (result is True)
            for name, result in zip(tasks.keys(), results)
        }

    # ── Introspection ──────────────────────────────────────────────────────

    @property
    def source_names(self) -> list[str]:
        return list(self._sources.keys())

    def get_source(self, name: str) -> AbstractJobSource | None:
        return self._sources.get(name)
