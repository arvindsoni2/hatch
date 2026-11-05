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


def _discovery_client(listing: list[dict], details: dict[str, dict]) -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/models":
            return httpx.Response(200, json=listing)
        repo_id = request.url.path.removeprefix("/api/models/")
        body = details.get(repo_id)
        return httpx.Response(200 if body else 404, json=body or {"error": "not found"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://huggingface.co")


def _repo(repo_id: str, license_name: str, pipeline_tag: str, files: list[str]) -> dict:
    return {
        "id": repo_id,
        "sha": "a" * 40,
        "pipeline_tag": pipeline_tag,
        "cardData": {"license": license_name},
        "siblings": [
            {"rfilename": name, "size": 1_000_000_000, "lfs": {"sha256": "b" * 64}}
            for name in files
        ],
    }


@pytest.mark.asyncio
async def test_policy_accepts_spark_and_minicpm_families_only_from_allowlisted_publishers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    details = {
        "XHToken/Spark-X2.6-4B-GGUF": _repo(
            "XHToken/Spark-X2.6-4B-GGUF", "apache-2.0", "text-generation",
            ["Spark-X2.6-4B-Q4_K_M.gguf"],
        ),
        "openbmb/MiniCPM5-2B-GGUF": _repo(
            "openbmb/MiniCPM5-2B-GGUF", "apache-2.0", "text-generation",
            ["MiniCPM5-2B-Q4_K_M.gguf"],
        ),
        "evilcorp/Spark-X2.6-4B-GGUF": _repo(
            "evilcorp/Spark-X2.6-4B-GGUF", "apache-2.0", "text-generation",
            ["Spark-X2.6-4B-Q4_K_M.gguf"],
        ),
    }

    result = await discover_models(
        _probe(), client=_discovery_client(list(details.values()), details)
    )

    assert {item.repo_id for item in result.models} == {
        "XHToken/Spark-X2.6-4B-GGUF",
        "openbmb/MiniCPM5-2B-GGUF",
    }
    assert result.rejected_counts["publisher"] == 1


@pytest.mark.asyncio
async def test_vision_repo_accepted_text_only_without_mmproj(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    repo = _repo(
        "openbmb/MiniCPM-V-4.7-1B-gguf", "apache-2.0", "image-text-to-text",
        [
            "MiniCPM-V-4_7-1B-Q8_0.gguf",
            "MiniCPM-V-4_7-1B-F16.gguf",
            "mmproj-model-f16-4x.gguf",
        ],
    )

    result = await discover_models(
        _probe(), client=_discovery_client([repo], {repo["id"]: repo})
    )

    assert [item.filename for item in result.models] == ["MiniCPM-V-4_7-1B-Q8_0.gguf"]
    assert result.models[0].task == "text-generation"
    assert all("mmproj" not in item.filename.lower() for item in result.models)


@pytest.mark.asyncio
async def test_unapproved_licence_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    rejected = _repo(
        "XHToken/Spark-X2.6-4B-Gemma-GGUF", "gemma", "text-generation",
        ["Spark-X2.6-4B-Q4_K_M.gguf"],
    )
    accepted = _repo(
        "XHToken/Spark-X2.6-4B-GGUF", "apache-2.0", "text-generation",
        ["Spark-X2.6-4B-Q4_K_M.gguf"],
    )

    result = await discover_models(
        _probe(),
        client=_discovery_client([rejected, accepted], {
            rejected["id"]: rejected,
            accepted["id"]: accepted,
        }),
    )

    assert [item.repo_id for item in result.models] == [accepted["id"]]
    assert result.rejected_counts["license"] == 1
