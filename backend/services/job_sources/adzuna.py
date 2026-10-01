"""Adzuna API job source connector.

Free tier: 1,000 calls/month with self-serve app_id and app_key.
Strongest in UK and EU markets; aggregated job ads across 16 countries.

Requires environment variables:
    ADZUNA_APP_ID - Your Adzuna app_id (get from https://developer.adzuna.com)
    ADZUNA_APP_KEY - Your Adzuna app_key
"""

from __future__ import annotations

import logging
import os

import httpx

from backend.core.schemas import Job
from backend.services.job_normalizer import normalize_generic_job
from backend.services.job_sources.base import AbstractJobSource, SourceConfig

logger = logging.getLogger(__name__)

ADZUNA_API_URL = "https://api.adzuna.com/v1/api/jobs"


class AdzunaSource(AbstractJobSource):
    """Fetch jobs from the Adzuna public API.

    Requires ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables.
    If not configured, the source is automatically disabled.
    """

    def __init__(self) -> None:
        app_id = os.getenv("ADZUNA_APP_ID", "")
        app_key = os.getenv("ADZUNA_APP_KEY", "")
        enabled = bool(app_id and app_key)

        if not enabled:
            logger.info(
                "Adzuna source disabled — set ADZUNA_APP_ID and ADZUNA_APP_KEY to enable"
            )

        super().__init__(
            SourceConfig(
                name="adzuna",
                enabled=enabled,
                priority=4,
                rate_limit=0.5,
                timeout_seconds=20.0,
            )
        )
        self._app_id = app_id
        self._app_key = app_key

    async def _fetch_raw(self, query: str, limit: int) -> list[Job]:
        if not self._app_id or not self._app_key:
            return []

        # Search US market by default; can be extended to other countries
        country = "us"
        url = f"{ADZUNA_API_URL}/{country}/search/1"
        params = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "results_per_page": min(limit, 50),
            "what": query,
            "sort_by": "date",
            "content-type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()

        data = resp.json()
        results = data.get("results", [])

        jobs: list[Job] = []
        for raw in results[:limit]:
            try:
                job = self._normalize_adzuna_job(raw)
                jobs.append(job)
            except Exception as exc:
                logger.debug("Skipping Adzuna job: %s", exc)

        logger.info("Adzuna: fetched %d jobs for query=%r", len(jobs), query)
        return jobs

    @staticmethod
    def _normalize_adzuna_job(raw: dict) -> Job:
        """Normalize an Adzuna API job listing."""
        title = raw.get("title", "")
        company = raw.get("company", {}).get("display_name", "")
        location = raw.get("location", {}).get("display_name", "")
        desc = raw.get("description", "")
        url = raw.get("redirect_url", "")

        # Adzuna provides salary data
        salary_min = raw.get("salary_min")
        salary_max = raw.get("salary_max")
        if salary_min:
            salary_min = int(float(salary_min))
        if salary_max:
            salary_max = int(float(salary_max))

        # Determine if remote
        location_lower = location.lower()
        is_remote = "remote" in location_lower or "anywhere" in location_lower

        # Extract skills from description
        from backend.services.job_normalizer import _extract_skills_from_text
        skills = _extract_skills_from_text(desc)

        posted = None
        if raw.get("created"):
            try:
                from datetime import datetime
                posted = datetime.fromisoformat(raw["created"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return Job(
            source="adzuna",
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
