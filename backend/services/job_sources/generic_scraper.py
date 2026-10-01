"""Generic HTML scraper for job listings with TF-IDF matching."""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter

import httpx
from bs4 import BeautifulSoup, Tag

from backend.core.schemas import Job
from backend.services.job_normalizer import normalize_generic_job
from backend.services.job_sources.base import AbstractJobSource, SourceConfig

logger = logging.getLogger(__name__)

# Tokeniser for TF-IDF
_WORD_RE = re.compile(r"[a-zA-Z]{3,}")


def _tokenise(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _compute_tfidf(
    chunks: list[str],
    query_tokens: list[str],
    top_k: int = 10,
) -> list[str]:
    """Return the top_k chunks most relevant to *query_tokens* via TF-IDF."""
    if not chunks:
        return []

    # Build document frequency
    doc_freq: Counter[str] = Counter()
    doc_tokens: list[list[str]] = []
    for chunk in chunks:
        tokens = _tokenise(chunk)
        doc_tokens.append(tokens)
        unique = set(tokens)
        for t in unique:
            doc_freq[t] += 1

    n_docs = len(chunks)
    query_set = set(query_tokens)
    scores: list[tuple[int, float]] = []

    for idx, tokens in enumerate(doc_tokens):
        tf = Counter(tokens)
        score = 0.0
        for qt in query_set:
            if qt in tf:
                idf = 1.0 + (n_docs / (1 + doc_freq[qt]))
                score += (tf[qt] / len(tokens)) * idf
        scores.append((idx, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [chunks[i] for i, _ in scores[:top_k] if scores[0][1] > 0]


class GenericScraperSource(AbstractJobSource):
    """Scrape an arbitrary URL for job listing blocks and match via TF-IDF."""

    def __init__(self, target_url: str = "") -> None:
        super().__init__(
            SourceConfig(
                name="generic_scraper",
                enabled=True,
                priority=1,
                rate_limit=0.5,
                timeout_seconds=25.0,
            )
        )
        self.target_url = target_url

    async def _fetch_raw(self, query: str, limit: int) -> list[Job]:
        url = self.target_url
        if not url:
            return []

        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; CareerCopilotBot/1.0)",
                },
            )
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        chunks = self._extract_text_chunks(soup)

        query_tokens = _tokenise(query)
        relevant = _compute_tfidf(chunks, query_tokens, top_k=limit)

        jobs: list[Job] = []
        for idx, chunk in enumerate(relevant):
            title, company = self._guess_title_company(chunk)
            raw = {
                "source": f"generic:{url[:80]}",
                "title": title or f"Position #{idx + 1}",
                "company": company,
                "description": chunk,
                "url": url,
                "source_job_id": hashlib.md5(chunk.encode()).hexdigest(),
            }
            try:
                jobs.append(normalize_generic_job(raw))
            except Exception as exc:
                logger.debug("Skipping generic job: %s", exc)

        logger.info("GenericScraper: extracted %d jobs from %s", len(jobs), url)
        return jobs

    @staticmethod
    def _extract_text_chunks(soup: BeautifulSoup) -> list[str]:
        """Extract meaningful text blocks from the page."""
        # Remove script/style/nav/footer noise
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        chunks: list[str] = []
        # Strategy 1: look for article/card/li sections
        for container in soup.select("article, .job-card, .listing, li"):
            text = container.get_text(separator=" ", strip=True)
            if len(text) > 50:
                chunks.append(text)

        # Strategy 2: fall back to all paragraphs
        if not chunks:
            for p in soup.find_all("p"):
                text = p.get_text(strip=True)
                if len(text) > 50:
                    chunks.append(text)

        return chunks

    @staticmethod
    def _guess_title_company(text: str) -> tuple[str, str]:
        """Heuristic: first line is title, second line is company."""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) >= 2:
            return lines[0], lines[1]
        if lines:
            return lines[0], ""
        return "", ""
