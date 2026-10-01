"""Deterministic skill gap analysis: current vs required vs market."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.core.schemas import ProficiencyLevel, SkillGap

# ── Normalization (shared) ──────────────────────────────────────────────────

from backend.services.skill_aliases import normalize_skill


def _norm(raw: str) -> str:
    return normalize_skill(raw)


# ── Market Demand Estimation ──────────────────────────────────────────────────


def _estimate_market_demand(skill: str, market_skills: dict[str, int]) -> str:
    """Estimate market demand from frequency map (int = count of jobs requiring it)."""
    count = market_skills.get(skill, 0)
    total = sum(market_skills.values()) if market_skills else 1
    ratio = count / total if total > 0 else 0

    if ratio >= 0.3:
        return "high"
    if ratio >= 0.1:
        return "medium"
    return "low"


# ── Public API ────────────────────────────────────────────────────────────────


def analyze_skill_gaps(
    resume_skills: list[str],
    target_role_skills: list[str],
    market_skills: dict[str, int],
) -> list[SkillGap]:
    """
    Identify skill gaps by comparing resume skills against
    target role requirements and market demand.

    Categories:
      - missing: required but not on resume
      - strong: well-represented on resume
      - weak: present but may need improvement
      - emerging: high market demand but not required for target role

    Priority: 1 (highest) to 5 (lowest), based on market demand + role requirement.
    """
    resume_set = {_norm(s) for s in resume_skills}
    role_set = {_norm(s) for s in target_role_skills}

    gaps: list[SkillGap] = []
    seen: set[str] = set()

    # Missing skills: required by role, not on resume
    for skill in sorted(role_set):
        if skill in resume_set:
            continue
        demand = _estimate_market_demand(skill, market_skills)
        priority = _priority_from_demand(demand, is_required=True)
        gaps.append(SkillGap(
            skill=skill,
            required_level=ProficiencyLevel.intermediate,
            priority=priority,
            market_demand=demand,
        ))
        seen.add(skill)

    # Strong skills: present on resume and required
    for skill in sorted(role_set & resume_set):
        if skill in seen:
            continue
        demand = _estimate_market_demand(skill, market_skills)
        gaps.append(SkillGap(
            skill=skill,
            current_level=ProficiencyLevel.advanced,
            required_level=ProficiencyLevel.intermediate,
            priority=5,
            market_demand=demand,
        ))
        seen.add(skill)

    # Emerging skills: high market demand, not on resume, not required by role
    for skill, count in sorted(market_skills.items(), key=lambda x: -x[1]):
        if skill in resume_set or skill in seen:
            continue
        demand = _estimate_market_demand(skill, market_skills)
        if demand == "high":
            priority = _priority_from_demand(demand, is_required=False)
            gaps.append(SkillGap(
                skill=skill,
                required_level=ProficiencyLevel.intermediate,
                priority=priority,
                market_demand=demand,
            ))
            seen.add(skill)

    # Weak skills: on resume but not in role requirements, low market demand
    for skill in sorted(resume_set - role_set):
        if skill in seen:
            continue
        demand = _estimate_market_demand(skill, market_skills)
        if demand in ("low", "medium"):
            gaps.append(SkillGap(
                skill=skill,
                current_level=ProficiencyLevel.beginner,
                required_level=ProficiencyLevel.intermediate,
                priority=5,
                market_demand=demand,
            ))
            seen.add(skill)

    gaps.sort(key=lambda g: g.priority)
    return gaps


def _priority_from_demand(demand: str, is_required: bool) -> int:
    """Convert market demand + role requirement into priority (1=highest)."""
    if is_required and demand == "high":
        return 1
    if is_required and demand == "medium":
        return 2
    if is_required:
        return 3
    if demand == "high":
        return 3
    if demand == "medium":
        return 4
    return 5
