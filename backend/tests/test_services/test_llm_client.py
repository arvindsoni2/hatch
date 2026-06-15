"""Tests for LLMClient — complete_json uses JSON-mode model for Ollama."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestLLMClient:

    async def test_complete_json_uses_get_json_model(self):
        """complete_json() calls get_json_model(), not get_primary_model()."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"key": "value"}'))
        mock_llm.bind.return_value = mock_llm

        with patch("app.services.llm_client.get_json_model", return_value=mock_llm) as mock_factory, \
             patch("app.services.llm_client.get_primary_model") as mock_primary:
            from app.services.llm_client import LLMClient
            client = LLMClient()
            result = await client.complete_json("sys", "user")

        mock_factory.assert_called_once()
        mock_primary.assert_not_called()
        assert result == {"key": "value"}

    async def test_complete_json_forwards_max_tokens(self):
        """Stage budgets must reach the provider instead of remaining decorative."""
        bound = MagicMock()
        bound.ainvoke = AsyncMock(return_value=MagicMock(content='{"ok": true}'))
        mock_llm = MagicMock()
        mock_llm.bind.return_value = bound

        with patch("app.services.llm_client.get_json_model", return_value=mock_llm):
            from app.services.llm_client import LLMClient
            result = await LLMClient().complete_json("sys", "user", max_tokens=321)

        mock_llm.bind.assert_called_once_with(max_tokens=321)
        assert result == {"ok": True}

    async def test_complete_json_retries_on_parse_failure(self):
        """complete_json() retries up to 3 times on JSONDecodeError."""
        call_count = 0

        async def flaky_invoke(messages):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return MagicMock(content="not json at all")
            return MagicMock(content='{"ok": true}')

        mock_llm = MagicMock()
        mock_llm.ainvoke = flaky_invoke
        mock_llm.bind.return_value = mock_llm

        with patch("app.services.llm_client.get_json_model", return_value=mock_llm):
            from app.services.llm_client import LLMClient
            client = LLMClient()
            result = await client.complete_json("sys", "user")

        assert result == {"ok": True}
        assert call_count == 3

    async def test_complete_json_raises_after_3_failures(self):
        """complete_json() raises ValueError after 3 parse failures."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="not json"))
        mock_llm.bind.return_value = mock_llm

        with patch("app.services.llm_client.get_json_model", return_value=mock_llm):
            from app.services.llm_client import LLMClient
            client = LLMClient()
            with pytest.raises(ValueError, match="3 attempts"):
                await client.complete_json("sys", "user")

    async def test_complete_strips_markdown_fences(self):
        """complete_json() strips ```json ... ``` code fences before parsing."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='```json\n{"key": "val"}\n```'))
        mock_llm.bind.return_value = mock_llm

        with patch("app.services.llm_client.get_json_model", return_value=mock_llm):
            from app.services.llm_client import LLMClient
            client = LLMClient()
            result = await client.complete_json("sys", "user")

        assert result == {"key": "val"}
