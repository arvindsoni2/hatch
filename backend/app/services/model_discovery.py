"""Curated, hardware-aware Hugging Face GGUF model discovery."""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from .ai_setup import load_catalog

POLICY_PATH = Path(__file__).parents[1] / "config" / "model_discovery_policy.json"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DiscoveredModel(BaseModel):
    catalog_id: str
    repo_id: str
    publisher: str
    family: str
    filename: str
    revision: str
    sha256: str
    size_bytes: int
    download_size_gb: float
    disk_required_gb: float
    min_ram_gb: int
    quantization: str
    task: Literal["text-generation"] = "text-generation"
    license: str
    download_url: str


class ModelDiscoveryResult(BaseModel):
    source: Literal["live", "cache", "fallback"]
    models: list[DiscoveredModel]
    compatible: list[DiscoveredModel]
    recommended_primary: DiscoveredModel | None = None
    recommended_triage: DiscoveredModel | None = None
    rejected_counts: dict[str, int] = Field(default_factory=dict)
    error: str | None = None


def _policy() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _config_dir() -> Path:
    return Path(os.getenv("HATCH_CONFIG_DIR", "/hatch-home/config"))


def _cache_path() -> Path:
    return _config_dir() / "model_discovery_cache.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _family(repo_id: str, families: list[str]) -> str | None:
    lowered = repo_id.lower()
    return next((family for family in families if family in lowered), None)


def _quantization(filename: str, quantizations: list[str]) -> str | None:
    upper = filename.upper()
    return next((value for value in quantizations if value.upper() in upper), None)


def _license(details: dict[str, Any]) -> str:
    card = details.get("cardData")
    if isinstance(card, dict) and isinstance(card.get("license"), str):
        return card["license"].lower()
    for tag in details.get("tags") or []:
        if isinstance(tag, str) and tag.startswith("license:"):
            return tag.split(":", 1)[1].lower()
    return ""


def _normalized_file(
    details: dict[str, Any],
    sibling: dict[str, Any],
    *,
    family: str,
    policy: dict[str, Any],
) -> DiscoveredModel | None:
    repo_id = str(details.get("id") or "")
    revision = str(details.get("sha") or "")
    filename = str(sibling.get("rfilename") or "")
    lfs = sibling.get("lfs") if isinstance(sibling.get("lfs"), dict) else {}
    size = sibling.get("size") or lfs.get("size")
    sha256 = str(lfs.get("sha256") or "")
    quantization = _quantization(filename, policy["quantizations"])
    if not (
        filename.lower().endswith(".gguf")
        and quantization
        and COMMIT_RE.fullmatch(revision)
        and SHA256_RE.fullmatch(sha256)
        and isinstance(size, int)
        and size > 0
    ):
        return None
    size_gb = round(size / 1_000_000_000, 3)
    return DiscoveredModel(
        catalog_id=f"hf:{repo_id}:{filename}:{revision[:12]}",
        repo_id=repo_id,
        publisher=repo_id.split("/", 1)[0].lower(),
        family=family,
        filename=filename,
        revision=revision,
        sha256=sha256,
        size_bytes=size,
        download_size_gb=size_gb,
        disk_required_gb=round(size_gb * 1.15 + 0.25, 2),
        min_ram_gb=max(3, math.ceil(size_gb * 1.25 + 2)),
        quantization=quantization,
        license=_license(details),
        download_url=f"https://huggingface.co/{repo_id}/resolve/{revision}/{filename}",
    )


def _rank(models: list[DiscoveredModel], probe: dict[str, Any]) -> tuple[
    list[DiscoveredModel], DiscoveredModel | None, DiscoveredModel | None
]:
    ram = float(probe.get("memory", {}).get("total_gb", 0) or 0)
    disk = float(probe.get("storage", {}).get("models_dir_free_gb", 0) or 0)
    compatible = [
        model for model in models
        if model.min_ram_gb <= ram and model.disk_required_gb <= disk
    ]
    compatible.sort(key=lambda model: (model.download_size_gb, model.repo_id, model.filename))
    triage = compatible[0] if compatible else None
    primary = compatible[-1] if compatible else None
    return compatible, primary, triage


def _result(
    source: Literal["live", "cache", "fallback"],
    models: list[DiscoveredModel],
    probe: dict[str, Any],
    *,
    rejected: Counter[str] | None = None,
    error: str | None = None,
) -> ModelDiscoveryResult:
    compatible, primary, triage = _rank(models, probe)
    return ModelDiscoveryResult(
        source=source,
        models=models,
        compatible=compatible,
        recommended_primary=primary,
        recommended_triage=triage,
        rejected_counts=dict(rejected or {}),
        error=error,
    )


def _load_cache(probe: dict[str, Any]) -> ModelDiscoveryResult | None:
    try:
        raw = json.loads(_cache_path().read_text(encoding="utf-8"))
        created = datetime.fromisoformat(str(raw["created_at"]).replace("Z", "+00:00"))
        ttl = timedelta(hours=float(_policy()["cache_ttl_hours"]))
        if _utcnow() - created > ttl:
            return None
        models = [DiscoveredModel.model_validate(item) for item in raw["models"]]
        return _result("cache", models, probe, rejected=Counter(raw.get("rejected_counts", {})))
    except (FileNotFoundError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _save_cache(models: list[DiscoveredModel], rejected: Counter[str]) -> None:
    path = _cache_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {
        "created_at": _utcnow().isoformat(),
        "models": [model.model_dump(mode="json") for model in models],
        "rejected_counts": dict(rejected),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _fallback(probe: dict[str, Any], error: str | None) -> ModelDiscoveryResult:
    models = [
        DiscoveredModel(
            catalog_id=item["id"],
            repo_id=item["repo_id"],
            publisher=item["repo_id"].split("/", 1)[0].lower(),
            family="qwen3.5",
            filename=item["filename"],
            revision=item["source_revision"],
            sha256=item["sha256"],
            size_bytes=int(float(item["download_size_gb"]) * 1_000_000_000),
            download_size_gb=float(item["download_size_gb"]),
            disk_required_gb=float(item["disk_required_gb"]),
            min_ram_gb=int(item["min_ram_gb"]),
            quantization=_quantization(item["filename"], _policy()["quantizations"]) or "Q4_K_M",
            license=item["license"],
            download_url=item["download_url_template"].format(
                source_revision=item["source_revision"]
            ),
        )
        for item in load_catalog()
    ]
    return _result("fallback", models, probe, error=error)


async def discover_models(
    probe: dict[str, Any],
    *,
    client: httpx.AsyncClient | None = None,
    force: bool = False,
) -> ModelDiscoveryResult:
    if not force and (cached := _load_cache(probe)) is not None:
        return cached
    policy = _policy()
    owned_client = client is None
    active_client = client or httpx.AsyncClient(
        base_url="https://huggingface.co", timeout=httpx.Timeout(15.0)
    )
    rejected: Counter[str] = Counter()
    try:
        response = await active_client.get(
            "/api/models",
            params={
                "filter": "text-generation",
                "search": "GGUF",
                "sort": "downloads",
                "direction": "-1",
                "limit": policy["max_repositories"],
            },
        )
        response.raise_for_status()
        listing = response.json()
        models: list[DiscoveredModel] = []
        for summary in listing if isinstance(listing, list) else []:
            repo_id = str(summary.get("id") or "")
            publisher = repo_id.split("/", 1)[0].lower()
            if publisher not in policy["approved_publishers"]:
                rejected["publisher"] += 1
                continue
            family = _family(repo_id, policy["approved_families"])
            lowered = repo_id.lower()
            if (
                not family
                or not any(marker in lowered for marker in ("instruct", "chat"))
                or any(marker in lowered for marker in ("reranker", "embedding", "embed"))
                or summary.get("pipeline_tag") not in policy["tasks"]
            ):
                rejected["task_or_family"] += 1
                continue
            detail_response = await active_client.get(
                f"/api/models/{repo_id}", params={"files_metadata": "true"}
            )
            detail_response.raise_for_status()
            details = detail_response.json()
            if _license(details) not in policy["approved_licenses"]:
                rejected["license"] += 1
                continue
            accepted = 0
            for sibling in details.get("siblings") or []:
                model = _normalized_file(details, sibling, family=family, policy=policy)
                if model is None:
                    continue
                models.append(model)
                accepted += 1
                if accepted >= policy["max_files_per_repository"]:
                    break
            if accepted == 0:
                rejected["file_metadata"] += 1
        if not models:
            raise ValueError("No curated compatible GGUF files were returned by Hugging Face.")
        _save_cache(models, rejected)
        return _result("live", models, probe, rejected=rejected)
    except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError) as exc:
        if cached := _load_cache(probe):
            cached.error = "Live discovery is unavailable; showing the recent curated cache."
            return cached
        return _fallback(probe, "Live discovery is unavailable; showing pinned fallback models.")
    finally:
        if owned_client:
            await active_client.aclose()


def verification_status(catalog_id: str) -> dict[str, Any]:
    try:
        manifest = json.loads(
            (_config_dir() / "model_verification.json").read_text(encoding="utf-8")
        )
        item = manifest.get(catalog_id)
        if not isinstance(item, dict):
            return {"status": "not_verified"}
        path = Path(str(item.get("path") or ""))
        if not path.is_file() or path.stat().st_size != item.get("size_bytes"):
            return {"status": "stale"}
        return {
            "status": "verified",
            "revision": item.get("revision"),
            "sha256": item.get("sha256"),
            "verified_at": item.get("verified_at"),
        }
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"status": "not_verified"}

