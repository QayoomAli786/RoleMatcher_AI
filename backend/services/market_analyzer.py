"""Deterministic market analysis from a list of Job objects."""

from __future__ import annotations

import math
from collections import Counter

from backend.core.schemas import Job, MarketSnapshot

# ── Skill Normalization ───────────────────────────────────────────────────────

_TECH_ALIASES: dict[str, str] = {
    "js": "javascript", "ts": "typescript", "py": "python",
    "react.js": "react", "reactjs": "react", "react js": "react",
    "vue.js": "vue", "vuejs": "vue", "angular.js": "angular",
    "angularjs": "angular", "node.js": "node", "nodejs": "node",
    "next.js": "next.js", "nextjs": "next.js",
    "golang": "go", "c sharp": "c#", "c plus plus": "c++",
    "postgres": "postgresql", "mongo": "mongodb", "dynamo": "dynamodb",
    "k8s": "kubernetes", "tf": "tensorflow", "pt": "pytorch",
    "sklearn": "scikit-learn", "gcp": "google cloud",
    "tailwind css": "tailwindcss", "material ui": "material-ui",
    "fast api": "fastapi", "spring boot": "spring boot",
    "open ai": "openai", "hugging face": "huggingface",
    "apache spark": "spark", "apache kafka": "kafka",
}


def _norm_skill(s: str) -> str:
    s = s.strip().lower()
    return _TECH_ALIASES.get(s, s)


# ── Analysis ──────────────────────────────────────────────────────────────────

_TREND_THRESHOLD = 0.05  # 5%+ jobs mentioning a skill = trend


def analyze_market(jobs: list[Job], target_role: str = "") -> MarketSnapshot:
    """
    Aggregate job listing data into a market snapshot.
    All calculations are deterministic arithmetic on listing fields.
    """
    if not jobs:
        return MarketSnapshot(target_role=target_role)

    total = len(jobs)

    # Skill frequency
    skill_counter: Counter[str] = Counter()
    for job in jobs:
        seen: set[str] = set()
        for s in job.skills:
            ns = _norm_skill(s)
            if ns not in seen:
                skill_counter[ns] += 1
                seen.add(ns)

    skill_freq = {k: v for k, v in skill_counter.most_common(50)}

    # Role frequency
    role_counter: Counter[str] = Counter()
    for job in jobs:
        title_lower = job.title.strip().lower()
        role_counter[title_lower] += 1
    role_freq = {k: v for k, v in role_counter.most_common(30)}

    # Seniority distribution
    seniority_counter: Counter[str] = Counter()
    for job in jobs:
        s = job.seniority.strip().lower() if job.seniority else "unspecified"
        seniority_counter[s] += 1
    seniority_dist = {k: round(v / total * 100, 1) for k, v in seniority_counter.most_common()}

    # Remote percentage
    remote_count = sum(1 for j in jobs if j.remote)
    remote_pct = round(remote_count / total * 100, 1)

    # Salary distribution
    salaries: list[tuple[int, int]] = []
    for job in jobs:
        if job.salary_min and job.salary_max:
            salaries.append((job.salary_min, job.salary_max))
    salary_dist: dict[str, float] = {}
    if salaries:
        avgs = [(lo + hi) / 2 for lo, hi in salaries]
        avgs.sort()
        salary_dist = {
            "min": round(min(avgs), 0),
            "p25": round(_percentile(avgs, 0.25), 0),
            "median": round(_percentile(avgs, 0.5), 0),
            "p75": round(_percentile(avgs, 0.75), 0),
            "max": round(max(avgs), 0),
            "count": len(salaries),
        }

    # Technology trends: skills appearing in >threshold fraction of jobs
    trends = [
        skill for skill, count in skill_freq.items()
        if count / total >= _TREND_THRESHOLD
    ]

    return MarketSnapshot(
        target_role=target_role,
        skill_frequency=skill_freq,
        role_frequency=role_freq,
        seniority_distribution=seniority_dist,
        salary_distribution=salary_dist,
        remote_percentage=remote_pct,
        technology_trends=trends,
    )


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)
