"""Curated Hugging Face local-model discovery tests."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.services.model_discovery import discover_models


FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "huggingface_models.json").read_text()
)


def _probe(ram_gb: float = 8, disk_gb: float = 20) -> dict:
    return {
        "sanitised": True,
        "memory": {"total_gb": ram_gb},
        "storage": {"models_dir_free_gb": disk_gb},
        "platform": {"os_family": "linux", "arch": "x86_64"},
    }


@pytest.fixture
def hf_client() -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/models":
            return httpx.Response(200, json=FIXTURE["listing"])
        repo_id = request.url.path.removeprefix("/api/models/")
        details = FIXTURE["details"].get(repo_id)
        return httpx.Response(200 if details else 404, json=details or {"error": "not found"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://huggingface.co")


@pytest.mark.asyncio
async def test_discovery_rejects_untrusted_unpinned_and_reranker_models(
    hf_client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))

    result = await discover_models(_probe(), client=hf_client)

    assert result.source == "live"
    assert {item.publisher for item in result.models} <= {"bartowski", "unsloth"}
    assert all(item.revision and item.sha256 and item.task == "text-generation" for item in result.models)
    assert all("reranker" not in item.repo_id.lower() for item in result.models)
    assert result.rejected_counts["publisher"] == 1
    assert result.rejected_counts["task_or_family"] == 1


@pytest.mark.asyncio
async def test_low_memory_probe_ranks_smaller_model_for_triage(
    hf_client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))

    result = await discover_models(_probe(ram_gb=8, disk_gb=20), client=hf_client)

    assert result.recommended_triage is not None
    assert "0.5B" in result.recommended_triage.repo_id
    assert result.recommended_primary is not None
    assert result.recommended_primary.min_ram_gb <= 8


@pytest.mark.asyncio
async def test_live_failure_uses_fresh_cache(
    hf_client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    await discover_models(_probe(), client=hf_client)

    async def fail(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    failed_client = httpx.AsyncClient(
        transport=httpx.MockTransport(fail), base_url="https://huggingface.co"
    )
    result = await discover_models(_probe(), client=failed_client, force=True)

    assert result.source == "cache"
    assert result.models
