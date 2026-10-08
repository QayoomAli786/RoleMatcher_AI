"""Regression check: the parsed model answer must keep its markdown structure."""

import asyncio

from backend.api.interview import _evaluate_answer, _parse_evaluation

SAMPLE = """SCORE: 7
STRENGTHS:
- Clear structure
- Gave a concrete example
IMPROVEMENTS:
- Add measurable results
MODEL ANSWER:
**Situation:** I owned the payments rewrite.

- Led a 4-person team
- Cut p99 latency by 40%

1. Set the goal first
2. Measured weekly
"""


def demo():
    result = _parse_evaluation(SAMPLE)
    assert result["score"] == 7, result["score"]
    assert result["strengths"] == ["Clear structure", "Gave a concrete example"], result["strengths"]
    assert result["improvements"] == ["Add measurable results"], result["improvements"]

    ma = result["model_answer"]
    # Line breaks must survive, otherwise marked() renders the whole thing as
    # one paragraph and every bullet/heading collapses into a bold blob.
    assert "\n" in ma, f"newlines collapsed into one line: {ma!r}"
    assert ma.startswith("**Situation:**"), ma
    assert "\n- Led a 4-person team" in ma, ma
    assert "\n1. Set the goal first" in ma, ma
    print("OK")


def test_zero_score_survives_parse() -> None:
    """SCORE: 0 must parse as 0 — the old clamp forced a minimum of 1."""
    result = _parse_evaluation("SCORE: 0\nSTRENGTHS:\n- none\nIMPROVEMENTS:\n- none\n")
    assert result["score"] == 0, result["score"]


def test_junk_answer_scores_zero_without_llm() -> None:
    """Random/short text scores 0 immediately, no LLM call involved."""
    for junk in ("asdf", "lorem ipsum", "x y"):
        result = asyncio.run(_evaluate_answer({"question": "q", "category": "technical"}, junk))
        assert result["score"] == 0, (junk, result["score"])


if __name__ == "__main__":
    demo()
    test_zero_score_survives_parse()
    test_junk_answer_scores_zero_without_llm()
    print("All checks passed")