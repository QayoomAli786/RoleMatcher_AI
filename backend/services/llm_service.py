"""Centralized LLM service — LangChain-backed model routing, structured output, caching, cost tracking.

Uses LangChain chat models (Google Gemini, Groq, OpenAI, DeepSeek, Qwen) instead of
raw litellm calls. The public API (``ModelRouter.complete`` / ``stream`` /
``structured``) is unchanged, so every LangGraph node keeps working as-is.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from contextvars import ContextVar, Token
from enum import Enum
from typing import Any, AsyncIterator, TypeVar

from pydantic import BaseModel

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ── Per-request API key override ─────────────────────────────────────────────

_request_api_key: ContextVar[str] = ContextVar("request_api_key", default="")


def set_request_api_key(key: str) -> Token[str]:
    """Set the API key to use for the current request's LLM calls."""
    return _request_api_key.set(key)


def reset_request_api_key(token: Token[str]) -> None:
    """Restore the previous request API key context."""
    _request_api_key.reset(token)


def get_request_api_key() -> str:
    return _request_api_key.get()

# ── Per-request model override ───────────────────────────────────────────────

_request_model: ContextVar[str] = ContextVar("request_model", default="")


def set_request_model(model: str) -> Token[str]:
    """Set the model override to use for the current request's LLM calls."""
    return _request_model.set(model)


def reset_request_model(token: Token[str]) -> None:
    """Restore the previous request model context."""
    _request_model.reset(token)


def get_request_model() -> str:
    return _request_model.get()

# ── Cost estimates per 1 M tokens (USD) ─────────────────────────────────────

_COST_TABLE: dict[str, dict[str, float]] = {
    # Gemini
    "gemini/gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini/gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini/gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    # Groq
    "groq/llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "groq/llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "groq/mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
    # OpenAI
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "openai/gpt-4o": {"input": 2.50, "output": 10.0},
    "openai/gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "openai/gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    # DeepSeek
    "deepseek/deepseek-chat": {"input": 0.27, "output": 1.10},
    "deepseek/deepseek-reasoner": {"input": 0.55, "output": 2.19},
    # Qwen (via OpenAI-compatible API)
    "openai/qwen-turbo": {"input": 0.05, "output": 0.20},
    "openai/qwen-plus": {"input": 0.40, "output": 1.20},
    "openai/qwen-max": {"input": 1.60, "output": 6.40},
}


class TaskCategory(str, Enum):
    EXTRACTION = "extraction"
    CHAT = "chat"
    ATS_EXPLANATION = "ats_explanation"
    RESUME_REWRITE = "resume_rewrite"
    CAREER_STRATEGY = "career_strategy"


# Category → preferred model tier
_TASK_MODEL_MAP: dict[TaskCategory, str] = {
    TaskCategory.EXTRACTION: "fast",
    TaskCategory.CHAT: "fast",
    TaskCategory.ATS_EXPLANATION: "strong",
    TaskCategory.RESUME_REWRITE: "strong",
    TaskCategory.CAREER_STRATEGY: "fast",
}

# Provider prefixes that must go through an OpenAI-compatible endpoint
_OPENAI_COMPATIBLE: dict[str, str] = {
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

# Same-provider fallback candidates, most capable first
_PROVIDER_MODELS: dict[str, list[str]] = {
    "gemini": [
        "gemini/gemini-2.5-pro",
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-flash-lite",
    ],
    "openai": [
        "openai/gpt-4o",
        "openai/gpt-4.1-mini",
        "openai/gpt-4o-mini",
        "openai/gpt-4.1-nano",
    ],
    "groq": [
        "groq/llama-3.3-70b-versatile",
        "groq/mixtral-8x7b-32768",
        "groq/llama-3.1-8b-instant",
    ],
    "deepseek": [
        "deepseek/deepseek-reasoner",
        "deepseek/deepseek-chat",
    ],
    "qwen": [
        "openai/qwen-max",
        "openai/qwen-plus",
        "openai/qwen-turbo",
    ],
}


class ModelRouter:
    """Route tasks to the appropriate LangChain chat model and handle fallbacks."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._cache: dict[str, Any] = {}
        self._usage_log: list[dict[str, Any]] = []

    # ── Model selection ────────────────────────────────────────────────────

    def _model_for(self, category: TaskCategory, model_override: str | None = None) -> str:
        if model_override:
            return model_override
        request_model = get_request_model()
        if request_model:
            return request_model
        tier = _TASK_MODEL_MAP.get(category, "fast")
        if tier == "strong":
            return self._settings.strong_model
        return self._settings.fast_model

    def _fallback_model(self, failed_model: str) -> str:
        """Return a fallback model, preferring the same provider's models first."""
        provider, _ = self._split_model(failed_model)
        candidates = _PROVIDER_MODELS.get(provider, [])
        for candidate in candidates:
            if candidate and candidate != failed_model:
                return candidate
        # Last resort: the other tier's model
        settings = self._settings
        if failed_model == settings.fast_model:
            return settings.strong_model
        return settings.fast_model

    @staticmethod
    def _split_model(model: str) -> tuple[str, str]:
        """Split a ``provider/model-name`` string into (provider, model_name)."""
        provider, _, model_name = model.partition("/")
        if not provider:
            provider = "openai"
        return provider, model_name or model

    # ── LangChain model factory ────────────────────────────────────────────

    def _resolve_api_key(self, provider: str, explicit_key: str) -> str | None:
        """Resolve API key: explicit param > Settings fields > None (lets LangChain check env)."""
        if explicit_key:
            return explicit_key
        s = self._settings
        key_map = {
            "gemini": s.gemini_api_key,
            "groq": s.groq_api_key,
            "openai": s.openai_api_key,
            "deepseek": s.deepseek_api_key,
            "qwen": s.qwen_api_key,
        }
        resolved = key_map.get(provider, "")
        return resolved or None

    def _build_chat_model(self, model: str, *, temperature: float, max_tokens: int, api_key: str = ""):
        """Create the appropriate LangChain chat model for a provider/model string."""
        provider, model_name = self._split_model(model)
        key = self._resolve_api_key(provider, api_key)

        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=key,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )

        if provider == "groq":
            from langchain_groq import ChatGroq

            return ChatGroq(
                model=model_name,
                api_key=key,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # OpenAI-compatible endpoints (OpenAI, DeepSeek, Qwen, …)
        from langchain_openai import ChatOpenAI

        base_url = _OPENAI_COMPATIBLE.get(provider)
        if not base_url and "qwen" in model_name.lower():
            base_url = _OPENAI_COMPATIBLE["qwen"]
        return ChatOpenAI(
            model=model_name,
            api_key=key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # ── Cache ──────────────────────────────────────────────────────────────

    @staticmethod
    def _cache_key(model: str, messages: list[dict[str, str]], temperature: float) -> str:
        """Deterministic cache key for identical (model, messages, temperature)."""
        blob = json.dumps(
            {"model": model, "messages": messages, "temperature": temperature},
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    # ── Core completion ────────────────────────────────────────────────────

    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        category: TaskCategory = TaskCategory.CHAT,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: type[BaseModel] | None = None,
        use_cache: bool = True,
    ) -> str | BaseModel:
        """Send a completion request with automatic retry and fallback.

        Returns a ``str`` by default, or a validated Pydantic instance when
        *response_format* is provided.
        """
        settings = self._settings
        chosen_model = self._model_for(category, model)
        temp = temperature if temperature is not None else settings.llm_temperature
        tokens = max_tokens or settings.llm_max_tokens

        if use_cache:
            key = self._cache_key(chosen_model, messages, temp)
            if key in self._cache:
                logger.debug("Cache hit for %s", key[:12])
                return self._cache[key]

        # Try primary model, then fallback
        for attempt_model in (chosen_model, self._fallback_model(chosen_model)):
            try:
                result = await self._call_llm(
                    model=attempt_model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=tokens,
                    response_format=response_format,
                )
                if use_cache:
                    self._cache[self._cache_key(chosen_model, messages, temp)] = result
                return result
            except Exception as exc:
                logger.warning(
                    "LLM call failed on %s: %s — trying fallback",
                    attempt_model,
                    exc,
                )

        raise RuntimeError("All LLM models failed")

    async def _call_llm(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: type[BaseModel] | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> str | BaseModel:
        """Execute a single LangChain chat-model completion call."""
        # Prefer explicit api_key, then the per-request override, then env vars
        effective_key = api_key or get_request_api_key() or ""

        chat = self._build_chat_model(
            model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=effective_key,
        )
        if api_base:
            # Allow an explicit base URL override (e.g. custom OpenAI-compatible endpoints)
            chat.base_url = api_base

        t0 = time.monotonic()
        response = await chat.ainvoke(messages)
        elapsed = time.monotonic() - t0

        content = ""
        if isinstance(response.content, str):
            content = response.content
        elif isinstance(response.content, list):
            # Gemini can return a list of content parts
            content = "".join(
                str(p.get("text", "")) for p in response.content if isinstance(p, dict)
            )

        # Track usage from LangChain's usage metadata when available
        meta = getattr(response, "usage_metadata", None) or {}
        prompt_tokens = meta.get("input_tokens", 0) or 0
        completion_tokens = meta.get("output_tokens", 0) or 0
        total_tokens = prompt_tokens + completion_tokens
        cost = self._estimate_cost(model, prompt_tokens, completion_tokens)

        self._usage_log.append(
            {
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": cost,
                "elapsed_s": round(elapsed, 3),
            }
        )
        logger.info(
            "LLM %s: %d tokens, $%.4f, %.2fs",
            model,
            total_tokens,
            cost,
            elapsed,
        )

        if response_format is not None:
            return response_format.model_validate_json(self._extract_json(content))

        return content

    @staticmethod
    def _extract_json(text: str) -> str:
        """Strip markdown code fences or surrounding prose from a JSON payload."""
        if not text:
            return text
        stripped = text.strip()
        if stripped.startswith("```"):
            # Remove ```json ... ``` fences
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        # Find the outermost JSON object/array if prose surrounds it
        brace_start = stripped.find("{")
        bracket_start = stripped.find("[")
        starts = [p for p in (brace_start, bracket_start) if p >= 0]
        start = min(starts) if starts else -1
        end = -1
        if start >= 0:
            ends = [p for p in (stripped.rfind("}"), stripped.rfind("]")) if p >= 0]
            end = max(ends) if ends else -1
        if start >= 0 and end > start:
            return stripped[start : end + 1]
        return stripped

    # ── Structured helpers ─────────────────────────────────────────────────

    async def structured(
        self,
        *,
        messages: list[dict[str, str]],
        schema: type[T],
        category: TaskCategory = TaskCategory.EXTRACTION,
        model: str | None = None,
    ) -> T:
        """Convenience wrapper that always returns a validated Pydantic model."""
        result = await self.complete(
            messages=messages,
            category=category,
            model=model,
            response_format=schema,
        )
        if isinstance(result, schema):
            return result
        # Fallback: parse JSON string
        return schema.model_validate_json(str(result))

    # ── Cost ───────────────────────────────────────────────────────────────

    @staticmethod
    def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        rates = _COST_TABLE.get(model, {"input": 1.0, "output": 3.0})
        return (prompt_tokens * rates["input"] + completion_tokens * rates["output"]) / 1_000_000

    @property
    def total_cost(self) -> float:
        return sum(e["cost_usd"] for e in self._usage_log)

    @property
    def total_tokens(self) -> int:
        return sum(e["total_tokens"] for e in self._usage_log)

    @property
    def usage_log(self) -> list[dict[str, Any]]:
        return list(self._usage_log)

    # ── Streaming ───────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_api_base(model: str) -> str | None:
        """Return the API base URL for models that need one (e.g. Qwen/DeepSeek)."""
        provider, model_name = ModelRouter._split_model(model)
        base = _OPENAI_COMPATIBLE.get(provider)
        if not base and "qwen" in model_name.lower():
            base = _OPENAI_COMPATIBLE["qwen"]
        return base

    async def stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str = "You are an expert AI career coach. Be concise and helpful.",
        temperature: float | None = None,
        max_tokens: int | None = None,
        api_key: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield text chunks from a streaming LangChain chat completion."""
        settings = self._settings
        chosen_model = model or settings.fast_model
        temp = temperature if temperature is not None else settings.llm_temperature
        tokens = max_tokens or settings.llm_max_tokens

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        effective_key = api_key or get_request_api_key() or ""

        try:
            chat = self._build_chat_model(
                chosen_model,
                temperature=temp,
                max_tokens=tokens,
                api_key=effective_key,
            )
            async for chunk in chat.astream(messages):
                text = getattr(chunk, "content", "") or ""
                if isinstance(text, list):
                    text = "".join(str(p.get("text", "")) for p in text if isinstance(p, dict))
                if text:
                    yield text
        except Exception as exc:
            logger.warning("Stream failed on %s: %s — trying fallback", chosen_model, exc)
            fallback = self._fallback_model(chosen_model)
            try:
                fb_chat = self._build_chat_model(
                    fallback,
                    temperature=temp,
                    max_tokens=tokens,
                    api_key=effective_key,
                )
                async for chunk in fb_chat.astream(messages):
                    text = getattr(chunk, "content", "") or ""
                    if isinstance(text, list):
                        text = "".join(str(p.get("text", "")) for p in text if isinstance(p, dict))
                    if text:
                        yield text
            except Exception as exc2:
                logger.error("All streaming models failed: %s", exc2)
                yield "I'm sorry, I encountered an error. Please try again."


# ── LLMService alias for backward compatibility ─────────────────────────────


class LLMService:
    """Thin wrapper used by the chat endpoint.  Delegates to the global ModelRouter singleton."""

    def __init__(self) -> None:
        # Always use the module-level singleton — never create a new ModelRouter
        global _llm_service
        if _llm_service is None:
            _llm_service = ModelRouter()
        self._router = _llm_service

    async def stream(
        self, prompt: str, *, model: str | None = None, api_key: str | None = None, **kwargs: Any
    ) -> AsyncIterator[str]:
        async for chunk in self._router.stream(prompt, model=model, api_key=api_key, **kwargs):
            yield chunk

    async def complete(self, *args: Any, **kwargs: Any) -> str | BaseModel:
        return await self._router.complete(*args, **kwargs)


# ── Module-level singleton ───────────────────────────────────────────────────

_llm_service: ModelRouter | None = None


def get_llm_service() -> ModelRouter:
    """Return (and create on first call) the global ModelRouter singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = ModelRouter()
    return _llm_service