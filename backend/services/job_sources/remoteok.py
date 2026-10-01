"""RemoteOK API job source connector.

Free public feed at remoteok.com/api — no auth required.
Covers remote tech/design/marketing jobs worldwide.
"""

from __future__ import annotations

import logging

import httpx

from backend.core.schemas import Job
from backend.services.job_normalizer import normalize_generic_job
from backend.services.job_sources.base import AbstractJobSource, SourceConfig

logger = logging.getLogger(__name__)

REMOTEOK_API_URL = "https://remoteok.com/api"


class RemoteOKSource(AbstractJobSource):
    """Fetch remote jobs from the RemoteOK public API."""

    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                name="remoteok",
                enabled=True,
                priority=6,
                rate_limit=1.0,
                timeout_seconds=15.0,
            )
        )
        self._headers = {
            "Accept": "application/json",
            "User-Agent": "CareerCopilot/1.0 (https://careercopilot.ai)",
        }

    async def _fetch_raw(self, query: str, limit: int) -> list[Job]:
        async with httpx.AsyncClient(headers=self._headers, follow_redirects=True) as client:
            resp = await client.get(REMOTEOK_API_URL)
            resp.raise_for_status()

        data = resp.json()
        if not isinstance(data, list):
            logger.warning("RemoteOK returned non-list response")
            return []

        # First item is metadata, skip it
        jobs_raw = [item for item in data if isinstance(item, dict) and "position" in item]

        # Client-side filtering by query keywords
        if query:
            query_lower = query.lower()
            query_tokens = [t for t in query_lower.split() if len(t) > 1]
            jobs_raw = [
                j for j in jobs_raw
                if any(
                    token in (j.get("position", "") + " " + j.get("description", "")).lower()
                    for token in query_tokens
                )
            ]

        jobs: list[Job] = []
        for raw in jobs_raw[:limit]:
            try:
                job = self._normalize_remoteok_job(raw)
                jobs.append(job)
            except Exception as exc:
                logger.debug("Skipping RemoteOK job: %s", exc)

        logger.info("RemoteOK: fetched %d jobs for query=%r", len(jobs), query)
        return jobs

    @staticmethod
    def _normalize_remoteok_job(raw: dict) -> Job:
        """Normalize a RemoteOK API job listing."""
        title = raw.get("position", "")
        company = raw.get("company", "")
        tags = raw.get("tags", []) or []
        if isinstance(tags, list):
            skills = [t.lower().strip() for t in tags if isinstance(t, str)]
        else:
            skills = []

        location = raw.get("location", "") or "Remote"
        is_remote = "remote" in location.lower() or raw.get("remote", False)

        # Parse salary from description if available
        salary_min = None
        salary_max = None
        desc = raw.get("description", "")

        posted = None
        if raw.get("date"):
            try:
                from datetime import datetime
                posted = datetime.fromisoformat(raw["date"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        url = raw.get("url", "")
        if not url:
            job_id = raw.get("id", "")
            url = f"https://remoteok.com/remote-jobs/{job_id}" if job_id else ""

        return Job(
            source="remoteok",
            source_job_id=str(raw.get("id", "")),
            title=title,
            company=company,
            location=location,
            remote=is_remote,
            description=desc,
            skills=skills,
            salary_min=salary_min,
            salary_max=salary_max,
            currency="USD",
            employment_type="full-time",
            seniority="mid",
            posted_at=posted,
            source_url=url,
        )
