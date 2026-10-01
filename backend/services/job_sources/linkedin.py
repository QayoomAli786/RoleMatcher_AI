"""LinkedIn guest API job source connector (HTML scraping)."""

from __future__ import annotations

import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

from backend.core.schemas import Job
from backend.services.job_normalizer import normalize_linkedin_job
from backend.services.job_sources.base import AbstractJobSource, SourceConfig

logger = logging.getLogger(__name__)

LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


class LinkedInSource(AbstractJobSource):
    """Scrape LinkedIn guest job listings (no auth required).

    Uses the public guest API that returns HTML fragments. Parsing is
    best-effort — LinkedIn may change markup at any time.
    """

    def __init__(self) -> None:
        super().__init__(
            SourceConfig(
                name="linkedin",
                enabled=True,
                priority=5,
                rate_limit=0.5,
                timeout_seconds=20.0,
            )
        )
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def _fetch_raw(self, query: str, limit: int) -> list[Job]:
        all_jobs: list[Job] = []
        batch_size = 25
        start = 0

        async with httpx.AsyncClient(headers=self._headers, follow_redirects=True) as client:
            while start < limit:
                params = {
                    "keywords": query,
                    "start": start,
                    "sortBy": "DD",
                }
                try:
                    resp = await client.get(LINKEDIN_SEARCH_URL, params=params)
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        logger.warning("LinkedIn rate-limited at start=%d", start)
                        break
                    raise

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("li")

                if not cards:
                    break

                for card in cards:
                    parsed = self._parse_card(card)
                    if parsed:
                        try:
                            all_jobs.append(normalize_linkedin_job(parsed))
                        except Exception as exc:
                            logger.debug("Skipping LinkedIn job: %s", exc)

                start += batch_size

        return all_jobs[:limit]

    def _parse_card(self, card) -> dict | None:
        """Extract structured data from a single LinkedIn job card."""
        title_el = card.select_one("h3.base-search-card__title")
        company_el = card.select_one("h4.base-search-card__subtitle")
        link_el = card.select_one("a.base-card__full-link")
        location_el = card.select_one("span.job-search-card__location")

        if not title_el or not link_el:
            return None

        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True) if company_el else ""
        url = link_el.get("href", "").split("?")[0]
        location = location_el.get_text(strip=True) if location_el else ""

        return {
            "title": title,
            "company": company,
            "location": location,
            "url": url,
            "jobId": self._extract_job_id(url),
        }

    @staticmethod
    def _extract_job_id(url: str) -> str:
        match = re.search(r"/view/[^/]*-(\d+)", url)
        return match.group(1) if match else url
