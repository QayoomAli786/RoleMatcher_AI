"""LangGraph StateGraph for resume parsing and profile building.

Workflow:
    parse_resume -> extract_text -> detect_sections -> build_profile -> generate_embedding -> store_resume

All nodes are deterministic (no LLM). Conditional edges handle parsing failures.
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph

from backend.core.schemas import ResumeProfile
from backend.core.state import ResumeState
from backend.services.embeddings import generate_embedding
from backend.services.resume_parser import parse_resume_from_text

logger = logging.getLogger(__name__)


# ── Nodes ──────────────────────────────────────────────────────────────────────


async def parse_resume_node(state: ResumeState) -> dict:
    """Parse resume text from state (already extracted by the upload endpoint)."""
    raw_text = state.get("resume_text", "")
    if not raw_text:
        return {
            "parsing_status": "failed",
            "error": "No resume text provided in state",
        }

    try:
        profile = parse_resume_from_text(raw_text)
        return {
            "resume_profile": profile.model_dump(),
            "parsing_status": "completed",
            "error": None,
        }
    except Exception as exc:
        logger.error("Resume parsing failed: %s", exc)
        return {"parsing_status": "failed", "error": str(exc)}


async def extract_text_node(state: ResumeState) -> dict:
    """Validate that resume text was successfully extracted."""
    if not state.get("resume_text"):
        return {"parsing_status": "failed", "error": "No text extracted from resume"}
    return {}


async def detect_sections_node(state: ResumeState) -> dict:
    """Validate that the profile has meaningful sections."""
    profile_data = state.get("resume_profile", {})
    skills = profile_data.get("skills", [])
    experience = profile_data.get("experience", [])

    if not skills and not experience:
        return {
            "parsing_status": "failed",
            "error": "Resume contains no recognizable skills or experience sections",
        }
    return {}


async def build_profile_node(state: ResumeState) -> dict:
    """Enrich the profile with computed fields (years of experience, target roles)."""
    profile_data = state.get("resume_profile", {})
    profile = ResumeProfile(**profile_data)

    if profile.experience:
        from datetime import date

        earliest = min(e.start_date for e in profile.experience)
        latest_end = max(
            (e.end_date or date.today() for e in profile.experience), default=date.today()
        )
        years = round((latest_end - earliest).days / 365.25, 1)
        profile.years_experience = years

    title_keywords: dict[str, list[str]] = {
        "engineer": ["software engineer", "backend engineer", "frontend engineer", "full stack engineer"],
        "developer": ["web developer", "mobile developer", "full stack developer"],
        "scientist": ["data scientist", "ml scientist"],
        "analyst": ["data analyst", "business analyst"],
        "architect": ["solution architect", "cloud architect"],
        "manager": ["engineering manager", "product manager", "technical manager"],
        "designer": ["ui designer", "ux designer", "product designer"],
    }

    roles: set[str] = set()
    for exp in profile.experience:
        title_lower = exp.title.lower()
        for keyword, role_list in title_keywords.items():
            if keyword in title_lower:
                roles.update(role_list)
    profile.target_roles = list(roles)[:5] if roles else ["software engineer"]

    return {"resume_profile": profile.model_dump()}


async def generate_embedding_node(state: ResumeState) -> dict:
    """Generate a vector embedding of the resume for similarity search."""
    profile_data = state.get("resume_profile", {})
    profile = ResumeProfile(**profile_data)

    parts = [profile.summary] if profile.summary else []
    parts.extend(s.name for s in profile.skills)
    parts.extend(f"{e.title} {e.company} {e.description[:200]}" for e in profile.experience)
    text_for_embedding = " ".join(parts)

    if not text_for_embedding.strip():
        return {}

    try:
        embedding = generate_embedding(text_for_embedding)
        return {"resume_profile": {**profile_data, "_embedding": embedding}}
    except Exception as exc:
        logger.warning("Embedding generation failed: %s", exc)
        return {}


async def store_resume_node(state: ResumeState) -> dict:
    """No-op — profile is already stored by the upload endpoint."""
    return {}


async def error_node(state: ResumeState) -> dict:
    """Handle parsing errors."""
    logger.error(
        "Resume pipeline failed for resume=%s: %s",
        state["resume_id"],
        state.get("error", "unknown"),
    )
    return {"parsing_status": "failed"}


# ── Routing ────────────────────────────────────────────────────────────────────


def route_after_parse(state: ResumeState) -> Literal["extract_text", "error_node"]:
    if state.get("parsing_status") == "failed":
        return "error_node"
    return "extract_text"


def route_after_sections(state: ResumeState) -> Literal["build_profile", "error_node"]:
    if state.get("parsing_status") == "failed":
        return "error_node"
    return "build_profile"


# ── Graph ──────────────────────────────────────────────────────────────────────


def build_resume_graph() -> StateGraph:
    graph = StateGraph(ResumeState)

    graph.add_node("parse_resume", parse_resume_node)
    graph.add_node("extract_text", extract_text_node)
    graph.add_node("detect_sections", detect_sections_node)
    graph.add_node("build_profile", build_profile_node)
    graph.add_node("generate_embedding", generate_embedding_node)
    graph.add_node("store_resume", store_resume_node)
    graph.add_node("error_node", error_node)

    graph.add_edge(START, "parse_resume")
    graph.add_conditional_edges(
        "parse_resume",
        route_after_parse,
        {"extract_text": "extract_text", "error_node": "error_node"},
    )
    graph.add_edge("extract_text", "detect_sections")
    graph.add_conditional_edges(
        "detect_sections",
        route_after_sections,
        {"build_profile": "build_profile", "error_node": "error_node"},
    )
    graph.add_edge("build_profile", "generate_embedding")
    graph.add_edge("generate_embedding", "store_resume")
    graph.add_edge("store_resume", END)
    graph.add_edge("error_node", END)

    return graph


resume_pipeline = build_resume_graph().compile()
