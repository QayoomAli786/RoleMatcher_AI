"""Top-level orchestration for CareerCopilot AI workflows.

Coordinates the main pipelines:
    - resume_pipeline: resume_graph
    - job_pipeline: job_graph
    - ats_pipeline: ats_graph
    - career_pipeline: career_graph
    - full_pipeline: resume -> jobs -> ATS -> career (sequential with shared state)

Each pipeline is independently invokable.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from backend.core.state import ATSState, CareerState, JobState, ResumeState

logger = logging.getLogger(__name__)


# ── Lazy imports to avoid circular dependencies ────────────────────────────────


def _get_resume_pipeline():
    from backend.graphs.resume_graph import resume_pipeline
    return resume_pipeline


def _get_job_pipeline():
    from backend.graphs.job_graph import job_pipeline
    return job_pipeline


def _get_ats_pipeline():
    from backend.graphs.ats_graph import ats_pipeline
    return ats_pipeline


def _get_career_pipeline():
    from backend.graphs.career_graph import career_pipeline
    return career_pipeline


def _get_interview_pipeline():
    from backend.graphs.interview_graph import interview_pipeline
    return interview_pipeline


def _get_chat_pipeline():
    from backend.graphs.chat_graph import chat_pipeline
    return chat_pipeline


def _get_cover_letter_pipeline():
    from backend.graphs.cover_letter_graph import cover_letter_pipeline
    return cover_letter_pipeline


def _get_resume_optimizer_pipeline():
    from backend.graphs.resume_optimizer_graph import resume_optimizer_pipeline
    return resume_optimizer_pipeline


# ── Pipeline Invokers ──────────────────────────────────────────────────────────


async def run_resume_pipeline(
    user_id: UUID,
    resume_id: UUID,
    resume_version_id: UUID | None = None,
) -> dict[str, Any]:
    """Run the resume parsing and profile building pipeline."""
    pipeline = _get_resume_pipeline()

    initial_state: ResumeState = {
        "user_id": user_id,
        "resume_id": resume_id,
        "resume_version_id": resume_version_id or uuid4(),
        "resume_text": "",
        "resume_profile": {},
        "parsing_status": "pending",
        "error": None,
    }

    result = await pipeline.ainvoke(initial_state)
    return dict(result)


async def run_job_pipeline(
    user_id: UUID,
    resume_id: UUID,
    target_role: str,
    resume_profile: dict | None = None,
    user_location: str = "",
) -> dict[str, Any]:
    """Run the job discovery and matching pipeline."""
    pipeline = _get_job_pipeline()

    initial_state: JobState = {
        "user_id": user_id,
        "resume_id": resume_id,
        "target_role": target_role,
        "user_location": user_location,
        "query_keywords": [],
        "source_results": {},
        "normalized_jobs": [],
        "deduplicated_jobs": [],
        "candidate_jobs": [],
        "matched_jobs": [],
        "recommendations": [],
    }

    # Attach resume profile for skill-based matching
    if resume_profile:
        initial_state["resume_profile"] = resume_profile

    result = await pipeline.ainvoke(initial_state)
    return dict(result)


async def run_ats_pipeline(
    user_id: UUID,
    resume_id: UUID,
    job_id: UUID,
    resume_text: str,
    job_description: str,
    resume_profile: dict | None = None,
) -> dict[str, Any]:
    """Run the ATS scoring and analysis pipeline."""
    pipeline = _get_ats_pipeline()

    initial_state: ATSState = {
        "user_id": user_id,
        "resume_id": resume_id,
        "job_id": job_id,
        "resume_text": resume_text,
        "job_description": job_description,
        "deterministic_score": {},
        "llm_explanation": {},
        "report": {},
    }

    result = await pipeline.ainvoke(initial_state)
    return dict(result)


async def run_career_pipeline(
    user_id: UUID,
    resume_id: UUID,
    target_role: str,
    resume_profile: dict | None = None,
) -> dict[str, Any]:
    """Run the career planning pipeline."""
    pipeline = _get_career_pipeline()

    initial_state: CareerState = {
        "user_id": user_id,
        "resume_id": resume_id,
        "target_role": target_role,
        "resume_profile": resume_profile or {},
        "skill_gaps": [],
        "market_data": {},
        "plan": {},
    }

    result = await pipeline.ainvoke(initial_state)
    return dict(result)


async def run_interview_pipeline(
    user_id: UUID,
    job_id: UUID,
    resume_id: UUID,
    resume_profile: dict | None = None,
    job_info: dict | None = None,
) -> dict[str, Any]:
    """Run the interview preparation pipeline."""
    pipeline = _get_interview_pipeline()

    initial_state = {
        "user_id": user_id,
        "job_id": job_id,
        "resume_id": resume_id,
        "resume_profile": resume_profile or {},
        "job_info": job_info or {},
        "questions": [],
        "current_question_index": 0,
        "user_answer": "",
        "evaluation": {},
        "session_id": uuid4(),
        "messages": [],
    }

    result = await pipeline.ainvoke(initial_state)
    return dict(result)


async def run_chat_pipeline(
    user_id: UUID,
    conversation_id: UUID,
    message: str,
    context: dict | None = None,
) -> dict[str, Any]:
    """Run the chat assistant pipeline."""
    pipeline = _get_chat_pipeline()

    initial_state = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "message": message,
        "context": context or {},
        "tools_used": [],
        "response": "",
        "messages": [],
    }

    result = await pipeline.ainvoke(initial_state)
    return dict(result)


async def run_cover_letter_pipeline(
    user_id: UUID,
    resume_id: UUID,
    job_description: str,
    job_title: str = "",
    company_name: str = "",
    tone: str = "professional",
    job_id: UUID | None = None,
    resume_profile: dict | None = None,
) -> dict[str, Any]:
    """Run the cover letter generation pipeline."""
    pipeline = _get_cover_letter_pipeline()

    initial_state = {
        "user_id": user_id,
        "resume_id": resume_id,
        "job_id": job_id,
        "resume_text": "",
        "job_description": job_description,
        "job_title": job_title,
        "company_name": company_name,
        "resume_profile": resume_profile or {},
        "tone": tone,
        "cover_letter": "",
        "error": None,
    }

    result = await pipeline.ainvoke(initial_state)
    return dict(result)


async def run_resume_optimizer_pipeline(
    user_id: UUID,
    resume_id: UUID,
    job_description: str,
    job_title: str = "",
    company_name: str = "",
    job_id: UUID | None = None,
    resume_profile: dict | None = None,
    resume_text: str = "",
) -> dict[str, Any]:
    """Run the job-specific resume tailoring pipeline."""
    pipeline = _get_resume_optimizer_pipeline()

    initial_state: dict[str, Any] = {
        "user_id": user_id,
        "resume_id": resume_id,
        "job_id": job_id,
        "resume_text": resume_text,
        "resume_profile": resume_profile or {},
        "job_description": job_description,
        "job_title": job_title,
        "company_name": company_name,
        "target_keywords": [],
        "optimized": {},
        "stripped": [],
        "error": None,
    }

    result = await pipeline.ainvoke(initial_state)
    return dict(result)


# ── Full Pipeline (Sequential) ─────────────────────────────────────────────────


async def run_full_pipeline(
    user_id: UUID,
    resume_id: UUID,
    target_role: str,
    job_description: str = "",
    job_id: UUID | None = None,
    user_location: str = "",
) -> dict[str, Any]:
    """
    Run the complete career intelligence pipeline:
        resume -> jobs -> ATS -> career

    Each stage feeds its output into the next via shared state.
    """
    results: dict[str, Any] = {}

    # Stage 1: Resume parsing
    logger.info("Full pipeline: Stage 1/4 - Resume parsing")
    resume_result = await run_resume_pipeline(user_id, resume_id)
    results["resume"] = resume_result

    resume_profile = resume_result.get("resume_profile", {})
    resume_text = resume_result.get("resume_text", "")

    if resume_result.get("parsing_status") == "failed":
        logger.error("Full pipeline aborted: resume parsing failed")
        results["error"] = "Resume parsing failed"
        return results

    # Stage 2: Job discovery
    logger.info("Full pipeline: Stage 2/4 - Job discovery")
    job_result = await run_job_pipeline(user_id, resume_id, target_role, user_location=user_location)
    results["jobs"] = job_result

    matched_jobs = job_result.get("matched_jobs", [])
    if matched_jobs and not job_id:
        # Use the top match for ATS analysis
        top_match = matched_jobs[0]
        job_id = top_match.get("id")
        job_description = top_match.get("description", job_description)

    # Stage 3: ATS analysis (if we have a job to compare against)
    if job_id and job_description:
        logger.info("Full pipeline: Stage 3/4 - ATS analysis")
        ats_result = await run_ats_pipeline(
            user_id=user_id,
            resume_id=resume_id,
            job_id=job_id,
            resume_text=resume_text,
            job_description=job_description,
            resume_profile=resume_profile,
        )
        results["ats"] = ats_result
    else:
        logger.info("Full pipeline: Stage 3/4 - ATS analysis skipped (no job match)")
        results["ats"] = {"skipped": True}

    # Stage 4: Career planning
    logger.info("Full pipeline: Stage 4/4 - Career planning")
    career_result = await run_career_pipeline(
        user_id=user_id,
        resume_id=resume_id,
        target_role=target_role,
        resume_profile=resume_profile,
    )
    results["career"] = career_result

    logger.info("Full pipeline complete for user=%s", user_id)
    return results


# ── Pipeline Registry ──────────────────────────────────────────────────────────


PIPELINE_REGISTRY: dict[str, Any] = {
    "resume": run_resume_pipeline,
    "job": run_job_pipeline,
    "ats": run_ats_pipeline,
    "career": run_career_pipeline,
    "interview": run_interview_pipeline,
    "chat": run_chat_pipeline,
    "cover_letter": run_cover_letter_pipeline,
    "resume_optimizer": run_resume_optimizer_pipeline,
    "full": run_full_pipeline,
}


def get_pipeline(name: str):
    """Retrieve a pipeline function by name."""
    pipeline = PIPELINE_REGISTRY.get(name)
    if pipeline is None:
        raise ValueError(f"Unknown pipeline: {name}. Available: {list(PIPELINE_REGISTRY.keys())}")
    return pipeline
