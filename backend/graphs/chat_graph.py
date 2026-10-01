"""LangGraph StateGraph for the career chatbot assistant.

Workflow:
    classify_intent -> retrieve_context -> select_tools ->
    execute_tools -> generate_response

Tool selection: get_resume, search_jobs, get_ats_score, get_skill_gaps,
get_career_plan, generate_interview_questions. Context minimization:
only retrieve what is needed for the question.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.core.state import ChatState
from backend.services.llm_service import ModelRouter, TaskCategory

logger = logging.getLogger(__name__)

_router = ModelRouter()


# ── Intent Classification ──────────────────────────────────────────────────────


class Intent(str, Enum):
    RESUME_QUERY = "resume_query"
    JOB_SEARCH = "job_search"
    ATS_ANALYSIS = "ats_analysis"
    SKILL_GAPS = "skill_gaps"
    CAREER_PLANNING = "career_planning"
    INTERVIEW_PREP = "interview_prep"
    GENERAL_CHAT = "general_chat"


_INTENT_KEYWORDS: dict[Intent, list[str]] = {
    Intent.RESUME_QUERY: [
        "resume", "cv", "profile", "skills", "experience", "education",
        "my background", "my qualifications",
    ],
    Intent.JOB_SEARCH: [
        "find jobs", "search jobs", "job listings", "open positions",
        "hiring", "job opportunities", "looking for work",
    ],
    Intent.ATS_ANALYSIS: [
        "ats", "applicant tracking", "ats score", "resume score",
        "resume analysis", "keyword match", "optimize resume",
    ],
    Intent.SKILL_GAPS: [
        "skill gap", "missing skills", "what to learn", "upskill",
        "learning path", "improve skills", "competencies",
    ],
    Intent.CAREER_PLANNING: [
        "career plan", "career path", "career transition", "career growth",
        "long term", "roadmap", "career advice", "career strategy",
    ],
    Intent.INTERVIEW_PREP: [
        "interview", "interview questions", "practice interview",
        "interview prep", "interview coaching", "mock interview",
    ],
}


def _classify_intent(text: str) -> Intent:
    """Rule-based intent classification (fast, no LLM)."""
    text_lower = text.lower()
    scores: dict[Intent, int] = {intent: 0 for intent in Intent}

    for intent, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[intent] += 1

    best = max(scores, key=lambda i: scores[i])
    if scores[best] == 0:
        return Intent.GENERAL_CHAT
    return best


# ── Tool Definitions ───────────────────────────────────────────────────────────


_TOOLS = {
    "get_resume": "Retrieve the user's resume profile and skills",
    "search_jobs": "Search for job listings matching the user's profile",
    "get_ats_score": "Analyze resume against a specific job description",
    "get_skill_gaps": "Identify gaps between user's skills and target role",
    "get_career_plan": "Generate a career development plan",
    "generate_interview_questions": "Create interview questions for practice",
}


# ── Nodes ──────────────────────────────────────────────────────────────────────


async def classify_intent_node(state: ChatState) -> dict:
    """Classify the user's message intent to determine which tools to use."""
    message = state.get("message", "")
    intent = _classify_intent(message)

    return {"context": {**state.get("context", {}), "intent": intent.value}}


async def retrieve_context_node(state: ChatState) -> dict:
    """Retrieve minimal context needed for the classified intent."""
    intent = state.get("context", {}).get("intent", "general_chat")
    context = state.get("context", {})

    # Only retrieve what the specific intent needs
    if intent == Intent.RESUME_QUERY.value:
        # Would load from DB in production
        context["resume_loaded"] = True

    elif intent == Intent.JOB_SEARCH.value:
        context["search_ready"] = True

    elif intent == Intent.ATS_ANALYSIS.value:
        context["resume_loaded"] = True
        context["job_desc_needed"] = True

    elif intent == Intent.SKILL_GAPS.value:
        context["resume_loaded"] = True
        context["market_data_needed"] = True

    elif intent == Intent.CAREER_PLANNING.value:
        context["resume_loaded"] = True
        context["market_data_needed"] = True

    elif intent == Intent.INTERVIEW_PREP.value:
        context["resume_loaded"] = True
        context["job_info_needed"] = True

    return {"context": context}


async def select_tools_node(state: ChatState) -> dict:
    """Select which tools to invoke based on intent."""
    intent = state.get("context", {}).get("intent", "general_chat")

    tool_map = {
        Intent.RESUME_QUERY.value: ["get_resume"],
        Intent.JOB_SEARCH.value: ["get_resume", "search_jobs"],
        Intent.ATS_ANALYSIS.value: ["get_resume", "get_ats_score"],
        Intent.SKILL_GAPS.value: ["get_resume", "get_skill_gaps"],
        Intent.CAREER_PLANNING.value: ["get_resume", "get_career_plan"],
        Intent.INTERVIEW_PREP.value: ["get_resume", "generate_interview_questions"],
        Intent.GENERAL_CHAT.value: [],
    }

    tools = tool_map.get(intent, [])
    return {"context": {**state.get("context", {}), "tools_selected": tools}, "tools_used": tools}


async def execute_tools_node(state: ChatState) -> dict:
    """Execute selected tools and collect results."""
    tools = state.get("tools_used", [])
    context = state.get("context", {})
    user_id = state.get("user_id")
    results: dict[str, str] = {}

    for tool in tools:
        try:
            if tool == "get_resume":
                results["resume"] = await _get_resume_context(user_id)
            elif tool == "search_jobs":
                results["jobs"] = await _search_jobs_context(state)
            elif tool == "get_ats_score":
                results["ats"] = await _get_ats_context(state)
            elif tool == "get_skill_gaps":
                results["skill_gaps"] = await _get_skill_gaps_context(state)
            elif tool == "get_career_plan":
                results["career_plan"] = await _get_career_plan_context(state)
            elif tool == "generate_interview_questions":
                results["interview"] = "Interview questions can be generated via POST /api/interviews."
        except Exception as exc:
            logger.warning("Tool %s failed: %s", tool, exc)
            results[tool] = f"{tool}: temporarily unavailable"

    context["tool_results"] = results
    return {"context": context}


async def _get_resume_context(user_id) -> str:
    """Load user's latest resume profile from in-memory store."""
    if user_id is None:
        return "No user session."
    from backend.core.store import list_resumes
    from uuid import UUID as _UUID

    resumes = list_resumes(_UUID(str(user_id)) if not isinstance(user_id, _UUID) else user_id)
    if not resumes:
        return "No resume uploaded yet."
    resume = resumes[0]
    profile = resume.parsed_profile or {}
    skills = [s.get("name", "") for s in profile.get("skills", []) if isinstance(s, dict)][:20]
    exp = profile.get("experience", [])
    years = profile.get("years_experience", 0)
    parts = [f"Skills: {', '.join(skills) if skills else 'none detected'}"]
    if exp:
        latest = exp[0] if isinstance(exp[0], dict) else {}
        parts.append(f"Current role: {latest.get('title', 'N/A')} at {latest.get('company', 'N/A')}")
    parts.append(f"Years of experience: {years}")
    return " | ".join(parts)


async def _search_jobs_context(state: ChatState) -> str:
    """Search for jobs matching the user's profile."""
    from backend.services.job_sources.manager import JobSourceManager

    manager = JobSourceManager()
    manager.register_default_sources()
    query = state.get("message", "software engineer")
    try:
        jobs = await manager.collect_jobs(query=query, limit=5)
        if not jobs:
            return "No matching jobs found right now."
        summaries = []
        for j in jobs[:5]:
            summaries.append(f"{j.title} at {j.company} ({j.location})")
        return f"Found {len(jobs)} jobs: {('; '.join(summaries))}"
    except Exception as exc:
        return f"Job search unavailable: {exc}"


async def _get_ats_context(state: ChatState) -> str:
    """Get ATS analysis context."""
    return "ATS analysis is available via POST /api/ats/analyze with resume_id and job_id."


async def _get_skill_gaps_context(state: ChatState) -> str:
    """Get skill gap analysis context."""
    from backend.services.skill_gap_engine import analyze_skill_gaps
    from backend.services.market_analyzer import analyze_market
    from backend.core.store import list_resumes
    from uuid import UUID as _UUID

    user_id = state.get("user_id")
    if user_id is None:
        return "No user session."

    uid = _UUID(str(user_id)) if not isinstance(user_id, _UUID) else user_id
    resumes = list_resumes(uid)
    if not resumes or not resumes[0].parsed_profile:
        return "No resume data available for skill gap analysis."

    resume = resumes[0]
    resume_skills = [s.get("name", "") for s in resume.parsed_profile.get("skills", []) if isinstance(s, dict)]
    market = analyze_market(jobs=[], target_role="software engineer")
    market_skills = market.skill_frequency if hasattr(market, 'skill_frequency') else {}
    role_skills = list(market_skills.keys())[:20]
    gaps = analyze_skill_gaps(resume_skills, role_skills, market_skills)
    if not gaps:
        return "No significant skill gaps detected."
    top = [f"{g.skill} (priority {g.priority}, demand: {g.market_demand})" for g in gaps[:5]]
    return f"Top skill gaps: {'; '.join(top)}"


async def generate_response_node(state: ChatState) -> dict:
    """Generate a conversational response using LLM with tool context."""
    message = state.get("message", "")
    context = state.get("context", {})
    tool_results = context.get("tool_results", {})
    intent = context.get("intent", "general_chat")

    # Build minimal context for the LLM
    context_parts = []
    for tool_name, result in tool_results.items():
        context_parts.append(f"[{tool_name}]: {result}")

    system_prompt = (
        "You are CareerCopilot, an AI career assistant. "
        "Be concise, helpful, and actionable. "
        "Use the provided context to answer the user's question."
    )

    if context_parts:
        system_prompt += f"\n\nContext:\n{'  '.join(context_parts)}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    try:
        result = await _router.complete(
            messages=messages,
            category=TaskCategory.CHAT,
        )
        response = str(result)
    except Exception as exc:
        logger.error("LLM response generation failed: %s", exc)
        raise RuntimeError(f"Failed to generate chat response: {exc}") from exc

    messages_history = list(state.get("messages", []))
    messages_history.append({"role": "user", "content": message})
    messages_history.append({"role": "assistant", "content": response})

    return {"response": response, "messages": messages_history}


async def error_node(state: ChatState) -> dict:
    """Handle pipeline errors."""
    logger.error("Chat pipeline failed for conversation=%s", state.get("conversation_id"))
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": "An error occurred. Please try again."})
    return {"response": "An error occurred.", "messages": messages}


# ── Routing ────────────────────────────────────────────────────────────────────


def route_after_classify(state: ChatState) -> Literal["retrieve_context", "error_node"]:
    """Branch based on whether intent was classified."""
    intent = state.get("context", {}).get("intent")
    if not intent:
        return "error_node"
    return "retrieve_context"


# ── Graph ──────────────────────────────────────────────────────────────────────


def build_chat_graph() -> StateGraph:
    """Construct the chat assistant workflow."""
    graph = StateGraph(ChatState)

    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("retrieve_context", retrieve_context_node)
    graph.add_node("select_tools", select_tools_node)
    graph.add_node("execute_tools", execute_tools_node)
    graph.add_node("generate_response", generate_response_node)
    graph.add_node("error_node", error_node)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        {"retrieve_context": "retrieve_context", "error_node": "error_node"},
    )
    graph.add_edge("retrieve_context", "select_tools")
    graph.add_edge("select_tools", "execute_tools")
    graph.add_edge("execute_tools", "generate_response")
    graph.add_edge("generate_response", END)
    graph.add_edge("error_node", END)

    return graph


# Compiled graph instance
chat_pipeline = build_chat_graph().compile()
