"""Interview endpoints — setup, question generation, answer evaluation, and scoring.

Sessions are stored in-memory. The flow is:
    1. POST /api/interviews            -> create session + generate 15 questions
    2. POST /api/interviews/{id}/answer -> evaluate one answer, store score
    3. GET  /api/interviews/{id}        -> fetch session state (scores, progress)
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.schemas import UserProfile
from backend.core.store import _interviews, get_resume, get_generic, store_generic
from backend.services.llm_service import ModelRouter, TaskCategory
from backend.security.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interviews")

_router = ModelRouter()


class _StartBody(BaseModel):
    resume_id: str | None = None
    job_role: str | None = None
    job_description: str | None = None
    interview_type: str = "mixed"  # technical | behavioral | mixed


class _AnswerBody(BaseModel):
    question_index: int
    answer: str


@router.post("", status_code=201)
async def start_interview(body: _StartBody, user: UserProfile = Depends(get_current_user)):
    """Create an interview session and generate questions."""
    role = (body.job_role or "").strip() or "software engineer"
    interview_type = body.interview_type or "mixed"
    resume_id = uuid.UUID(body.resume_id) if body.resume_id else None

    resume_profile = {}
    if resume_id:
        resume = get_resume(resume_id)
        if resume is not None:
            resume_profile = resume.parsed_profile or {}

    questions = await _generate_questions(
        role=role,
        job_description=body.job_description or "",
        interview_type=interview_type,
        resume_profile=resume_profile,
    )

    session_id = uuid.uuid4()
    store_generic(_interviews, session_id, {
        "user_id": user.id,
        "session_id": str(session_id),
        "job_role": role,
        "interview_type": interview_type,
        "job_description": body.job_description or "",
        "resume_id": str(resume_id) if resume_id else None,
        "questions": questions,
        "answers": [],
        "scores": [],
        "total_questions": len(questions),
        "status": "in_progress",
        "created_at": str(uuid.uuid4()),
    })

    return {
        "session_id": str(session_id),
        "total_questions": len(questions),
        "questions": questions,
    }


@router.post("/{interview_id}/answer")
async def submit_answer(interview_id: uuid.UUID, body: _AnswerBody, user: UserProfile = Depends(get_current_user)):
    """Evaluate the user's answer and store the result."""
    session = get_generic(_interviews, interview_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Interview session not found")

    questions = session.get("questions", [])
    idx = body.question_index
    if idx < 0 or idx >= len(questions):
        raise HTTPException(status_code=400, detail="Invalid question index")

    question = questions[idx]
    answer = body.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer cannot be empty")

    evaluation = await _evaluate_answer(question, answer)
    score = evaluation.get("score", 0)

    scores = list(session.get("scores", []))
    while len(scores) < len(questions):
        scores.append(None)
    scores[idx] = score

    session["scores"] = scores
    answers = list(session.get("answers", []))
    while len(answers) < len(questions):
        answers.append(None)
    answers[idx] = answer
    session["answers"] = answers

    # Determine if session is complete
    completed = all(s is not None for s in scores)
    if completed:
        session["status"] = "completed"

    store_generic(_interviews, interview_id, session)

    return {
        "session_id": str(interview_id),
        "question_index": idx,
        "score": score,
        "feedback": evaluation.get("feedback", ""),
        "strengths": evaluation.get("strengths", []),
        "improvements": evaluation.get("improvements", []),
        "model_answer": evaluation.get("model_answer", ""),
        "total_questions": len(questions),
        "completed": completed,
    }


@router.get("/{interview_id}")
async def get_interview(interview_id: uuid.UUID, user: UserProfile = Depends(get_current_user)):
    session = get_generic(_interviews, interview_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Interview session not found")

    scores = [s for s in session.get("scores", []) if s is not None]
    overall = round(sum(scores) / len(scores), 1) if scores else 0

    return {
        "session_id": str(interview_id),
        "job_role": session.get("job_role", ""),
        "interview_type": session.get("interview_type", ""),
        "total_questions": session.get("total_questions", 0),
        "status": session.get("status", ""),
        "questions": session.get("questions", []),
        "scores": session.get("scores", []),
        "answers": session.get("answers", []),
        "overall_score": overall,
        "completed": session.get("status") == "completed",
    }


@router.get("/{interview_id}/feedback")
async def get_feedback(interview_id: uuid.UUID, user: UserProfile = Depends(get_current_user)):
    session = get_generic(_interviews, interview_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Interview session not found")

    scores = [s for s in session.get("scores", []) if s is not None]
    overall = round(sum(scores) / len(scores), 1) if scores else 0

    return {
        "session_id": str(interview_id),
        "overall_score": overall,
        "scores": session.get("scores", []),
        "feedback": session.get("feedback_summary", "Session in progress"),
    }


async def _generate_questions(
    role: str,
    job_description: str,
    interview_type: str,
    resume_profile: dict,
) -> list[dict]:
    """Generate 15 interview questions using the LLM."""
    skills = [s.get("name", "") for s in resume_profile.get("skills", []) if isinstance(s, dict)][:15]
    experience = resume_profile.get("experience", [])

    if interview_type == "technical":
        type_prompt = (
            "10 technical questions (medium-hard difficulty)\n"
            "3 system design questions (hard)\n"
            "2 behavioral questions\n"
        )
    elif interview_type == "behavioral":
        type_prompt = (
            "12 behavioral questions (medium difficulty)\n"
            "3 resume-based questions\n"
        )
    else:  # mixed
        type_prompt = (
            "5 technical questions (medium difficulty)\n"
            "4 behavioral questions\n"
            "3 system design questions (hard)\n"
            "3 resume-based questions\n"
        )

    prompt = (
        f"Generate exactly 15 interview questions for a {role} position.\n\n"
        f"Candidate skills: {', '.join(skills) if skills else 'not specified'}\n"
        f"Interview type: {interview_type}\n\n"
        f"Include:\n{type_prompt}\n\n"
        f"Job description:\n{job_description[:2000] if job_description else 'N/A'}\n\n"
        "Return each question on a NEW line, formatted exactly as:\n"
        "[CATEGORY] [DIFFICULTY] Question text\n"
        "where CATEGORY is one of: technical, behavioral, system_design, resume\n"
        "and DIFFICULTY is one of: easy, medium, hard\n"
        "Do NOT number the questions. Do NOT include any extra text or headers."
    )

    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": prompt}],
            category=TaskCategory.CHAT,
        )
        questions = _parse_questions(str(result))
        if len(questions) < 15:
            logger.warning(
                "LLM returned only %d questions, filling the rest (raw response: %.200s)",
                len(questions),
                str(result).replace("\n", " "),
            )
        # If we got too few, pad with fallbacks
        while len(questions) < 15:
            questions.append(_fallback_question(role, len(questions)))
        return questions[:15]
    except Exception as exc:
        logger.error("Question generation failed: %s", exc)
        return [_fallback_question(role, i) for i in range(15)]


def _parse_questions(text: str) -> list[dict]:
    """Parse question lines into dicts.

    Accepts several formats:
      - ``[technical] [easy] question text``
      - ``1. [technical] easy: question text``
      - ``- **Behavioral (Medium):** question text``
      - ``1. Tell me about...`` (category/difficulty defaulted)
    """
    questions: list[dict] = []
    seen: set[str] = set()
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        category = "technical"
        difficulty = "medium"

        lower = line.lower()
        if "[behavioral]" in lower or "behavioral" in lower:
            category = "behavioral"
        elif "[system" in lower or "system design" in lower:
            category = "system_design"
        elif "[resume]" in lower or "resume-based" in lower or "on your resume" in lower:
            category = "resume"

        if "[easy]" in lower or "easy" in lower:
            difficulty = "easy"
        elif "[hard]" in lower or "hard" in lower:
            difficulty = "hard"

        # Strip leading list markers / bullets / numbering
        content = re.sub(r"^\s*(?:\d+[.)]|[-*•]|\*+|#+)\s*", "", line).strip()

        # Remove bracket tags like [technical] [easy]
        content = re.sub(r"\[[^\]]*\]", "", content).strip()

        # Remove bold markers
        content = re.sub(r"\*\*(.+?)\*\*", r"\1", content)
        content = re.sub(r"(?<![\w*])\*(?![\w*])(.+?)(?<![\w*])\*(?![\w*])", r"\1", content)

        # Trim leading "Category: " / "Category -" / difficulty prefixes
        content = re.sub(
            r"^(behavioral|technical|system[ _-]?design|resume)\s*(?:\([^)]*\))?[:\-]+\s*",
            "",
            content,
            flags=re.I,
        )
        content = re.sub(
            r"^(easy|medium|hard)\s*[:\-]+\s*",
            "",
            content,
            flags=re.I,
        )
        content = content.strip(" :-.")

        if not content:
            continue

        # De-duplicate near-identical questions
        key = content.lower().strip()
        if key in seen:
            continue
        seen.add(key)

        questions.append({
            "question": content,
            "category": category,
            "difficulty": difficulty,
        })
    return questions


def _fallback_question(role: str, index: int) -> dict:
    """Provide a generic fallback question."""
    fallbacks = [
        ("Tell me about a challenging project you worked on and how you overcame the difficulties.", "behavioral", "medium"),
        ("Describe your experience with the main technologies used for this role.", "technical", "medium"),
        ("How do you stay updated with the latest trends in your field?", "behavioral", "easy"),
        ("Walk me through how you would design a scalable system from scratch.", "system_design", "hard"),
        ("Why do you want to work in this role and what makes you a good fit?", "behavioral", "medium"),
        ("Explain a technical concept in your domain as if I were a junior developer.", "technical", "medium"),
        ("Tell me about a time you had to deal with a difficult team member.", "behavioral", "medium"),
        ("Describe a project on your resume and your specific contribution to it.", "resume", "medium"),
        ("What are the most important metrics you track in your work and why?", "technical", "hard"),
        ("How would you prioritize tasks when working on multiple projects simultaneously?", "behavioral", "easy"),
        ("Design a system that handles high traffic with reliability.", "system_design", "hard"),
        ("What was the most difficult bug or issue you ever fixed and how did you solve it?", "technical", "hard"),
        ("Where do you see yourself in five years and how does this role fit into that plan?", "behavioral", "easy"),
        ("Tell me about a time you led a project to success. What was your approach?", "resume", "medium"),
        ("Describe your process for learning a new technology quickly.", "technical", "medium"),
    ]
    text, cat, diff = fallbacks[index % len(fallbacks)]
    return {
        "question": text,
        "category": cat,
        "difficulty": diff,
    }


async def _evaluate_answer(question: dict, answer: str) -> dict:
    """Evaluate the user's answer using the LLM."""
    prompt = (
        f"Interview Question: {question.get('question', 'N/A')}\n"
        f"Category: {question.get('category', 'N/A')}\n"
        f"Difficulty: {question.get('difficulty', 'N/A')}\n\n"
        f"Candidate Answer:\n{answer}\n\n"
        "Evaluate this answer on a scale of 1-10. Provide a structured response with:\n"
        "1. Score (integer 1-10)\n"
        "2. Strengths: 2-3 bullet points of what was good\n"
        "3. Improvements: 2-3 bullet points of what could be better\n"
        "4. Model Answer: A well-structured, detailed answer using markdown formatting\n\n"
        "Format:\n"
        "SCORE: <number>\n"
        "STRENGTHS:\n- ...\n- ...\n"
        "IMPROVEMENTS:\n- ...\n- ...\n"
        "MODEL ANSWER:\n<use markdown with headings, bold, bullet points, and numbered lists as needed>"
    )

    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": prompt}],
            category=TaskCategory.CHAT,
        )
        return _parse_evaluation(str(result))
    except Exception as exc:
        logger.warning("Answer evaluation failed: %s", exc)
        return {
            "score": 5,
            "feedback": "Evaluation temporarily unavailable.",
            "strengths": [],
            "improvements": [],
            "model_answer": "",
        }


def _parse_evaluation(text: str) -> dict:
    """Parse the structured evaluation output."""
    lines = text.split("\n")
    score = 5
    strengths: list[str] = []
    improvements: list[str] = []
    model_answer = ""
    section = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("SCORE:"):
            try:
                score = int(line.split(":", 1)[1].strip())
                score = max(1, min(10, score))
            except ValueError:
                score = 5
            section = None
        elif line.upper().startswith("STRENGTHS") or line.upper().startswith("STRENGTH:"):
            section = "strengths"
        elif line.upper().startswith("IMPROVEMENTS") or line.upper().startswith("IMPROVEMENT:"):
            section = "improvements"
        elif line.upper().startswith("MODEL ANSWER") or line.upper().startswith("MODEL:"):
            section = "model_answer"
        elif section == "strengths" and line.startswith("-"):
            strengths.append(line.lstrip("- ").strip())
        elif section == "improvements" and line.startswith("-"):
            improvements.append(line.lstrip("- ").strip())
        elif section == "model_answer":
            model_answer += (" " if model_answer else "") + line

    feedback = (
        f"Score: {score}/10\n"
        f"Strengths: {', '.join(strengths) if strengths else 'Good coverage of the topic'}\n"
        f"Areas to improve: {', '.join(improvements) if improvements else 'Keep practicing'}"
    )

    return {
        "score": score,
        "feedback": feedback,
        "strengths": strengths,
        "improvements": improvements,
        "model_answer": model_answer,
    }