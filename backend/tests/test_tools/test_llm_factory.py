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
        assert result is mock_model

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
        assert result is mock_model

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
        mock_profile.llm.primary_model = "phi3:mini"
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
        assert call_kwargs.get("model") == "phi3:mini"
        assert call_kwargs.get("model_provider") == "ollama"
        assert result is mock_model

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
            result = get_json_model()

        call_kwargs = mock_init.call_args.kwargs
        assert "format" not in call_kwargs

    def test_get_json_model_raises_for_empty_model_name(self):
        """get_json_model() raises ValueError when primary_model is empty for Ollama."""
        mock_profile = MagicMock()
        mock_profile.llm.provider = "ollama"
        mock_profile.llm.primary_model = ""
        mock_profile.llm.temperature = 0.3
        mock_profile.llm.max_retries = 3
        mock_profile.llm.base_url = "http://localhost:11434"

        with patch("app.agents.tools.llm_factory.load_profile", return_value=mock_profile):
            from app.agents.tools.llm_factory import get_json_model
            with pytest.raises(ValueError, match="model name is empty"):
                get_json_model()
