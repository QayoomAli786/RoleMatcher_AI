"""LangGraph StateGraph for interview preparation and coaching.

Workflow:
    generate_questions -> present_question -> evaluate_answer ->
    provide_feedback -> next_question

Supports interruption/resumption via interrupt() for user input.
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend.core.schemas import InterviewCategory, InterviewQuestion, QuestionDifficulty
from backend.core.state import InterviewState
from backend.services.llm_service import ModelRouter, TaskCategory

logger = logging.getLogger(__name__)

_router = ModelRouter()


# ── Nodes ──────────────────────────────────────────────────────────────────────


async def generate_questions_node(state: InterviewState) -> dict:
    """Generate a set of interview questions based on resume and job info."""
    job_info = state.get("job_info", {})
    profile = state.get("resume_profile", {})

    role = job_info.get("title", "software engineer")
    skills = [s.get("name", "") for s in profile.get("skills", []) if isinstance(s, dict)][:10]

    prompt = (
        f"Generate 8 interview questions for a {role} position.\n"
        f"Candidate skills: {', '.join(skills)}\n\n"
        "Include a mix of:\n"
        "- 3 technical questions (medium difficulty)\n"
        "- 2 behavioral questions\n"
        "- 2 system design questions (hard)\n"
        "- 1 resume-based question\n\n"
        "Return each question as: [CATEGORY] [DIFFICULTY] Question text"
    )

    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": prompt}],
            category=TaskCategory.CHAT,
        )

        questions = []
        raw_lines = str(result).strip().split("\n")
        for line in raw_lines:
            line = line.strip()
            if not line or not line.startswith("["):
                continue

            category = InterviewCategory.technical
            difficulty = QuestionDifficulty.medium
            text = line

            if "[technical]" in line.lower():
                category = InterviewCategory.technical
                text = line.split("]", 2)[-1].strip() if line.count("[") >= 2 else line.split("]", 1)[-1].strip()
            elif "[behavioral]" in line.lower():
                category = InterviewCategory.behavioral
                text = line.split("]", 2)[-1].strip() if line.count("[") >= 2 else line.split("]", 1)[-1].strip()
            elif "[system" in line.lower():
                category = InterviewCategory.system_design
                text = line.split("]", 2)[-1].strip() if line.count("[") >= 2 else line.split("]", 1)[-1].strip()
            elif "[resume]" in line.lower():
                category = InterviewCategory.resume

            if "[easy]" in line.lower():
                difficulty = QuestionDifficulty.easy
            elif "[hard]" in line.lower():
                difficulty = QuestionDifficulty.hard

            if text:
                questions.append(
                    InterviewQuestion(
                        question=text,
                        category=category,
                        difficulty=difficulty,
                    ).model_dump()
                )

        if not questions:
            questions = [
                InterviewQuestion(
                    question="Tell me about a challenging project you worked on and how you handled it.",
                    category=InterviewCategory.behavioral,
                ).model_dump(),
            ]

        return {"questions": questions, "current_question_index": 0}

    except Exception as exc:
        logger.error("Question generation failed: %s", exc)
        raise RuntimeError(f"Failed to generate interview questions: {exc}") from exc


async def present_question_node(state: InterviewState) -> dict:
    """Present the current question and wait for user input via interrupt."""
    questions = state.get("questions", [])
    idx = state.get("current_question_index", 0)

    if idx >= len(questions):
        return {}

    question = questions[idx]
    logger.info(
        "Presenting question %d/%d: %s",
        idx + 1,
        len(questions),
        question.get("question", "")[:80],
    )

    # Use interrupt to pause and wait for user's answer
    user_answer = interrupt(
        {
            "question_number": idx + 1,
            "total_questions": len(questions),
            "question": question,
        }
    )

    return {"user_answer": str(user_answer)}


async def evaluate_answer_node(state: InterviewState) -> dict:
    """Evaluate the user's answer using LLM."""
    questions = state.get("questions", [])
    idx = state.get("current_question_index", 0)
    question = questions[idx] if idx < len(questions) else {}
    user_answer = state.get("user_answer", "")

    if not user_answer.strip():
        return {"evaluation": {"score": 0, "feedback": "No answer provided."}}

    prompt = (
        f"Interview Question: {question.get('question', 'N/A')}\n"
        f"Category: {question.get('category', 'N/A')}\n"
        f"Difficulty: {question.get('difficulty', 'N/A')}\n\n"
        f"Candidate Answer:\n{user_answer}\n\n"
        "Evaluate this answer. Provide:\n"
        "1. A score from 1-10\n"
        "2. What was good about the answer\n"
        "3. What could be improved\n"
        "4. A model answer outline"
    )

    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": prompt}],
            category=TaskCategory.CHAT,
        )

        evaluation = {
            "feedback": str(result),
            "question": question.get("question", ""),
            "user_answer": user_answer,
        }

        return {"evaluation": evaluation}

    except Exception as exc:
        logger.error("Answer evaluation failed: %s", exc)
        raise RuntimeError(f"Failed to evaluate answer: {exc}") from exc


async def provide_feedback_node(state: InterviewState) -> dict:
    """Provide feedback to the user and update message history."""
    evaluation = state.get("evaluation", {})
    feedback = evaluation.get("feedback", "No feedback available.")
    messages = list(state.get("messages", []))

    messages.append({"role": "assistant", "content": feedback})

    return {"messages": messages}


async def next_question_node(state: InterviewState) -> dict:
    """Advance to the next question or signal completion."""
    idx = state.get("current_question_index", 0)
    questions = state.get("questions", [])
    new_index = idx + 1

    if new_index >= len(questions):
        messages = list(state.get("messages", []))
        messages.append({
            "role": "assistant",
            "content": f"Interview session complete! You answered {len(questions)} questions. "
                       "Great practice session!",
        })
        return {"current_question_index": new_index, "messages": messages}

    return {"current_question_index": new_index}


async def error_node(state: InterviewState) -> dict:
    """Handle pipeline errors."""
    logger.error("Interview pipeline failed for session=%s", state.get("session_id"))
    return {}


# ── Routing ────────────────────────────────────────────────────────────────────


def route_after_present(state: InterviewState) -> Literal["evaluate_answer", "error_node"]:
    """Branch based on whether we have a question to evaluate."""
    questions = state.get("questions", [])
    idx = state.get("current_question_index", 0)
    if idx >= len(questions) or not state.get("user_answer"):
        return "error_node"
    return "evaluate_answer"


def route_after_next(state: InterviewState) -> Literal["present_question", "END"]:
    """Loop back for next question or end the session."""
    idx = state.get("current_question_index", 0)
    questions = state.get("questions", [])
    if idx < len(questions):
        return "present_question"
    return "END"


# ── Graph ──────────────────────────────────────────────────────────────────────


def build_interview_graph() -> StateGraph:
    """Construct the interview preparation workflow."""
    graph = StateGraph(InterviewState)

    graph.add_node("generate_questions", generate_questions_node)
    graph.add_node("present_question", present_question_node)
    graph.add_node("evaluate_answer", evaluate_answer_node)
    graph.add_node("provide_feedback", provide_feedback_node)
    graph.add_node("next_question", next_question_node)
    graph.add_node("error_node", error_node)

    graph.add_edge(START, "generate_questions")
    graph.add_edge("generate_questions", "present_question")
    graph.add_conditional_edges(
        "present_question",
        route_after_present,
        {"evaluate_answer": "evaluate_answer", "error_node": "error_node"},
    )
    graph.add_edge("evaluate_answer", "provide_feedback")
    graph.add_edge("provide_feedback", "next_question")
    graph.add_conditional_edges(
        "next_question",
        route_after_next,
        {"present_question": "present_question", "END": END},
    )
    graph.add_edge("error_node", END)

    return graph


# Compiled graph instance
interview_pipeline = build_interview_graph().compile()
