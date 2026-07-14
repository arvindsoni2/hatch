"""Cloud provider routing catalog and explicit validation evidence."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

CATALOG_PATH = Path(__file__).parents[1] / "config" / "provider_catalog.json"


def provider_catalog() -> dict[str, Any]:
    value = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(value.get("providers"), list):
        raise ValueError("provider catalog is invalid")
    return value


def _provider(provider_id: str) -> dict[str, Any]:
    provider = next(
        (item for item in provider_catalog()["providers"] if item["id"] == provider_id),
        None,
    )
    if provider is None:
        raise ValueError(f"unsupported provider: {provider_id}")
    return provider


def validate_provider_selection(
    provider_id: str,
    primary_model: str | None,
    triage_model: str | None,
) -> tuple[str, str]:
    provider = _provider(provider_id)
    primary = primary_model or provider["primary_model"]
    triage = triage_model or provider["triage_model"]
    allowed = set(provider["models"])
    if primary not in allowed or triage not in allowed:
        raise ValueError(f"Selected model is not in the curated {provider_id} catalog.")
    return primary, triage


def _config_dir() -> Path:
    return Path(os.getenv("HATCH_CONFIG_DIR", "/hatch-home/config"))


def _evidence_path() -> Path:
    return _config_dir() / "provider_validation.json"


def _fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _read_evidence() -> dict[str, Any]:
    try:
        value = json.loads(_evidence_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_evidence(provider_id: str, evidence: dict[str, Any]) -> None:
    path = _evidence_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    values = _read_evidence()
    values[provider_id] = evidence
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def provider_validation_status(
    provider_id: str,
    primary_model: str,
    triage_model: str,
) -> dict[str, Any]:
    provider = _provider(provider_id)
    secret = os.getenv(provider["secret_env"], "")
    evidence = _read_evidence().get(provider_id)
    if not secret:
        return {"status": "missing_secret", "validated_at": None}
    if not isinstance(evidence, dict):
        return {"status": "not_tested", "validated_at": None}
    try:
        validated_at = datetime.fromisoformat(
            str(evidence["validated_at"]).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError):
        return {"status": "not_tested", "validated_at": None}
    ttl = timedelta(hours=float(provider_catalog()["validation_ttl_hours"]))
    matches = (
        evidence.get("secret_fingerprint") == _fingerprint(secret)
        and evidence.get("primary_model") == primary_model
        and evidence.get("triage_model") == triage_model
        and datetime.now(timezone.utc) - validated_at <= ttl
    )
    return {
        "status": "ready" if matches and evidence.get("status") == "ready" else "not_tested",
        "validated_at": evidence.get("validated_at") if matches else None,
    }


def _request(provider_id: str, model: str, secret: str) -> tuple[str, dict[str, str], dict[str, Any]]:
    if provider_id == "anthropic":
        return (
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": secret,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            {"model": model, "max_tokens": 4, "messages": [{"role": "user", "content": "Reply OK."}]},
        )
    if provider_id == "openai":
        return (
            "https://api.openai.com/v1/responses",
            {"authorization": f"Bearer {secret}", "content-type": "application/json"},
            {"model": model, "input": "Reply OK.", "max_output_tokens": 8},
        )
    if provider_id == "google_genai":
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={secret}",
            {"content-type": "application/json"},
            {"contents": [{"parts": [{"text": "Reply OK."}]}], "generationConfig": {"maxOutputTokens": 8}},
        )
    return (
        "https://openrouter.ai/api/v1/chat/completions",
        {
            "authorization": f"Bearer {secret}",
            "content-type": "application/json",
            "x-openrouter-title": "Hatch Setup Test",
        },
        {"model": model, "messages": [{"role": "user", "content": "Reply OK."}], "max_tokens": 8},
    )


async def test_provider_connection(
    provider_id: str,
    primary_model: str | None = None,
    triage_model: str | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    try:
        primary, triage = validate_provider_selection(
            provider_id, primary_model, triage_model
        )
        provider = _provider(provider_id)
    except ValueError as exc:
        return {"ok": False, "status": "invalid_selection", "error": str(exc)}
    secret = os.getenv(provider["secret_env"], "")
    if not secret:
        return {
            "ok": False,
            "status": "missing_secret",
            "error": f"{provider['secret_env']} is not configured.",
            "next_command": f"hatch secrets set {provider_id}",
        }
    url, headers, body = _request(provider_id, primary, secret)
    owned_client = client is None
    active_client = client or httpx.AsyncClient(timeout=httpx.Timeout(20.0))
    try:
        response = await active_client.post(url, headers=headers, json=body)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        status = "invalid_secret" if code in {401, 403} else "provider_unavailable"
        if code == 404:
            status = "model_not_found"
        elif code == 429:
            status = "rate_limited"
        return {"ok": False, "status": status, "error": f"Provider returned HTTP {code}."}
    except httpx.HTTPError:
        return {"ok": False, "status": "provider_unavailable", "error": "Provider request failed."}
    finally:
        if owned_client:
            await active_client.aclose()
    validated_at = datetime.now(timezone.utc).isoformat()
    _write_evidence(provider_id, {
        "status": "ready",
        "primary_model": primary,
        "triage_model": triage,
        "secret_fingerprint": _fingerprint(secret),
        "validated_at": validated_at,
    })
    return {
        "ok": True,
        "status": "ready",
        "provider": provider_id,
        "primary_model": primary,
        "triage_model": triage,
        "validated_at": validated_at,
    }

