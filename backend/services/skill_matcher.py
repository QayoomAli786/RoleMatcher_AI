"""Deterministic skill matching: overlap, exact, partial, and missing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Skill Alias Map (shared) ────────────────────────────────────────────────

from backend.services.skill_aliases import SKILL_ALIASES as _SKILL_ALIASES, normalize_skill

# Part-of-speech stems for fuzzy partial matching
_PARTIAL_PAIRS: list[tuple[str, str]] = [
    ("javascript", "node"),
    ("react", "react native"),
    ("python", "django"),
    ("python", "flask"),
    ("python", "fastapi"),
    ("java", "spring"),
    ("java", "kotlin"),
    ("typescript", "javascript"),
    ("html", "css"),
    ("html", "react"),
    ("sql", "postgresql"),
    ("sql", "mysql"),
    ("aws", "cloud"),
    ("docker", "kubernetes"),
    ("machine learning", "deep learning"),
    ("git", "ci/cd"),
]


def _normalize(raw: str) -> str:
    return normalize_skill(raw)


def _is_partial_match(a: str, b: str) -> bool:
    """Check if two skills have a known partial relationship."""
    pair = tuple(sorted([a, b]))
    for p1, p2 in _PARTIAL_PAIRS:
        if (a == p1 and b == p2) or (a == p2 and b == p1):
            return True
    if a in b or b in a:
        return True
    return False


# ── Result ────────────────────────────────────────────────────────────────────


@dataclass
class SkillMatchResult:
    exact_matches: list[str] = field(default_factory=list)
    partial_matches: list[tuple[str, str]] = field(default_factory=list)
    resume_only: list[str] = field(default_factory=list)
    job_only: list[str] = field(default_factory=list)
    overlap_percentage: float = 0.0
    total_resume: int = 0
    total_job: int = 0


# ── Public API ────────────────────────────────────────────────────────────────


def match_skills(resume_skills: list[str], job_skills: list[str]) -> SkillMatchResult:
    """
    Match resume skills against required job skills.

    Returns exact matches, partial matches, missing skills, and extra skills.
    """
    norm_resume = [_normalize(s) for s in resume_skills]
    norm_job = [_normalize(s) for s in job_skills]

    resume_set = set(norm_resume)
    job_set = set(norm_job)

    exact = list(resume_set & job_set)
    missing = list(job_set - resume_set)

    # Check partial matches for missing skills
    partial: list[tuple[str, str]] = []
    remaining_missing: list[str] = []
    for ms in missing:
        matched = False
        for rs in resume_set:
            if _is_partial_match(rs, ms):
                partial.append((rs, ms))
                matched = True
                break
        if not matched:
            remaining_missing.append(ms)

    resume_only = list(resume_set - job_set)

    total_job = len(job_set)
    overlap = (len(exact) + len(partial)) / total_job if total_job > 0 else 1.0

    return SkillMatchResult(
        exact_matches=sorted(exact),
        partial_matches=sorted(partial),
        resume_only=sorted(resume_only),
        job_only=sorted(remaining_missing),
        overlap_percentage=round(overlap * 100, 1),
        total_resume=len(resume_set),
        total_job=total_job,
    )
