"""Career input gate: gibberish must be rejected before any roadmap is built.

Two layers: a cheap deterministic shape gate, then an LLM yes/no judgment.
"""

import asyncio

from backend.api import career


def test_shape_gate():
    for junk in ("", "   ", "a", "123", "!!!", "x1", "$$$", "12345 67890", "aaaa"):
        assert not career._is_valid_profession(junk), f"junk accepted: {junk!r}"
    for good in ("Cardiologist", "Software Engineer", "MBBS doctor", "RN",
                 "MD", "web3 developer", "nurse", "Data Scientist", "Dr"):
        assert career._is_valid_profession(good), f"valid rejected: {good!r}"


def _stub_router(reply=None, error=False):
    async def complete(**kwargs):
        if error:
            raise RuntimeError("llm down")
        assert kwargs["temperature"] == 0.0 and kwargs["max_tokens"] == 5
        return reply
    return complete


def test_llm_judgment():
    original = career._router.complete
    try:
        career._router.complete = _stub_router(reply="NO")
        assert not asyncio.run(career._profession_looks_real("asdf"))
        assert not asyncio.run(career._profession_looks_real("hello world"))

        career._router.complete = _stub_router(reply="YES")
        assert asyncio.run(career._profession_looks_real("Cardiologist"))

        career._router.complete = _stub_router(error=True)
        assert asyncio.run(career._profession_looks_real("nurse")), "must fail open"
    finally:
        career._router.complete = original


def test_message():
    assert "valid profession" in career._INVALID_PROFESSION_MSG


def demo():
    test_shape_gate()
    test_llm_judgment()
    test_message()
    print("OK")


if __name__ == "__main__":
    demo()
