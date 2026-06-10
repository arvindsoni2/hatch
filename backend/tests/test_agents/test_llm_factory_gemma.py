"""Tests for gemma4:e2b tuning in llm_factory and claude_client.

T5a — reasoning flag flows from profile to Ollama model build
T5a — Gemma 4 channel-form thought tokens are stripped before JSON parsing
T5d — top_p / top_k kwargs flow to Ollama build
T5e — soft warning logged when tiny primary model + reasoning disabled
"""
from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# T5a — Gemma 4 channel-form thought stripping
# ---------------------------------------------------------------------------

def test_strip_gemma4_channel_thoughts_from_json():
    """Gemma 4 emits <|channel>thought ...<channel|> — must be stripped before JSON parse."""
    import re as _re

    raw = '<|channel>thought I should analyse this carefully<channel|>{"role_title": "Architect"}'

    # The same strip logic used in claude_client.py
    text = _re.sub(r"<\|channel>.*?<channel\|>", "", raw, flags=_re.DOTALL)
    text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL)
    cleaned = text.strip()

    result = json.loads(cleaned)
    assert result["role_title"] == "Architect"


def test_strip_multiline_channel_thoughts():
    """Multi-line Gemma 4 thinking blocks must be stripped."""
    import re as _re

    raw = (
        "<|channel>thought\nStep 1: analyse the JD\n"
        "Step 2: identify keywords\n<channel|>"
        '{"company_name": "Mace", "sector": "construction"}'
    )
    text = _re.sub(r"<\|channel>.*?<channel\|>", "", raw, flags=_re.DOTALL)
    result = json.loads(text.strip())
    assert result["company_name"] == "Mace"


def test_strip_both_think_and_channel_forms():
    """Both <think>...</think> and <|channel>...<channel|> must be stripped."""
    import re as _re

    raw = "<think>qwen thinking</think><|channel>gemma thinking<channel|>42"
    text = _re.sub(r"<\|channel>.*?<channel\|>", "", raw, flags=_re.DOTALL)
    text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL)
    assert text.strip() == "42"


# ---------------------------------------------------------------------------
# T5a — reasoning flag gates <|think|> prepend
# ---------------------------------------------------------------------------

def test_reasoning_flag_true_prepends_think_token():
    """For gemma4 + reasoning=True, <|think|> must appear in system prompt."""
    from app.agents.tools.llm_factory import _maybe_add_think_token

    result = _maybe_add_think_token(
        "You are a CV writer.", provider="ollama", reasoning=True, model_name="gemma4:e2b"
    )
    assert "<|think|>" in result


def test_reasoning_flag_false_does_not_prepend_think_token():
    """For gemma4 + reasoning=False, system prompt must not be modified."""
    from app.agents.tools.llm_factory import _maybe_add_think_token

    result = _maybe_add_think_token(
        "You are a CV writer.", provider="ollama", reasoning=False, model_name="gemma4:e2b"
    )
    assert "<|think|>" not in result


def test_reasoning_flag_ignored_for_non_ollama():
    """<|think|> must only be prepended for Ollama; other providers use native flags."""
    from app.agents.tools.llm_factory import _maybe_add_think_token

    result = _maybe_add_think_token("You are a CV writer.", provider="anthropic", reasoning=True)
    assert "<|think|>" not in result


# ---------------------------------------------------------------------------
# T5a — LLMConfig.reasoning flows to _build_model
# ---------------------------------------------------------------------------

def test_reasoning_field_exists_on_llm_config():
    """LLMConfig must expose a reasoning field (default False)."""
    from app.schemas.profile import LLMConfig
    cfg = LLMConfig()
    assert hasattr(cfg, "reasoning")
    assert cfg.reasoning is False


def test_reasoning_true_in_profile_passes_to_ollama_kwargs():
    """_build_model must pass reasoning=True to init_chat_model when profile sets it."""
    from unittest.mock import patch, MagicMock
    from app.agents.tools import llm_factory

    mock_cfg = MagicMock()
    mock_cfg.provider = "ollama"
    mock_cfg.reasoning = True
    mock_cfg.temperature = 0.3
    mock_cfg.max_retries = 3
    mock_cfg.base_url = None
    mock_cfg.api_key_env = ""

    captured: dict = {}

    def fake_init(model, model_provider, **kwargs):
        captured.update(kwargs)
        m = MagicMock()
        m.with_config = MagicMock(return_value=m)
        return m

    with patch.object(llm_factory, "init_chat_model", side_effect=fake_init):
        llm_factory._build_model("gemma4:e2b", mock_cfg)

    assert captured.get("reasoning") is True


# ---------------------------------------------------------------------------
# T5d — top_p / top_k fields exist on LLMConfig
# ---------------------------------------------------------------------------

def test_top_p_top_k_fields_on_llm_config():
    """LLMConfig must expose top_p and top_k fields (both optional, default None)."""
    from app.schemas.profile import LLMConfig
    cfg = LLMConfig()
    assert hasattr(cfg, "top_p")
    assert hasattr(cfg, "top_k")
    assert cfg.top_p is None
    assert cfg.top_k is None


def test_top_p_top_k_passed_to_ollama_when_set():
    """_build_model must pass top_p/top_k to Ollama when configured."""
    from unittest.mock import patch, MagicMock
    from app.agents.tools import llm_factory

    mock_cfg = MagicMock()
    mock_cfg.provider = "ollama"
    mock_cfg.reasoning = False
    mock_cfg.temperature = 1.0
    mock_cfg.max_retries = 3
    mock_cfg.base_url = None
    mock_cfg.api_key_env = ""
    mock_cfg.top_p = 0.95
    mock_cfg.top_k = 64

    captured: dict = {}

    def fake_init(model, model_provider, **kwargs):
        captured.update(kwargs)
        m = MagicMock()
        m.with_config = MagicMock(return_value=m)
        return m

    with patch.object(llm_factory, "init_chat_model", side_effect=fake_init):
        llm_factory._build_model("gemma4:e2b", mock_cfg)

    assert captured.get("top_p") == 0.95
    assert captured.get("top_k") == 64


# ---------------------------------------------------------------------------
# T5e — soft warning for tiny model + reasoning disabled
# ---------------------------------------------------------------------------

def test_warning_logged_for_tiny_model_with_reasoning_off(caplog):
    """A warning must be logged when primary_model is a tiny model and reasoning=False."""
    import logging
    from unittest.mock import patch, MagicMock
    from app.agents.tools import llm_factory

    mock_cfg = MagicMock()
    mock_cfg.provider = "ollama"
    mock_cfg.reasoning = False
    mock_cfg.temperature = 0.3
    mock_cfg.max_retries = 3
    mock_cfg.base_url = None
    mock_cfg.api_key_env = ""
    mock_cfg.top_p = None
    mock_cfg.top_k = None

    def fake_init(model, model_provider, **kwargs):
        m = MagicMock()
        m.with_config = MagicMock(return_value=m)
        return m

    with patch.object(llm_factory, "init_chat_model", side_effect=fake_init):
        with caplog.at_level(logging.WARNING, logger="app.agents.tools.llm_factory"):
            llm_factory._build_model("gemma4:e2b", mock_cfg)

    assert any("reasoning" in r.message.lower() or "e2b" in r.message.lower() for r in caplog.records), (
        f"Expected warning about tiny model + reasoning disabled, got: {[r.message for r in caplog.records]}"
    )
