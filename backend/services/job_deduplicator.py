"""Deterministic job deduplication: fingerprint, URL, and token-overlap similarity."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Sequence

from backend.core.schemas import Job

# ── Fingerprinting ────────────────────────────────────────────────────────────

_STRIP_RE = re.compile(r"[^a-z0-9 ]")
_SPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).lower()
    text = _SPACE_RE.sub(" ", _STRIP_RE.sub("", text)).strip()
    return text


def _fingerprint(job: Job) -> str:
    """Deterministic key from company+title+location."""
    company = _normalize(job.company)
    title = _normalize(job.title)
    location = _normalize(job.location)
    return f"{company}|{title}|{location}"


_URL_CLEAN_RE = re.compile(r"[?#].*$|https?://|www\.|/+$")


def _normalize_url(url: str) -> str:
    """Normalize a job URL for dedup."""
    url = _URL_CLEAN_RE.sub("", url.lower().strip())
    return url.rstrip("/")


def _tokenize(text: str) -> set[str]:
    return set(_normalize(text).split())


# ── Public API ────────────────────────────────────────────────────────────────


def deduplicate(jobs: Sequence[Job], *, similarity_threshold: float = 0.7) -> list[Job]:
    """
    Deduplicate a list of jobs by:
      1. Company+title+location fingerprint (exact)
      2. Normalized URL (exact)
      3. Token overlap (near-duplicate)
    """
    unique: list[Job] = []
    fp_seen: dict[str, int] = {}
    url_seen: dict[str, int] = {}
    token_sets: list[set[str]] = []

    for job in jobs:
        fp = _fingerprint(job)
        if fp in fp_seen:
            _merge_into(unique[fp_seen[fp]], job)
            continue

        norm_url = _normalize_url(job.source_url) if job.source_url else ""
        if norm_url and norm_url in url_seen:
            _merge_into(unique[url_seen[norm_url]], job)
            continue

        is_near_dup = False
        job_tokens = _tokenize(f"{job.title} {job.description[:500]}")
        for idx, existing_tokens in enumerate(token_sets):
            if not job_tokens or not existing_tokens:
                continue
            overlap = len(job_tokens & existing_tokens) / max(len(job_tokens | existing_tokens), 1)
            if overlap >= similarity_threshold:
                _merge_into(unique[idx], job)
                is_near_dup = True
                break

        if not is_near_dup:
            idx = len(unique)
            unique.append(job)
            fp_seen[fp] = idx
            if norm_url:
                url_seen[norm_url] = idx
            token_sets.append(job_tokens)

    return unique


def _merge_into(target: Job, source: Job) -> None:
    """Merge information from a duplicate job into the target."""
    if not target.description and source.description:
        target.description = source.description

    source_skills = set(source.skills)
    existing = set(target.skills)
    target.skills = list(existing | source_skills)

    if not target.salary_min and source.salary_min:
        target.salary_min = source.salary_min
    if not target.salary_max and source.salary_max:
        target.salary_max = source.salary_max

    if not target.source_url and source.source_url:
        target.source_url = source.source_url
    if not target.location and source.location:
        target.location = source.location
    if not target.employment_type and source.employment_type:
        target.employment_type = source.employment_type
    if not target.seniority and source.seniority:
        target.seniority = source.seniority
    if not target.posted_at and source.posted_at:
        target.posted_at = source.posted_at
    if target.source == "generic" and source.source != "generic":
        target.source = source.source


def find_duplicates(jobs: Sequence[Job], *, similarity_threshold: float = 0.7) -> list[tuple[int, int]]:
    """Return pairs of (i, j) indices where jobs[i] and jobs[j] are duplicates."""
    fps: dict[str, list[int]] = defaultdict(list)
    urls: dict[str, list[int]] = defaultdict(list)
    token_list: list[set[str]] = []
    duplicates: list[tuple[int, int]] = []

    for i, job in enumerate(jobs):
        fp = _fingerprint(job)
        for j in fps[fp]:
            duplicates.append((j, i))
        fps[fp].append(i)

        norm_url = _normalize_url(job.source_url) if job.source_url else ""
        if norm_url:
            for j in urls[norm_url]:
                duplicates.append((j, i))
            urls[norm_url].append(i)

        job_tokens = _tokenize(f"{job.title} {job.description[:500]}")
        for j, existing_tokens in enumerate(token_list):
            if not job_tokens or not existing_tokens:
                continue
            overlap = len(job_tokens & existing_tokens) / max(len(job_tokens | existing_tokens), 1)
            if overlap >= similarity_threshold:
                duplicates.append((j, i))
                break

        token_list.append(job_tokens)

    return duplicates
