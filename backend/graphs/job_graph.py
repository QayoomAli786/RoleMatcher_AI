"""LangGraph StateGraph for job discovery, normalization, and matching.

Workflow:
    extract_keywords -> collect_from_sources -> normalize_jobs -> deduplicate ->
    embed_jobs -> filter_candidates -> score_matches -> generate_recommendations

Parallel source collection via JobSourceManager. Deterministic scoring; LLM only for final explanation.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from langgraph.graph import END, START, StateGraph

from backend.core.schemas import Job, JobMatch, ResumeProfile
from backend.core.state import JobState
from backend.services.embeddings import (
    batch_embed,
    compute_similarity,
    get_embedding_service,
)
from backend.services.job_deduplicator import deduplicate
from backend.services.job_normalizer import (
    extract_skills_from_description,
    normalize_generic_job,
    normalize_linkedin_job,
)
from backend.services.job_sources.manager import JobSourceManager
from backend.services.llm_service import ModelRouter, TaskCategory

logger = logging.getLogger(__name__)

_router = ModelRouter()
_source_manager = JobSourceManager()
_source_manager.register_default_sources()


# ── Nodes ──────────────────────────────────────────────────────────────────────


async def extract_keywords_node(state: JobState) -> dict:
    """Extract search keywords from the target role description and/or resume profile."""
    target = state.get("target_role", "")
    profile = state.get("resume_profile", {}) or {}

    # Pull skills directly from the resume profile when available
    resume_skills = [
        s.get("name", "")
        for s in profile.get("skills", [])
        if isinstance(s, dict) and s.get("name")
    ]

    keywords = extract_skills_from_description(target)
    keywords = list(dict.fromkeys(keywords))

    # Merge in resume skills (deduplicated, preserving order)
    for skill in resume_skills:
        if skill.lower() not in [k.lower() for k in keywords]:
            keywords.append(skill)

    # Ensure the target role itself is included
    if target and target.lower() not in [k.lower() for k in keywords]:
        keywords.insert(0, target)

    # Cap keyword count to keep queries focused
    keywords = keywords[:20]

    return {"query_keywords": keywords}


async def collect_from_sources_node(state: JobState) -> dict:
    """Query all registered job sources in parallel with failure isolation."""
    keywords = state.get("query_keywords", [])
    location = state.get("user_location", "")
    parts = list(keywords)
    if location:
        parts.append(location)
    query = " ".join(parts)
    if not query:
        return {"source_results": {}}

    try:
        jobs = await _source_manager.collect_jobs(query=query, limit=50)
    except Exception as exc:
        logger.error("Job collection failed: %s", exc)
        raise RuntimeError(f"Failed to collect jobs from sources: {exc}") from exc

    # Group jobs by source
    source_map: dict[str, list[dict]] = {}
    for job in jobs:
        source_map.setdefault(job.source, []).append(job.model_dump())

    return {"source_results": source_map}


async def normalize_jobs_node(state: JobState) -> dict:
    """Normalize raw job listings from each source into Job schema.

    Sources already return normalized ``Job`` objects — those are passed
    through unchanged so fields like ``source_url`` are preserved. Only truly
    raw listings get run through the source normalizer.
    """
    raw_results = state.get("source_results", {})
    normalized: list[dict] = []

    normalizers = {
        "linkedin": normalize_linkedin_job,
    }

    for source_name, raw_jobs in raw_results.items():
        normalizer = normalizers.get(source_name, normalize_generic_job)
        for raw in raw_jobs:
            try:
                if isinstance(raw, dict) and raw.get("created_at") is not None:
                    normalized.append(raw)
                    continue
                job = normalizer(raw)
                normalized.append(job.model_dump())
            except Exception as exc:
                logger.warning("Failed to normalize job from %s: %s", source_name, exc)

    return {"normalized_jobs": normalized}


async def deduplicate_node(state: JobState) -> dict:
    """Remove duplicate job listings across sources."""
    normalized = state.get("normalized_jobs", [])
    if not normalized:
        return {"deduplicated_jobs": []}

    jobs = [Job(**d) for d in normalized]
    unique = deduplicate(jobs)
    return {"deduplicated_jobs": [j.model_dump() for j in unique]}


async def embed_jobs_node(state: JobState) -> dict:
    """Generate embeddings for deduplicated jobs for semantic matching."""
    deduped = state.get("deduplicated_jobs", [])
    if not deduped:
        return {"candidate_jobs": []}

    # Build text representations for embedding
    texts = []
    for job_data in deduped:
        parts = [job_data.get("title", ""), job_data.get("company", "")]
        parts.extend(job_data.get("skills", []))
        desc = job_data.get("description", "")[:300]
        parts.append(desc)
        texts.append(" ".join(parts))

    try:
        embeddings = batch_embed(texts)
        for job_data, emb in zip(deduped, embeddings):
            job_data["_embedding"] = emb
    except Exception as exc:
        logger.warning("Job embedding failed: %s", exc)

    return {"candidate_jobs": deduped}


_ALL_LOCATIONS = {"all countries", "all", "worldwide", "global", "everywhere"}


def _is_all_locations(loc: str) -> bool:
    """Check if the location means 'show all' (no filtering)."""
    return loc.lower().strip() in _ALL_LOCATIONS


async def filter_candidates_node(state: JobState) -> dict:
    """Pre-filter candidates based on basic criteria (remove obviously irrelevant).

    Location filtering:
    - 'All Countries' / 'All' / 'Worldwide' → no location filtering (show everything)
    - Specific location → strict match (remote jobs always pass)
    - Empty location → treat as 'All Countries'
    """
    candidates = state.get("candidate_jobs", [])
    keywords = [k.lower() for k in state.get("query_keywords", [])]
    user_location = state.get("user_location", "").lower().strip()
    show_all_locations = _is_all_locations(user_location) or not user_location

    filtered = []
    for job_data in candidates:
        title = (job_data.get("title", "") or "").lower()
        skills = [s.lower() for s in job_data.get("skills", [])]
        desc = (job_data.get("description", "") or "").lower()[:500]

        # Basic relevance check: at least one keyword must match
        combined_text = f"{title} {' '.join(skills)} {desc}"
        if not any(kw in combined_text for kw in keywords):
            continue

        # Location filter
        if not show_all_locations:
            job_location = (job_data.get("location", "") or "").lower()
            is_remote = job_data.get("remote", False)
            if not is_remote:
                if not job_location:
                    # No location listed — skip (user asked for a specific place)
                    continue
                # Normalize for comparison: strip common suffixes
                def _loc_key(loc: str) -> str:
                    return loc.replace(", ", ",").replace(" metro area", "").replace(" area", "").strip()
                ul = _loc_key(user_location)
                jl = _loc_key(job_location)
                # Require at least one to contain the other, or share a city token
                if not (ul in jl or jl in ul):
                    ul_tokens = set(t.strip() for t in ul.split(",") if len(t.strip()) > 2)
                    jl_tokens = set(t.strip() for t in jl.split(",") if len(t.strip()) > 2)
                    if not (ul_tokens & jl_tokens):
                        continue

        filtered.append(job_data)

    return {"candidate_jobs": filtered}


async def score_matches_node(state: JobState) -> dict:
    """Score each candidate against the resume using deterministic metrics + semantic similarity."""
    candidates = state.get("candidate_jobs", [])
    if not candidates:
        return {"matched_jobs": []}

    # Use the resume profile skills as the baseline for matching
    profile = state.get("resume_profile", {}) or {}
    resume_skill_names = [
        s.get("name", "")
        for s in profile.get("skills", [])
        if isinstance(s, dict) and s.get("name")
    ]
    if not resume_skill_names:
        # Fall back to query keywords when no resume profile available
        resume_skill_names = state.get("query_keywords", [])

    resume_skills = set(s.lower() for s in resume_skill_names)
    user_location = state.get("user_location", "").lower().strip()

    matched: list[dict] = []
    embedding_service = get_embedding_service()

    for job_data in candidates:
        job_skills = set(s.lower() for s in job_data.get("skills", []))
        title = (job_data.get("title", "") or "").lower()

        # Skill overlap score
        if job_skills:
            overlap = len(resume_skills & job_skills) / len(job_skills) if job_skills else 0.0
            overlap = min(overlap, 1.0)
        else:
            overlap = 0.5  # default if no skills listed

        # Keyword-in-title score
        title_score = sum(1 for k in resume_skills if k in title) / max(len(resume_skills), 1)
        title_score = min(title_score, 1.0)

        # Semantic score (embedding similarity)
        semantic_score = 0.0
        job_emb = job_data.get("_embedding")
        if job_emb and resume_skills:
            # Create a simple query embedding from resume keywords
            query_text = " ".join(list(resume_skills)[:15])
            try:
                query_emb = embedding_service.generate_embedding(query_text)
                semantic_score = compute_similarity(query_emb, job_emb)
            except Exception:
                semantic_score = 0.5

        # Location score: compare job location against user preference
        is_remote = job_data.get("remote", False)
        job_location = (job_data.get("location", "") or "").lower()

        if _is_all_locations(user_location):
            # User wants all locations — neutral score for everyone
            location_score = 0.8
        elif is_remote:
            location_score = 0.95
        elif user_location and job_location:
            def _loc_key(loc: str) -> str:
                return loc.replace(", ", ",").replace(" metro area", "").replace(" area", "").strip()
            ul = _loc_key(user_location)
            jl = _loc_key(job_location)
            if ul in jl or jl in ul:
                location_score = 1.0
            else:
                ul_tokens = set(t.strip() for t in ul.split(",") if len(t.strip()) > 2)
                jl_tokens = set(t.strip() for t in jl.split(",") if len(t.strip()) > 2)
                location_score = 1.0 if (ul_tokens & jl_tokens) else 0.3
        else:
            location_score = 0.7  # unknown location — neutral

        # Composite score
        overall = (overlap * 0.35 + title_score * 0.25 + semantic_score * 0.25 + location_score * 0.15)

        missing = list(job_skills - resume_skills)

        # Ensure the job dict has a stable UUID for the analyze endpoint
        if not job_data.get("id"):
            job_data["id"] = str(uuid.uuid4())

        match = JobMatch(
            job_id=job_data["id"],
            overall_score=round(overall, 3),
            skill_score=round(overlap, 3),
            experience_score=0.8,  # default; would need DB data
            seniority_score=0.8,
            location_score=round(location_score, 3),
            salary_score=0.8,
            semantic_score=round(semantic_score, 3),
            missing_skills=missing,
        )

        job_data["match"] = match.model_dump()
        matched.append(job_data)

    # Sort by overall score descending
    matched.sort(key=lambda j: j["match"]["overall_score"], reverse=True)

    return {"matched_jobs": matched}


async def generate_recommendations_node(state: JobState) -> dict:
    """Use LLM to generate a natural-language recommendation summary."""
    matched = state.get("matched_jobs", [])
    user_location = state.get("user_location", "")

    if not matched:
        if _is_all_locations(user_location):
            return {"recommendations": ["No jobs found matching your criteria. Try broadening your search keywords."]}
        else:
            return {"recommendations": [f"No jobs available for this role in {user_location}. Try a different location, search remotely, or broaden your keywords."]}

    top_jobs = matched[:5]
    job_summaries = []
    for i, job in enumerate(top_jobs, 1):
        match = job.get("match", {})
        job_summaries.append(
            f"{i}. {job.get('title', 'N/A')} at {job.get('company', 'N/A')} "
            f"(score: {match.get('overall_score', 0):.0%}, "
            f"missing: {', '.join(match.get('missing_skills', [])[:3])})"
        )

    location_context = ""
    if user_location and not _is_all_locations(user_location):
        location_context = f"Location preference: {user_location}\n"

    prompt = (
        f"Target role: {state.get('target_role', 'software engineer')}\n"
        f"{location_context}"
        f"Top {len(top_jobs)} matched jobs:\n" + "\n".join(job_summaries)
        + "\n\nProvide 2-3 brief strategic recommendations for the user."
    )

    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": prompt}],
            category=TaskCategory.CAREER_STRATEGY,
        )
        recommendations = [line.strip() for line in str(result).split("\n") if line.strip()]
        return {"recommendations": recommendations}
    except Exception as exc:
        logger.error("LLM recommendation failed: %s", exc)
        raise RuntimeError(f"Failed to generate recommendations: {exc}") from exc


async def error_node(state: JobState) -> dict:
    """Handle pipeline errors."""
    logger.error("Job pipeline failed for user=%s", state.get("user_id"))
    return {"recommendations": ["Job search pipeline encountered an error. Please try again."]}


# ── Routing ────────────────────────────────────────────────────────────────────


def route_after_collect(state: JobState) -> Literal["normalize_jobs", "error_node"]:
    """Branch on whether sources returned results."""
    if not state.get("source_results"):
        return "error_node"
    return "normalize_jobs"


def route_after_filter(state: JobState) -> Literal["score_matches", "error_node"]:
    """Branch on whether filtering yielded candidates."""
    if not state.get("candidate_jobs"):
        return "error_node"
    return "score_matches"


# ── Graph ──────────────────────────────────────────────────────────────────────


def build_job_graph() -> StateGraph:
    """Construct the job discovery and matching workflow."""
    graph = StateGraph(JobState)

    # Nodes
    graph.add_node("extract_keywords", extract_keywords_node)
    graph.add_node("collect_from_sources", collect_from_sources_node)
    graph.add_node("normalize_jobs", normalize_jobs_node)
    graph.add_node("deduplicate", deduplicate_node)
    graph.add_node("embed_jobs", embed_jobs_node)
    graph.add_node("filter_candidates", filter_candidates_node)
    graph.add_node("score_matches", score_matches_node)
    graph.add_node("generate_recommendations", generate_recommendations_node)
    graph.add_node("error_node", error_node)

    # Edges
    graph.add_edge(START, "extract_keywords")
    graph.add_edge("extract_keywords", "collect_from_sources")
    graph.add_conditional_edges(
        "collect_from_sources",
        route_after_collect,
        {"normalize_jobs": "normalize_jobs", "error_node": "error_node"},
    )
    graph.add_edge("normalize_jobs", "deduplicate")
    graph.add_edge("deduplicate", "embed_jobs")
    graph.add_edge("embed_jobs", "filter_candidates")
    graph.add_conditional_edges(
        "filter_candidates",
        route_after_filter,
        {"score_matches": "score_matches", "error_node": "error_node"},
    )
    graph.add_edge("score_matches", "generate_recommendations")
    graph.add_edge("generate_recommendations", END)
    graph.add_edge("error_node", END)

    return graph


# Compiled graph instance
job_pipeline = build_job_graph().compile()
