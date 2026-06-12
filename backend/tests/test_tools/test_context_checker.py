"""Tests for the startup context budget assertion (RT-2)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_llm_cfg(
    provider: str = "llamacpp",
    base_url: str = "http://llm-primary:8080/v1",
    triage_base_url: str = "http://llm-triage:8081/v1",
):
    cfg = MagicMock()
    cfg.provider = provider
    cfg.base_url = base_url
    cfg.triage_base_url = triage_base_url
    return cfg


class TestAssertContextBudgets:
    @pytest.mark.asyncio
    async def test_skips_non_llamacpp_provider(self):
        """assert_context_budgets does nothing for non-llamacpp providers."""
        from app.agents.tools.context_checker import assert_context_budgets, get_degraded_details

        cfg = _make_llm_cfg(provider="ollama")
        await assert_context_budgets(cfg)
        assert get_degraded_details() == []

    @pytest.mark.asyncio
    async def test_skips_silently_when_server_unreachable(self):
        """When /props returns a network error, check passes silently."""
        import httpx
        from app.agents.tools.context_checker import assert_context_budgets, get_degraded_details

        cfg = _make_llm_cfg()
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.side_effect = httpx.ConnectError("refused")
            mock_cls.return_value = mock_client

            await assert_context_budgets(cfg)

        assert get_degraded_details() == []

    @pytest.mark.asyncio
    async def test_warns_when_slot_context_too_small(self):
        """Mismatch between slot context and budget emits a warning and sets degraded details."""
        from app.agents.tools.context_checker import assert_context_budgets, get_degraded_details

        cfg = _make_llm_cfg(base_url="http://llm-primary:8080/v1", triage_base_url="")

        # /props returns ctx=1024 parallel=1 → slot=1024, which is too small for primary
        props_response = MagicMock()
        props_response.raise_for_status = MagicMock()
        props_response.json.return_value = {"n_ctx": 1024, "n_parallel": 1}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = props_response
            mock_cls.return_value = mock_client

            with patch("app.agents.tools.context_checker.logger") as mock_log:
                await assert_context_budgets(cfg)
                assert mock_log.warning.called

        details = get_degraded_details()
        assert len(details) >= 1
        assert details[0]["reason"] == "context_budget_exceeds_slot"

    @pytest.mark.asyncio
    async def test_no_degraded_when_slot_sufficient(self):
        """No degraded details when /props shows slot context >= required budget."""
        from app.agents.tools.context_checker import assert_context_budgets, get_degraded_details

        cfg = _make_llm_cfg(base_url="http://llm-primary:8080/v1", triage_base_url="")

        # /props returns ctx=32768 parallel=1 → slot=32768, more than enough
        props_response = MagicMock()
        props_response.raise_for_status = MagicMock()
        props_response.json.return_value = {"n_ctx": 32768, "n_parallel": 1}

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = props_response
            mock_cls.return_value = mock_client

            await assert_context_budgets(cfg)

        assert get_degraded_details() == []
