"""LangChain model factory — provider-agnostic LLM access for all agents.

Agents call get_triage_model() or get_primary_model(). The provider and model
names come from profile.yaml so users can switch between Anthropic, OpenAI,
Google, Ollama, Azure, or Bedrock without touching any agent code.

Never import provider SDKs (anthropic, openai, google.generativeai) directly
in agent code. Always go through this module.
"""
from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import LLMResult

from .profile_loader import load_profile

try:
    from langchain_core.callbacks import BaseCallbackHandler as _BaseCallbackHandler
except ImportError:
    _BaseCallbackHandler = object  # type: ignore[assignment,misc]

# ── In-memory LLM trace ring buffer ──────────────────────────────────────────

@dataclass
class _LLMTrace:
    id: int
    ts: str
    model: str
    duration_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    response_preview: str

_trace_counter: int = 0
_trace_buffer: deque[_LLMTrace] = deque(maxlen=100)

# Per-million-token pricing (USD) for common models — approximate estimates
_COST_TABLE: dict[str, tuple[float, float]] = {
    # model_fragment: (input_per_1M, output_per_1M)
    "gemini-2.0-flash": (0.075, 0.30),
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-3.0-flash": (0.075, 0.30),
    "gemini-2.0-pro": (1.25, 5.00),
    "gemini-2.5-pro": (1.25, 5.00),
    "gemini-3.0-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "claude-haiku": (0.80, 4.00),
    "claude-sonnet": (3.00, 15.00),
    "claude-opus": (15.00, 75.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


class CostTrackingCallback(_BaseCallbackHandler):  # type: ignore[misc]
    """LangChain callback that captures token usage and queues CostTracking rows.

    Usage:
        cb = CostTrackingCallback(agent_name="scorer", model="gemini-2.5-flash", job_id=job_id)
        llm.invoke(prompt, config={"callbacks": [cb]})
        await cb.flush(db)
    """

    def __init__(self, agent_name: str, model: str, job_id: str | None = None) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.model = model
        self.job_id = job_id
        self._pending: list[dict[str, Any]] = []

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = (response.llm_output or {}).get("token_usage", {})
        tokens_in = usage.get("prompt_tokens") or usage.get("input_token_count") or 0
        tokens_out = usage.get("completion_tokens") or usage.get("generated_token_count") or 0
        if not tokens_in and not tokens_out:
            text = " ".join(
                g.text for gen in response.generations for g in gen if hasattr(g, "text")
            )
            tokens_out = estimate_tokens(text)
        cost = estimate_cost(self.model, tokens_in, tokens_out)
        self._pending.append({
            "agent_name": self.agent_name,
            "model": self.model,
            "job_id": self.job_id,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_estimate": cost,
        })

    async def flush(self, db: Any) -> None:
        """Write all queued CostTracking rows to the database."""
        if not self._pending:
            return
        from ...models.cost_tracking import CostTracking
        for row in self._pending:
            db.add(CostTracking(**row))
        await db.flush()
        self._pending.clear()


class _LatencyCallback(_BaseCallbackHandler):  # type: ignore[misc]
    """Always-on callback attached to every model to record latency + response preview."""

    def __init__(self, model_name: str) -> None:
        super().__init__()
        self._model = model_name
        self._t0: float = 0.0

    def on_chat_model_start(self, serialized: dict, messages: list, **kwargs: Any) -> None:
        self._t0 = time.monotonic()

    def on_llm_start(self, serialized: dict, prompts: list, **kwargs: Any) -> None:
        self._t0 = time.monotonic()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        global _trace_counter
        duration_ms = int((time.monotonic() - self._t0) * 1000) if self._t0 else 0

        usage = (response.llm_output or {}).get("token_usage", {})
        tokens_in = usage.get("prompt_tokens") or usage.get("input_token_count") or 0
        tokens_out = usage.get("completion_tokens") or usage.get("generated_token_count") or 0

        preview = ""
        for gen_list in response.generations:
            for gen in gen_list:
                text = getattr(gen, "text", None) or ""
                if not text:
                    msg = getattr(gen, "message", None)
                    if msg:
                        content = getattr(msg, "content", "")
                        text = content if isinstance(content, str) else str(content)
                if text:
                    preview = text[:300]
                    break
            if preview:
                break

        if not tokens_out:
            tokens_out = estimate_tokens(preview)

        _trace_counter += 1
        _trace_buffer.append(_LLMTrace(
            id=_trace_counter,
            ts=datetime.now(timezone.utc).isoformat(),
            model=self._model,
            duration_ms=duration_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=estimate_cost(self._model, tokens_in, tokens_out),
            response_preview=preview,
        ))


def record_trace(
    model_name: str,
    duration_ms: int,
    content: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    """Record a completed LLM call to the trace buffer."""
    global _trace_counter
    tokens_out = tokens_out or estimate_tokens(content)
    _trace_counter += 1
    _trace_buffer.append(_LLMTrace(
        id=_trace_counter,
        ts=datetime.now(timezone.utc).isoformat(),
        model=model_name,
        duration_ms=duration_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=estimate_cost(model_name, tokens_in, tokens_out),
        response_preview=content[:300],
    ))


def get_llm_traces() -> list[dict[str, Any]]:
    """Return the last 100 LLM traces in reverse-chronological order."""
    return [
        {
            "id": t.id,
            "ts": t.ts,
            "model": t.model,
            "duration_ms": t.duration_ms,
            "tokens_in": t.tokens_in,
            "tokens_out": t.tokens_out,
            "cost_usd": t.cost_usd,
            "response_preview": t.response_preview,
        }
        for t in reversed(_trace_buffer)
    ]


def clear_llm_traces() -> None:
    """Wipe the in-memory trace buffer."""
    _trace_buffer.clear()


def _attach_tracer(model: BaseChatModel, model_name: str) -> BaseChatModel:
    """Attach the latency callback via with_config (Runnable-level, Pydantic-safe)."""
    try:
        return model.with_config({"callbacks": [_LatencyCallback(model_name)]})  # type: ignore[return-value]
    except Exception:
        return model


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return max(1, len(text) // 4)


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Return approximate USD cost for a model call based on known pricing."""
    model_lower = model.lower()
    for fragment, (in_rate, out_rate) in _COST_TABLE.items():
        if fragment in model_lower:
            return round(
                (tokens_in / 1_000_000) * in_rate + (tokens_out / 1_000_000) * out_rate,
                6,
            )
    return 0.0


def _build_model(model_name: str, llm_cfg: Any) -> BaseChatModel:
    """Instantiate a LangChain chat model from profile LLM config."""
    if not model_name:
        raise ValueError(
            f"LLM model name is empty for provider '{llm_cfg.provider}'. "
            "Set triage_model / primary_model in profile.yaml → llm section."
        )

    # llamacpp exposes an OpenAI-compatible API — use ChatOpenAI directly
    if llm_cfg.provider == "llamacpp":
        if not llm_cfg.base_url:
            raise ValueError(
                "provider='llamacpp' requires base_url to be set in profile.yaml → llm.base_url "
                "(e.g. 'http://llamacpp:8080/v1')"
            )
        from langchain_openai import ChatOpenAI  # noqa: PLC0415
        return _attach_tracer(ChatOpenAI(
            model=model_name,
            base_url=llm_cfg.base_url,
            openai_api_key="not-required",
            temperature=llm_cfg.temperature,
            max_retries=llm_cfg.max_retries,
        ), model_name)

    provider = llm_cfg.provider

    kwargs: dict[str, Any] = {
        "temperature": llm_cfg.temperature,
        "max_retries": llm_cfg.max_retries,
    }

    # Resolve API key from env (never read key directly from profile)
    if llm_cfg.api_key_env:
        api_key = os.getenv(llm_cfg.api_key_env, "")
        if api_key:
            kwargs["api_key"] = api_key

    # base_url is used for Ollama and Azure endpoints.
    # Ollama falls back to host.containers.internal so it works from inside containers
    # even when profile.yaml was saved without an explicit base_url.
    _ollama_default = "http://host.containers.internal:11434"
    effective_base_url = llm_cfg.base_url or (_ollama_default if llm_cfg.provider == "ollama" else None)
    if effective_base_url:
        kwargs["base_url"] = effective_base_url

    # Disable thinking/reasoning mode for Ollama — models like gemma4 default to thinking
    # mode which generates thousands of internal tokens before responding, causing 14+ minute
    # response times and breaking JSON parsing.
    if llm_cfg.provider == "ollama":
        kwargs["reasoning"] = False

    return _attach_tracer(init_chat_model(
        model=model_name,
        model_provider=provider,
        **kwargs,
    ), model_name)


def get_triage_model() -> BaseChatModel:
    """Return the fast/cheap triage model configured in profile.yaml.

    Used for: pre-filtering job listings, quick relevance checks.
    Default: Haiku / GPT-4o-mini / Gemini Flash (depends on provider).
    """
    profile = load_profile()
    return _build_model(profile.llm.triage_model, profile.llm)


def get_primary_model() -> BaseChatModel:
    """Return the strong primary model configured in profile.yaml.

    Used for: detailed scoring, CV tailoring, coaching, question generation.
    Default: Sonnet / GPT-4o / Gemini Pro (depends on provider).
    """
    profile = load_profile()
    return _build_model(profile.llm.primary_model, profile.llm)


def get_json_model() -> BaseChatModel:
    """Return the primary model configured for JSON-constrained output.

    For Ollama providers, passes format='json' to enable constrained token
    sampling — only valid JSON tokens are sampled at the model level.
    For all other providers, delegates to get_primary_model() (JSON is
    enforced via system-prompt instructions instead).
    """
    profile = load_profile()
    llm_cfg = profile.llm
    if llm_cfg.provider == "ollama":
        if not llm_cfg.primary_model:
            raise ValueError(
                f"LLM model name is empty for provider '{llm_cfg.provider}'. "
                "Set primary_model in profile.yaml → llm section."
            )
        kwargs: dict[str, Any] = {
            "temperature": llm_cfg.temperature,
            "max_retries": llm_cfg.max_retries,
            "format": "json",
            "base_url": llm_cfg.base_url or "http://host.containers.internal:11434",
            "reasoning": False,
        }
        return _attach_tracer(init_chat_model(
            model=llm_cfg.primary_model,
            model_provider="ollama",
            **kwargs,
        ), llm_cfg.primary_model)
    if llm_cfg.provider == "llamacpp":
        if not llm_cfg.base_url:
            raise ValueError(
                "provider='llamacpp' requires base_url to be set in profile.yaml → llm.base_url "
                "(e.g. 'http://llamacpp:8080/v1')"
            )
        from langchain_openai import ChatOpenAI  # noqa: PLC0415
        return _attach_tracer(ChatOpenAI(
            model=llm_cfg.primary_model,
            base_url=llm_cfg.base_url,
            openai_api_key="not-required",
            temperature=llm_cfg.temperature,
            max_retries=llm_cfg.max_retries,
            model_kwargs={"response_format": {"type": "json_object"}},
        ), llm_cfg.primary_model)
    return _build_model(llm_cfg.primary_model, llm_cfg)
