"""Web search via DuckDuckGo (ddgs) — exposed to the LLM as a tool.

``web_search`` never raises: search failures degrade to an error payload the
LLM can react to, so roadmap generation never dies because of the network.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# OpenAI-format tool schema handed to bind_tools().
WEB_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web with DuckDuckGo. Returns a JSON list of results, "
            "each with title, url and snippet. Use it to research current, "
            "role-specific facts and learning resources before answering."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
            },
            "required": ["query"],
        },
    },
}


async def web_search(query: str, max_results: int = 5) -> str:
    """Run one DuckDuckGo search. Always returns a JSON string; never raises."""
    query = (query or "").strip()
    if not query:
        return json.dumps({"error": "empty query"})

    def _run() -> list[dict]:
        from ddgs import DDGS

        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))

    try:
        # ddgs is synchronous and blocks on network — keep the event loop free.
        results = await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning("DuckDuckGo search failed for %r: %s", query, exc)
        return json.dumps({"error": "search unavailable", "query": query})

    items = [
        {
            "title": r.get("title", ""),
            "url": r.get("href") or r.get("url") or "",
            "snippet": r.get("body", ""),
        }
        for r in results
        if isinstance(r, dict)
    ]
    logger.info("web_search(%r) -> %d results", query, len(items))
    return json.dumps(items, ensure_ascii=False)
