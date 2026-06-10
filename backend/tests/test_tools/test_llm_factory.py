"""Tests for LLM factory — provider-agnostic model construction."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from app.agents.tools.llm_factory import estimate_tokens, estimate_cost


class TestLlmFactory:

    def test_get_triage_model_calls_init_chat_model_with_correct_args(self):
        """get_triage_model() calls init_chat_model with provider and model from profile."""
        mock_model = MagicMock()
        mock_profile = MagicMock()
        mock_profile.llm.provider = "anthropic"
        mock_profile.llm.triage_model = "claude-haiku-4-5-20251001"
        mock_profile.llm.primary_model = "claude-sonnet-4-6"
        mock_profile.llm.temperature = 0.3
        mock_profile.llm.max_retries = 3
        mock_profile.llm.api_key_env = "ANTHROPIC_API_KEY"
        mock_profile.llm.base_url = None

        with patch("app.agents.tools.llm_factory.load_profile", return_value=mock_profile), \
             patch("app.agents.tools.llm_factory.init_chat_model", return_value=mock_model) as mock_init:
            from app.agents.tools.llm_factory import get_triage_model
            result = get_triage_model()

        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs.get("model") == "claude-haiku-4-5-20251001"
        assert call_kwargs.get("model_provider") == "anthropic"
        # _attach_tracer wraps the model via .with_config() for latency callbacks
        assert result is mock_model.with_config.return_value

    def test_get_primary_model_calls_init_chat_model_with_correct_args(self):
        """get_primary_model() calls init_chat_model with the primary model from profile."""
        mock_model = MagicMock()
        mock_profile = MagicMock()
        mock_profile.llm.provider = "anthropic"
        mock_profile.llm.triage_model = "claude-haiku-4-5-20251001"
        mock_profile.llm.primary_model = "claude-sonnet-4-6"
        mock_profile.llm.temperature = 0.3
        mock_profile.llm.max_retries = 3
        mock_profile.llm.api_key_env = "ANTHROPIC_API_KEY"
        mock_profile.llm.base_url = None

        with patch("app.agents.tools.llm_factory.load_profile", return_value=mock_profile), \
             patch("app.agents.tools.llm_factory.init_chat_model", return_value=mock_model) as mock_init:
            from app.agents.tools.llm_factory import get_primary_model
            result = get_primary_model()

        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs.get("model") == "claude-sonnet-4-6"
        assert call_kwargs.get("model_provider") == "anthropic"
        # _attach_tracer wraps the model via .with_config() for latency callbacks
        assert result is mock_model.with_config.return_value

    def test_estimate_cost_returns_correct_value_for_known_model(self):
        """estimate_cost() calculates correct USD cost from the pricing table."""
        # claude-sonnet: $3.00/1M input, $15.00/1M output
        cost = estimate_cost("claude-sonnet-4-6", tokens_in=1_000_000, tokens_out=1_000_000)
        assert abs(cost - 18.0) < 0.01

    def test_estimate_tokens_approximates_four_chars_per_token(self):
        """estimate_tokens() uses 4-chars-per-token approximation."""
        text = "a" * 400
        assert estimate_tokens(text) == 100

    def test_estimate_cost_returns_zero_for_unknown_model(self):
        """estimate_cost() returns 0.0 for unrecognised model names."""
        cost = estimate_cost("some-unknown-model-xyz", tokens_in=1000, tokens_out=1000)
        assert cost == 0.0

    def test_get_json_model_passes_format_json_for_ollama(self):
        """get_json_model() passes format='json' to ChatOllama for constrained decoding."""
        mock_model = MagicMock()
        mock_profile = MagicMock()
        mock_profile.llm.provider = "ollama"
        mock_profile.llm.primary_model = "qwen3:4b"
        mock_profile.llm.temperature = 0.3
        mock_profile.llm.max_retries = 3
        mock_profile.llm.api_key_env = ""
        mock_profile.llm.base_url = "http://localhost:11434"

        with patch("app.agents.tools.llm_factory.load_profile", return_value=mock_profile), \
             patch("app.agents.tools.llm_factory.init_chat_model", return_value=mock_model) as mock_init:
            from app.agents.tools.llm_factory import get_json_model
            result = get_json_model()

        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs.get("format") == "json"
        assert call_kwargs.get("model") == "qwen3:4b"
        assert call_kwargs.get("model_provider") == "ollama"
        # _attach_tracer wraps the model via .with_config() for latency callbacks
        assert result is mock_model.with_config.return_value

    def test_get_json_model_no_format_for_non_ollama(self):
        """get_json_model() does not pass format='json' for non-Ollama providers."""
        mock_model = MagicMock()
        mock_profile = MagicMock()
        mock_profile.llm.provider = "anthropic"
        mock_profile.llm.primary_model = "claude-sonnet-4-6"
        mock_profile.llm.temperature = 0.3
        mock_profile.llm.max_retries = 3
        mock_profile.llm.api_key_env = "ANTHROPIC_API_KEY"
        mock_profile.llm.base_url = None

        with patch("app.agents.tools.llm_factory.load_profile", return_value=mock_profile), \
             patch("app.agents.tools.llm_factory.init_chat_model", return_value=mock_model) as mock_init:
            from app.agents.tools.llm_factory import get_json_model
            get_json_model()

        call_kwargs = mock_init.call_args.kwargs
        assert "format" not in call_kwargs

    def test_get_json_model_raises_for_empty_model_name(self):
        """get_json_model() propagates ValueError from _detect_ollama_model when Ollama has no models."""
        mock_profile = MagicMock()
        mock_profile.llm.provider = "ollama"
        mock_profile.llm.primary_model = ""
        mock_profile.llm.temperature = 0.3
        mock_profile.llm.max_retries = 3
        mock_profile.llm.base_url = "http://localhost:11434"

        with patch("app.agents.tools.llm_factory.load_profile", return_value=mock_profile), \
             patch("app.agents.tools.llm_factory._detect_ollama_model",
                   side_effect=ValueError("model name is empty")):
            from app.agents.tools.llm_factory import get_json_model
            with pytest.raises(ValueError, match="model name is empty"):
                get_json_model()


def _make_llm_cfg(provider: str, base_url: str = "http://llamacpp:8080/v1") -> MagicMock:
    cfg = MagicMock()
    cfg.provider = provider
    cfg.primary_model = "Qwen3-14B-Instruct"
    cfg.triage_model = "Qwen3-14B-Instruct"
    cfg.temperature = 0.3
    cfg.max_retries = 2
    cfg.base_url = base_url
    cfg.api_key_env = ""
    return cfg


def _make_profile(provider: str) -> MagicMock:
    profile = MagicMock()
    profile.llm = _make_llm_cfg(provider)
    return profile


def _unwrap(model: object) -> object:
    """Unwrap a RunnableBinding returned by _attach_tracer to get the inner model."""
    return model.bound if hasattr(model, "bound") else model  # type: ignore[union-attr]


class TestLlamaCppProvider:
    def test_build_model_llamacpp_returns_chat_openai(self):
        """_build_model with provider=llamacpp returns a ChatOpenAI (wrapped by _attach_tracer)."""
        from langchain_openai import ChatOpenAI
        from app.agents.tools.llm_factory import _build_model

        cfg = _make_llm_cfg("llamacpp")
        model = _build_model("Qwen3-14B-Instruct", cfg)

        assert isinstance(_unwrap(model), ChatOpenAI)

    def test_get_primary_model_llamacpp_uses_base_url(self):
        """get_primary_model for llamacpp passes openai_api_base."""
        from langchain_openai import ChatOpenAI
        from app.agents.tools.llm_factory import get_primary_model

        with patch("app.agents.tools.llm_factory.load_profile", return_value=_make_profile("llamacpp")):
            model = get_primary_model()

        inner = _unwrap(model)
        assert isinstance(inner, ChatOpenAI)
        assert inner.openai_api_base == "http://llamacpp:8080/v1"

    def test_get_json_model_llamacpp_sets_response_format(self):
        """get_json_model for llamacpp sets response_format=json_object in model_kwargs."""
        from langchain_openai import ChatOpenAI
        from app.agents.tools.llm_factory import get_json_model

        with patch("app.agents.tools.llm_factory.load_profile", return_value=_make_profile("llamacpp")):
            model = get_json_model()

        inner = _unwrap(model)
        assert isinstance(inner, ChatOpenAI)
        assert inner.model_kwargs.get("response_format") == {"type": "json_object"}


class TestModelAwareThinking:
    """LLM-2: qwen3 thinking is ON by default; gemma4 is OFF by default."""

    def test_maybe_add_think_token_qwen3_adds_no_think_when_reasoning_false(self):
        """_maybe_add_think_token prepends /no_think for qwen3 when reasoning=False."""
        from app.agents.tools.llm_factory import _maybe_add_think_token
        result = _maybe_add_think_token("Evaluate the response.", "ollama", False, "qwen3:4b")
        assert result.startswith("/no_think")

    def test_maybe_add_think_token_qwen3_no_prefix_when_reasoning_true(self):
        """_maybe_add_think_token does NOT add /no_think for qwen3 when reasoning=True."""
        from app.agents.tools.llm_factory import _maybe_add_think_token
        result = _maybe_add_think_token("Evaluate the response.", "ollama", True, "qwen3:4b")
        assert not result.startswith("/no_think")

    def test_maybe_add_think_token_gemma4_adds_think_when_reasoning_true(self):
        """_maybe_add_think_token prepends <|think|> for gemma4 when reasoning=True."""
        from app.agents.tools.llm_factory import _maybe_add_think_token
        result = _maybe_add_think_token("Score this answer.", "ollama", True, "gemma4:e2b")
        assert result.startswith("<|think|>")

    def test_maybe_add_think_token_gemma4_no_prefix_when_reasoning_false(self):
        """_maybe_add_think_token is a no-op for gemma4 when reasoning=False."""
        from app.agents.tools.llm_factory import _maybe_add_think_token
        result = _maybe_add_think_token("Score this answer.", "ollama", False, "gemma4:e2b")
        assert result == "Score this answer."

    def test_maybe_add_think_token_non_ollama_is_noop(self):
        """_maybe_add_think_token is always a no-op for non-Ollama providers."""
        from app.agents.tools.llm_factory import _maybe_add_think_token
        result = _maybe_add_think_token("prompt", "anthropic", True, "claude-sonnet-4-6")
        assert result == "prompt"

    def test_build_model_qwen3_passes_think_false(self):
        """For qwen3 models, _build_model passes think=False when reasoning=False."""
        mock_model = MagicMock()
        mock_profile = MagicMock()
        mock_profile.llm.provider = "ollama"
        mock_profile.llm.primary_model = "qwen3:4b"
        mock_profile.llm.temperature = 0.3
        mock_profile.llm.max_retries = 3
        mock_profile.llm.api_key_env = ""
        mock_profile.llm.base_url = "http://localhost:11434"
        mock_profile.llm.reasoning = False
        mock_profile.llm.top_p = None
        mock_profile.llm.top_k = None

        with patch("app.agents.tools.llm_factory.load_profile", return_value=mock_profile), \
             patch("app.agents.tools.llm_factory.init_chat_model", return_value=mock_model) as mock_init:
            from app.agents.tools.llm_factory import get_primary_model
            get_primary_model()

        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs.get("think") is False
        assert "reasoning" not in call_kwargs  # qwen3 uses think=, not reasoning=

    def test_tiny_model_patterns_include_qwen3_small_variants(self):
        """_TINY_MODEL_PATTERNS flags qwen3:1.7b as tiny but not qwen3:4b."""
        from app.agents.tools.llm_factory import _TINY_MODEL_PATTERNS
        assert any(p in "qwen3:1.7b" for p in _TINY_MODEL_PATTERNS)
        assert not any(p in "qwen3:4b" for p in _TINY_MODEL_PATTERNS)


class TestThinkBlockStripping:
    def test_complete_json_strips_think_blocks(self):
        """complete_json strips <think>…</think> before JSON parsing."""
        import asyncio
        from unittest.mock import AsyncMock

        from app.services.claude_client import ClaudeClient

        raw = '<think>Let me think about this carefully.</think>\n{"key": "value"}'
        mock_response = MagicMock()
        mock_response.content = raw

        async def run():
            client = ClaudeClient()
            with patch(
                "app.services.claude_client.get_json_model",
                return_value=MagicMock(ainvoke=AsyncMock(return_value=mock_response)),
            ):
                result = await client.complete_json("system", "user")
            return result

        result = asyncio.run(run())
        assert result == {"key": "value"}
