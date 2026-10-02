"""Regression check: the parsed model answer must keep its markdown structure."""

from backend.api.interview import _parse_evaluation

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


if __name__ == "__main__":
    demo()