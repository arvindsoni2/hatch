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
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import LLMResult

from .profile_loader import load_profile

try:
    from langchain_core.callbacks import BaseCallbackHandler as _BaseCallbackHandler
except ImportError:
    _BaseCallbackHandler = object  # type: ignore[assignment,misc]

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
        from langchain_openai import ChatOpenAI  # noqa: PLC0415
        return ChatOpenAI(
            model=model_name,
            openai_api_base=llm_cfg.base_url,
            openai_api_key="not-required",
            temperature=llm_cfg.temperature,
            max_retries=llm_cfg.max_retries,
        )

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

    # base_url is used for Ollama and Azure endpoints
    if llm_cfg.base_url:
        kwargs["base_url"] = llm_cfg.base_url

    return init_chat_model(
        model=model_name,
        model_provider=provider,
        **kwargs,
    )


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
        }
        if llm_cfg.base_url:
            kwargs["base_url"] = llm_cfg.base_url
        return init_chat_model(
            model=llm_cfg.primary_model,
            model_provider="ollama",
            **kwargs,
        )
    if llm_cfg.provider == "llamacpp":
        from langchain_openai import ChatOpenAI  # noqa: PLC0415
        return ChatOpenAI(
            model=llm_cfg.primary_model,
            openai_api_base=llm_cfg.base_url,
            openai_api_key="not-required",
            temperature=llm_cfg.temperature,
            max_retries=llm_cfg.max_retries,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    return _build_model(llm_cfg.primary_model, llm_cfg)
