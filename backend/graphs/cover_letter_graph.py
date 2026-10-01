"""LangGraph StateGraph for cover letter generation.

Workflow:
    analyze_resume -> analyze_job -> generate_cover_letter -> refine_tone

Takes resume profile + job description and produces a tailored cover letter.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from backend.core.state import CoverLetterState
from backend.services.llm_service import ModelRouter, TaskCategory

logger = logging.getLogger(__name__)

_router = ModelRouter()


def _fallback_cover_letter(state: CoverLetterState) -> str:
    """Deterministic cover letter template used when the LLM is unavailable."""
    profile = state.get("resume_profile", {})
    job_title = state.get("job_title", "the position")
    company = state.get("company_name", "your company")

    skills = [s.get("name", "") for s in profile.get("skills", []) if isinstance(s, dict)][:8]
    highlights = profile.get("_experience_highlights", [])
    summary = profile.get("_summary", "")

    body = (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my strong interest in the {job_title} position at {company}. "
    )
    if summary:
        body += f"With my background, I bring a proven ability to deliver results. {summary.strip()} "
    else:
        body += "I bring a track record of delivering results and a genuine passion for this work. "

    if highlights:
        body += "\n\nThroughout my career, I have:\n"
        for h in highlights[:3]:
            body += f"- {h}\n"

    if skills:
        body += f"\nMy key strengths include {', '.join(skills)}. "
        body += "I apply these skills to solve real problems and drive measurable outcomes for the team."

    body += (
        "\n\nI am particularly drawn to this role because it aligns with my professional goals "
        "and I am confident I can contribute meaningfully from day one. "
        "I would welcome the opportunity to discuss how my experience can benefit your team "
        f"in an interview.\n\n"
        f"Thank you for your time and consideration.\n\n"
        f"Sincerely,\n"
        f"[Your Name]"
    )
    return body


# ── Nodes ──────────────────────────────────────────────────────────────────────


async def analyze_resume_node(state: CoverLetterState) -> dict:
    """Extract key strengths, skills, and experiences from the resume profile."""
    profile = state.get("resume_profile", {})
    resume_text = state.get("resume_text", "")

    skills = [s.get("name", "") for s in profile.get("skills", []) if isinstance(s, dict)][:15]
    experience = profile.get("experience", [])
    summary = profile.get("summary", "")

    experience_highlights = []
    for exp in experience[:3]:
        if isinstance(exp, dict):
            highlight = f"{exp.get('title', '')} at {exp.get('company', '')}"
            if exp.get("description"):
                highlight += f" — {exp['description'][:150]}"
            experience_highlights.append(highlight)

    state_update = {
        "resume_profile": {
            **profile,
            "_analyzed_skills": skills,
            "_experience_highlights": experience_highlights,
            "_summary": summary,
        }
    }
    return state_update


async def analyze_job_node(state: CoverLetterState) -> dict:
    """Analyze the job description to identify key requirements and keywords."""
    job_desc = state.get("job_description", "")
    job_title = state.get("job_title", "the position")
    company = state.get("company_name", "your company")

    if not job_desc:
        return {}

    prompt = (
        f"Analyze this job description for a {job_title} role at {company}.\n\n"
        f"JOB DESCRIPTION:\n{job_desc[:2000]}\n\n"
        "Extract and return as a concise list:\n"
        "1. Top 5 required skills/technologies\n"
        "2. Key responsibilities (2-3 lines)\n"
        "3. Ideal candidate qualities\n"
        "4. Company culture signals\n"
        "Keep it brief — max 200 words."
    )

    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": prompt}],
            category=TaskCategory.EXTRACTION,
        )

        profile = state.get("resume_profile", {})
        profile["_job_analysis"] = str(result)
        return {"resume_profile": profile}
    except Exception as exc:
        logger.warning("Job analysis failed: %s", exc)
        return {}


async def generate_cover_letter_node(state: CoverLetterState) -> dict:
    """Generate a tailored cover letter using resume + job analysis."""
    profile = state.get("resume_profile", {})
    job_title = state.get("job_title", "the position")
    company = state.get("company_name", "your company")
    job_desc = state.get("job_description", "")
    tone = state.get("tone", "professional")

    skills = profile.get("_analyzed_skills", [])
    highlights = profile.get("_experience_highlights", [])
    summary = profile.get("_summary", "")
    job_analysis = profile.get("_job_analysis", "")

    tone_instructions = {
        "professional": "Write in a polished, professional tone. Be concise and direct.",
        "enthusiastic": "Write with genuine enthusiasm and energy. Show excitement about the role.",
        "confident": "Write with strong confidence. Highlight achievements assertively.",
        "creative": "Write with a creative, memorable style that stands out from typical cover letters.",
    }

    prompt = (
        f"Write a cover letter for a {job_title} position at {company}.\n\n"
        f"TONE: {tone_instructions.get(tone, tone_instructions['professional'])}\n\n"
        f"CANDIDATE SUMMARY:\n{summary[:500]}\n\n"
        f"KEY SKILLS: {', '.join(skills[:10])}\n\n"
        f"EXPERIENCE HIGHLIGHTS:\n"
    )

    for h in highlights[:3]:
        prompt += f"- {h}\n"

    if job_analysis:
        prompt += f"\nJOB ANALYSIS:\n{job_analysis}\n"

    if job_desc:
        prompt += f"\nJOB DESCRIPTION (excerpt):\n{job_desc[:1000]}\n"

    prompt += (
        "\n---\n"
        "Write a compelling cover letter (300-400 words) that:\n"
        "1. Opens with a strong hook connecting the candidate to the role\n"
        "2. Highlights 2-3 most relevant experiences with specific results\n"
        "3. Shows understanding of the company and role\n"
        "4. Closes with a clear call to action\n\n"
        "Format: plain text, paragraph style. No markdown headers."
    )

    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": prompt}],
            category=TaskCategory.RESUME_REWRITE,
        )

        return {"cover_letter": str(result), "error": None}
    except Exception as exc:
        logger.error("Cover letter generation failed: %s", exc)
        raise RuntimeError(f"Failed to generate cover letter: {exc}") from exc


async def refine_tone_node(state: CoverLetterState) -> dict:
    """Final quality check — ensure the cover letter is polished and error-free."""
    cover_letter = state.get("cover_letter", "")

    if not cover_letter or len(cover_letter) < 100:
        return {}

    prompt = (
        "Review and polish this cover letter. Fix any grammar, spelling, or tone issues. "
        "Improve flow and impact. Keep the same meaning and structure.\n\n"
        f"COVER LETTER:\n{cover_letter}\n\n"
        "Return the polished version only — no commentary."
    )

    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": prompt}],
            category=TaskCategory.RESUME_REWRITE,
        )

        refined = str(result).strip()
        # Use refined version only if it's substantive
        if len(refined) > len(cover_letter) * 0.5:
            return {"cover_letter": refined}
        return {}
    except Exception as exc:
        logger.warning("Tone refinement failed: %s", exc)
        return {}


async def error_node(state: CoverLetterState) -> dict:
    """Handle pipeline errors."""
    logger.error("Cover letter pipeline failed for user=%s", state.get("user_id"))
    return {"error": "Cover letter generation failed. Please try again."}


# ── Graph ──────────────────────────────────────────────────────────────────────


def build_cover_letter_graph() -> StateGraph:
    """Construct the cover letter generation workflow."""
    graph = StateGraph(CoverLetterState)

    graph.add_node("analyze_resume", analyze_resume_node)
    graph.add_node("analyze_job", analyze_job_node)
    graph.add_node("generate_cover_letter", generate_cover_letter_node)
    graph.add_node("refine_tone", refine_tone_node)
    graph.add_node("error_node", error_node)

    graph.add_edge(START, "analyze_resume")
    graph.add_edge("analyze_resume", "analyze_job")
    graph.add_edge("analyze_job", "generate_cover_letter")
    graph.add_edge("generate_cover_letter", "refine_tone")
    graph.add_edge("refine_tone", END)
    graph.add_edge("error_node", END)

    return graph


# Compiled graph instance
cover_letter_pipeline = build_cover_letter_graph().compile()
