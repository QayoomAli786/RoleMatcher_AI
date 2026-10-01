"""Jobicy API job source connector."""

from __future__ import annotations

import logging

import httpx

from backend.core.schemas import Job
from backend.services.job_normalizer import normalize_jobicy_job
from backend.services.job_sources.base import AbstractJobSource, SourceConfig

logger = logging.getLogger(__name__)

JOBICY_API_URL = "https://jobicy.com/api/v2/remote-jobs"


class JobicySource(AbstractJobSource):
    """Fetch remote jobs from the Jobicy public API."""

    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                name="jobicy",
                enabled=True,
                priority=8,
                rate_limit=2.0,
                timeout_seconds=15.0,
            )
        )

    async def _fetch_raw(self, query: str, limit: int) -> list[Job]:
        params: dict[str, str | int] = {"count": min(limit, 50)}
        if query:
            params["tag"] = query

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                JOBICY_API_URL,
                params=params,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()

        data = resp.json()
        jobs_raw: list[dict] = data.get("jobs", [])

        jobs: list[Job] = []
        for raw in jobs_raw[:limit]:
            try:
                jobs.append(normalize_jobicy_job(raw))
            except Exception as exc:
                logger.debug("Skipping Jobicy job: %s", exc)

        logger.info("Jobicy: fetched %d jobs for query=%r", len(jobs), query)
        return jobs
