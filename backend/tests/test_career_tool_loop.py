"""Tool loop: the model must be able to search the web before answering."""

import asyncio
import json

from backend.services.llm_service import ModelRouter, TaskCategory
from backend.services.web_search import WEB_SEARCH_SCHEMA, web_search


class _Resp:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeChat:
    """Scripted chat model: pops one canned response per invoke, records convos."""

    def __init__(self, script):
        self._script = list(script)
        self.bound_tools = None
        self.seen = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, convo):
        self.seen.append([m for m in convo])
        return self._script.pop(0)


def _run(coro):
    return asyncio.run(coro)


def test_tool_loop_executes_search_and_returns_json() -> None:
    router = ModelRouter()
    fake = _FakeChat([
        _Resp(tool_calls=[{"name": "web_search", "args": {"query": "doctor path"}, "id": "c1"}]),
        _Resp(content='{"roadmap_steps": [{"step": 1}]}'),
    ])
    router._build_chat_model = lambda *a, **k: fake

    captured = {}

    async def fake_search(query: str) -> str:
        captured["query"] = query
        return json.dumps([{"title": "t", "url": "u", "snippet": "s"}])

    out = _run(router.complete_with_tools(
        messages=[{"role": "user", "content": "make a plan"}],
        tools=[WEB_SEARCH_SCHEMA],
        handlers={"web_search": fake_search},
        category=TaskCategory.CAREER_STRATEGY,
    ))

    assert captured["query"] == "doctor path", captured
    assert out == '{"roadmap_steps": [{"step": 1}]}', out
    assert fake.bound_tools == [WEB_SEARCH_SCHEMA], "tool schema not bound"
    # Second invoke must carry the tool result back to the model
    tool_msgs = [m for m in fake.seen[1]
                 if isinstance(m, dict) and m.get("role") == "tool"]
    assert len(tool_msgs) == 1 and "title" in tool_msgs[0]["content"], tool_msgs


def test_tool_loop_forces_answer_after_max_rounds() -> None:
    router = ModelRouter()
    call = lambda: _Resp(tool_calls=[{"name": "web_search", "args": {"query": "q"}, "id": "c"}])
    fake = _FakeChat([call(), call(), call(), call(), _Resp(content="final answer")])
    router._build_chat_model = lambda *a, **k: fake

    async def noop_search(query: str) -> str:
        return "[]"

    out = _run(router.complete_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=[WEB_SEARCH_SCHEMA],
        handlers={"web_search": noop_search},
        max_rounds=4,
    ))
    assert out == "final answer", out
    assert len(fake.seen) == 5, len(fake.seen)


def test_web_search_never_raises() -> None:
    out = _run(web_search(""))
    assert json.loads(out) == {"error": "empty query"}, out


def demo():
    test_tool_loop_executes_search_and_returns_json()
    test_tool_loop_forces_answer_after_max_rounds()
    test_web_search_never_raises()
    print("OK")


if __name__ == "__main__":
    demo()
