"""LangGraph state definitions for CareerCopilot AI workflows."""

from typing import Annotated, Any, Literal
from uuid import UUID

from langgraph.graph import add_messages
from typing_extensions import TypedDict


class ResumeState(TypedDict):
    """State for the resume parsing and analysis pipeline."""

    user_id: UUID
    resume_id: UUID
    resume_version_id: UUID
    resume_text: str
    resume_profile: dict[str, Any]  # Serialized ResumeProfile
    parsing_status: Literal["pending", "in_progress", "completed", "failed"]
    error: str | None


class JobState(TypedDict):
    """State for the job search and matching pipeline."""

    user_id: UUID
    resume_id: UUID
    target_role: str
    resume_profile: dict[str, Any]  # Serialized ResumeProfile
    user_location: str
    query_keywords: list[str]
    source_results: dict[str, list[dict[str, Any]]]  # source_name -> raw jobs
    normalized_jobs: list[dict[str, Any]]
    deduplicated_jobs: list[dict[str, Any]]
    candidate_jobs: list[dict[str, Any]]
    matched_jobs: list[dict[str, Any]]
    recommendations: list[str]


class ATSState(TypedDict):
    """State for the ATS scoring and analysis pipeline."""

    user_id: UUID
    resume_id: UUID
    job_id: UUID
    resume_text: str
    job_description: str
    deterministic_score: dict[str, float]
    llm_explanation: dict[str, Any]
    report: dict[str, Any]  # Serialized ATSReport


class CareerState(TypedDict):
    """State for the career planning pipeline."""

    user_id: UUID
    resume_id: UUID
    target_role: str
    resume_profile: dict[str, Any]
    skill_gaps: list[dict[str, Any]]
    market_data: dict[str, Any]
    plan: dict[str, Any]  # Serialized CareerPlan


class InterviewState(TypedDict):
    """State for the interview preparation pipeline."""

    user_id: UUID
    job_id: UUID
    resume_id: UUID
    resume_profile: dict[str, Any]
    job_info: dict[str, Any]
    questions: list[dict[str, Any]]
    current_question_index: int
    user_answer: str
    evaluation: dict[str, Any]
    session_id: UUID
    messages: Annotated[list[dict[str, Any]], add_messages]


class ChatState(TypedDict):
    """State for the conversational AI interface."""

    user_id: UUID
    conversation_id: UUID
    message: str
    context: dict[str, Any]
    tools_used: list[str]
    response: str
    messages: Annotated[list[dict[str, Any]], add_messages]


class CoverLetterState(TypedDict):
    """State for the cover letter generation pipeline."""

    user_id: UUID
    resume_id: UUID
    job_id: UUID | None
    resume_text: str
    job_description: str
    job_title: str
    company_name: str
    resume_profile: dict[str, Any]
    tone: str  # professional, enthusiastic, confident, creative
    cover_letter: str
    error: str | None


class ResumeOptimizerState(TypedDict, total=False):
    """State for the job-specific resume tailoring pipeline."""

    user_id: UUID
    resume_id: UUID
    job_id: UUID | None
    resume_text: str
    resume_profile: dict[str, Any]
    job_description: str
    job_title: str
    company_name: str
    target_keywords: list[str]
    optimized: dict[str, Any]  # Serialized OptimizedResume
    stripped: list[str]  # Fabricated claims removed by the guardrail
    error: str | None
