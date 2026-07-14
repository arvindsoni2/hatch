"""Cloud provider catalog and validation evidence tests."""
from __future__ import annotations

import httpx
import pytest

from app.services.provider_catalog import (
    provider_catalog,
    provider_validation_status,
    test_provider_connection as run_provider_test,
    validate_provider_selection,
)


def test_catalog_owns_primary_and_triage_models_without_secrets() -> None:
    catalog = provider_catalog()

    assert {provider["id"] for provider in catalog["providers"]} == {
        "anthropic", "openai", "google_genai", "openrouter"
    }
    assert all(provider["primary_model"] for provider in catalog["providers"])
    assert all(provider["triage_model"] for provider in catalog["providers"])
    assert "sk-" not in str(catalog)


def test_selection_rejects_models_outside_provider_catalog() -> None:
    with pytest.raises(ValueError, match="not in the curated"):
        validate_provider_selection("openai", "invented-primary", "invented-triage")


@pytest.mark.asyncio
async def test_explicit_openai_test_uses_responses_api_and_redacts_secret(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-sensitive-value")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "resp_test", "status": "completed"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await run_provider_test(
        "openai", "gpt-5.6", "gpt-5.6", client=client
    )

    assert result["ok"] is True
    assert requests[0].url.path == "/v1/responses"
    assert "sk-sensitive-value" not in str(result)
    assert "sk-sensitive-value" not in (tmp_path / "provider_validation.json").read_text()
    assert provider_validation_status("openai", "gpt-5.6", "gpt-5.6")["status"] == "ready"


@pytest.mark.asyncio
async def test_google_test_keeps_api_key_out_of_request_url(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_API_KEY", "google-sensitive-value")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"candidates": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await run_provider_test(
        "google_genai", "gemini-2.5-flash", "gemini-2.5-flash", client=client
    )

    assert result["ok"] is True
    assert "google-sensitive-value" not in str(requests[0].url)
    assert requests[0].headers["x-goog-api-key"] == "google-sensitive-value"
