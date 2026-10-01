"""Remotive API job source connector."""

from __future__ import annotations

import logging

import httpx

from backend.core.schemas import Job
from backend.services.job_normalizer import normalize_remotive_job
from backend.services.job_sources.base import AbstractJobSource, SourceConfig

logger = logging.getLogger(__name__)

REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSource(AbstractJobSource):
    """Fetch remote jobs from the Remotive public API."""

    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                name="remotive",
                enabled=True,
                priority=10,
                rate_limit=2.0,
                timeout_seconds=15.0,
            )
        )

    async def _fetch_raw(self, query: str, limit: int) -> list[Job]:
        params: dict[str, str | int] = {"limit": min(limit, 100)}
        if query:
            params["search"] = query

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                REMOTIVE_API_URL,
                params=params,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()

        data = resp.json()
        jobs_raw: list[dict] = data.get("jobs", [])

        jobs: list[Job] = []
        for raw in jobs_raw[:limit]:
            try:
                jobs.append(normalize_remotive_job(raw))
            except Exception as exc:
                logger.debug("Skipping Remotive job: %s", exc)

        logger.info("Remotive: fetched %d jobs for query=%r", len(jobs), query)
        return jobs
