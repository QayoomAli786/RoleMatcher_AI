"""LangGraph StateGraph for ATS scoring and optimization.

Workflow:
    extract_keywords -> analyze_skills -> analyze_experience ->
    calculate_deterministic_score -> generate_llm_explanation -> build_report

Score is fully deterministic; LLM only produces the human-readable explanation.
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph

from backend.core.schemas import ATSReport, ResumeProfile
from backend.core.state import ATSState
from backend.services.ats_engine import calculate_ats_score
from backend.services.llm_service import ModelRouter, TaskCategory

logger = logging.getLogger(__name__)

_router = ModelRouter()


# ── Nodes ──────────────────────────────────────────────────────────────────────


async def extract_keywords_node(state: ATSState) -> dict:
    """Extract relevant keywords from the job description for scoring."""
    job_desc = state.get("job_description", "")
    if not job_desc:
        return {}

    # Keyword extraction is done inside calculate_ats_score,
    # but we pre-compute here for the LLM explanation step
    from backend.services.ats_engine import _extract_keywords

    keywords = _extract_keywords(job_desc, top_n=40)
    return {"deterministic_score": {"_job_keywords": keywords}}


async def analyze_skills_node(state: ATSState) -> dict:
    """Analyze skill coverage between resume and job description."""
    # Pre-computation step; actual scoring happens in calculate_deterministic_score
    return {}


async def analyze_experience_node(state: ATSState) -> dict:
    """Analyze experience relevance and seniority alignment."""
    return {}


async def calculate_deterministic_score_node(state: ATSState) -> dict:
    """Run the deterministic ATS scoring engine."""
    resume_text = state.get("resume_text", "")
    job_desc = state.get("job_description", "")
    profile_data = state.get("resume_profile", {})

    if not resume_text or not job_desc:
        return {
            "deterministic_score": {
                "overall": 0.0,
                "error": "Missing resume text or job description",
            }
        }

    try:
        profile = ResumeProfile(**profile_data) if profile_data else ResumeProfile()
        report = calculate_ats_score(resume_text, job_desc, profile)

        return {
            "deterministic_score": {
                "overall": report.overall_score,
                "keyword": report.keyword_score,
                "skill": report.skill_score,
                "experience": report.experience_score,
                "semantic": report.semantic_score,
                "education": report.education_score,
                "missing_keywords": report.missing_keywords,
                "missing_skills": report.missing_skills,
            }
        }
    except Exception as exc:
        logger.error("ATS scoring failed: %s", exc)
        return {"deterministic_score": {"overall": 0.0, "error": str(exc)}}


async def generate_llm_explanation_node(state: ATSState) -> dict:
    """Use LLM to generate a human-readable explanation of the ATS scores."""
    scores = state.get("deterministic_score", {})
    missing_kw = scores.get("missing_keywords", [])
    missing_skills = scores.get("missing_skills", [])

    prompt = (
        f"ATS Score Analysis:\n"
        f"Overall: {scores.get('overall', 0):.0f}%\n"
        f"Keyword: {scores.get('keyword', 0):.0f}%\n"
        f"Skill: {scores.get('skill', 0):.0f}%\n"
        f"Experience: {scores.get('experience', 0):.0f}%\n"
        f"Education: {scores.get('education', 0):.0f}%\n"
        f"Missing keywords: {', '.join(missing_kw[:10])}\n"
        f"Missing skills: {', '.join(missing_skills[:10])}\n\n"
        "Provide a brief explanation of why this score was given and "
        "3-5 actionable recommendations to improve the resume for this role."
    )

    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": prompt}],
            category=TaskCategory.ATS_EXPLANATION,
        )
        return {"llm_explanation": {"text": str(result), "scores": scores}}
    except Exception as exc:
        logger.warning("LLM explanation failed: %s", exc)
        return {"llm_explanation": {"text": "", "scores": scores, "error": str(exc)}}


async def build_report_node(state: ATSState) -> dict:
    """Assemble the final ATSReport from deterministic scores and LLM explanation."""
    scores = state.get("deterministic_score", {})
    explanation = state.get("llm_explanation", {})

    report = ATSReport(
        overall_score=scores.get("overall", 0.0),
        keyword_score=scores.get("keyword", 0.0),
        skill_score=scores.get("skill", 0.0),
        experience_score=scores.get("experience", 0.0),
        semantic_score=scores.get("semantic", 0.0),
        education_score=scores.get("education", 0.0),
        missing_keywords=scores.get("missing_keywords", []),
        missing_skills=scores.get("missing_skills", []),
        recommendations=[explanation.get("text", "")],
    )

    logger.info(
        "ATS report built: overall=%.1f%% user=%s job=%s",
        report.overall_score,
        state.get("user_id"),
        state.get("job_id"),
    )

    return {"report": report.model_dump()}


async def error_node(state: ATSState) -> dict:
    """Handle pipeline errors."""
    logger.error(
        "ATS pipeline failed for user=%s job=%s",
        state.get("user_id"),
        state.get("job_id"),
    )
    return {"report": ATSReport(overall_score=0.0).model_dump()}


# ── Routing ────────────────────────────────────────────────────────────────────


def route_after_score(state: ATSState) -> Literal["generate_llm_explanation", "build_report"]:
    """Skip LLM explanation if scoring failed entirely."""
    scores = state.get("deterministic_score", {})
    if scores.get("error"):
        return "build_report"
    return "generate_llm_explanation"


# ── Graph ──────────────────────────────────────────────────────────────────────


def build_ats_graph() -> StateGraph:
    """Construct the ATS scoring and analysis workflow."""
    graph = StateGraph(ATSState)

    # Nodes
    graph.add_node("extract_keywords", extract_keywords_node)
    graph.add_node("analyze_skills", analyze_skills_node)
    graph.add_node("analyze_experience", analyze_experience_node)
    graph.add_node("calculate_deterministic_score", calculate_deterministic_score_node)
    graph.add_node("generate_llm_explanation", generate_llm_explanation_node)
    graph.add_node("build_report", build_report_node)
    graph.add_node("error_node", error_node)

    # Edges
    graph.add_edge(START, "extract_keywords")
    graph.add_edge("extract_keywords", "analyze_skills")
    graph.add_edge("analyze_skills", "analyze_experience")
    graph.add_edge("analyze_experience", "calculate_deterministic_score")
    graph.add_conditional_edges(
        "calculate_deterministic_score",
        route_after_score,
        {
            "generate_llm_explanation": "generate_llm_explanation",
            "build_report": "build_report",
        },
    )
    graph.add_edge("generate_llm_explanation", "build_report")
    graph.add_edge("build_report", END)
    graph.add_edge("error_node", END)

    return graph


# Compiled graph instance
ats_pipeline = build_ats_graph().compile()
