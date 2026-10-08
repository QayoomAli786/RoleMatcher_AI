"""Interview session must store per-question evaluations for the final review."""

import asyncio
import uuid

from backend.api import interview as itq
from backend.core.schemas import UserProfile

_QUESTIONS_REPLY = "\n".join(f"[technical] [medium] Sample question {i + 1}?" for i in range(15))

_EVAL_REPLY = (
    "SCORE: 8\n"
    "STRENGTHS:\n"
    "- clear structure\n"
    "- good example\n"
    "IMPROVEMENTS:\n"
    "- add metrics\n"
    "MODEL ANSWER:\n"
    "A strong answer covers context, action and result."
)


def _stub_complete(questions_reply, eval_reply):
    async def complete(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        if "Generate exactly 15" in prompt:
            return questions_reply
        return eval_reply
    return complete


async def _run():
    user = UserProfile(email="test@example.com", name="Tester")
    created = await itq.start_interview(itq._StartBody(job_role="tester"), user)
    assert created["total_questions"] == 15, created
    sid = uuid.UUID(created["session_id"])

    resp = await itq.submit_answer(
        sid, itq._AnswerBody(question_index=0, answer="I would carefully analyze the problem first."), user
    )
    assert resp["score"] == 8, resp
    assert resp["model_answer"], resp

    got = await itq.get_interview(sid, user)
    evs = got["evaluations"]
    assert len(evs) == 15, f"expected 15 slots, got {len(evs)}"
    assert evs[0] is not None and evs[0]["score"] == 8
    assert "clear structure" in evs[0]["strengths"]
    assert evs[0]["model_answer"], "model answer must be stored"
    assert all(e is None for e in evs[1:]), "unanswered slots stay empty"

    # Short junk answers still store a zero-score evaluation.
    await itq.submit_answer(sid, itq._AnswerBody(question_index=1, answer="idk"), user)
    got2 = await itq.get_interview(sid, user)
    assert got2["evaluations"][1] is not None
    assert got2["evaluations"][1]["score"] == 0


def demo():
    original = itq._router.complete
    itq._router.complete = _stub_complete(_QUESTIONS_REPLY, _EVAL_REPLY)
    try:
        asyncio.run(_run())
    finally:
        itq._router.complete = original
    print("OK")


if __name__ == "__main__":
    demo()
