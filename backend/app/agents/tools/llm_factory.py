"""LangChain model factory — provider-agnostic LLM access for all agents.

Agents call get_triage_model() or get_primary_model(). The provider and model
names come from profile.yaml so users can switch between Anthropic, OpenAI,
Google, Ollama, Azure, or Bedrock without touching any agent code.

Never import provider SDKs (anthropic, openai, google.generativeai) directly
in agent code. Always go through this module.
"""
from __future__ import annotations

import os
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from .profile_loader import load_profile


def _build_model(model_name: str, llm_cfg: Any) -> BaseChatModel:
    """Instantiate a LangChain chat model from profile LLM config."""
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
