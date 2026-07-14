#!/usr/bin/env python3
"""Host-side Hatch easy-install command line interface."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HATCH_HOME = Path(os.getenv("HATCH_HOME", Path.home() / ".hatch")).expanduser().resolve()
CONFIG_DIR = HATCH_HOME / "config"
MODELS_DIR = HATCH_HOME / "models"
PROBE_DIR = HATCH_HOME / "probe"
LOGS_DIR = HATCH_HOME / "logs"
BACKUPS_DIR = HATCH_HOME / "backups"
CATALOG_PATH = ROOT / "backend" / "app" / "config" / "model_catalog.json"
RUNTIME_PATH = CONFIG_DIR / "ai_runtime.json"
INTENT_PATH = CONFIG_DIR / "ai_setup_intent.json"
SECRETS_PATH = CONFIG_DIR / "secrets.env"
INSTALL_PATH = CONFIG_DIR / "install.json"
BACKEND_CAPABILITIES_PATH = CONFIG_DIR / "backend_capabilities.json"
PROVIDERS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "google_gemini": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "azure_openai": "AZURE_OPENAI_API_KEY",
}
PROVIDER_ALIASES = {
    "google": "google_genai",
    "google_gemini": "google_genai",
}
BACKEND_PROFILE_ENABLED = {
    "core": [],
    "browser": ["browser"],
    "local-embeddings": ["local-embeddings"],
    "full": ["browser", "local-embeddings", "perception", "advanced-coach"],
}
BACKEND_PROFILE_COMPOSE = {
    "core": None,
    "browser": "docker-compose.browser.yml",
    "local-embeddings": "docker-compose.local-embeddings.yml",
    "full": "docker-compose.full.yml",
}


def enabled_capabilities_for_profile(profile: str) -> list[str]:
    try:
        return list(BACKEND_PROFILE_ENABLED[profile])
    except KeyError:
        fail(f"Unsupported backend capability profile: {profile}")


def default_backend_capabilities() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profile": "core",
        "enabled": [],
        "updated_at": None,
        "updated_by": "default",
    }


def read_backend_capabilities() -> dict[str, Any]:
    try:
        payload = json.loads(BACKEND_CAPABILITIES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default_backend_capabilities()
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[hatch] Invalid backend capability config; using core: {exc}", file=sys.stderr)
        return default_backend_capabilities()

    profile = payload.get("profile", "core")
    if profile not in BACKEND_PROFILE_ENABLED:
        print(
            f"[hatch] Unsupported backend capability profile '{profile}'; using core.",
            file=sys.stderr,
        )
        return default_backend_capabilities()
    return {
        "schema_version": 1,
        "profile": profile,
        "enabled": enabled_capabilities_for_profile(profile),
        "updated_at": payload.get("updated_at"),
        "updated_by": payload.get("updated_by", "unknown"),
    }


def write_backend_capabilities(profile: str, *, updated_by: str) -> None:
    if profile not in BACKEND_PROFILE_ENABLED:
        fail(
            "Unsupported backend capability profile: "
            f"{profile}. Choose: {', '.join(BACKEND_PROFILE_ENABLED)}"
        )
    write_json(BACKEND_CAPABILITIES_PATH, {
        "schema_version": 1,
        "profile": profile,
        "enabled": enabled_capabilities_for_profile(profile),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": updated_by,
    })


def ensure_home() -> None:
    for path in (CONFIG_DIR, MODELS_DIR, PROBE_DIR, LOGS_DIR, BACKUPS_DIR, HATCH_HOME / "bin"):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def catalog() -> list[dict[str, Any]]:
    value = read_json(CATALOG_PATH, [])
    if not value:
        fail(f"Model catalogue is unavailable: {CATALOG_PATH}")
    return value


def fail(message: str, code: int = 1) -> None:
    print(f"[hatch] {message}", file=sys.stderr)
    raise SystemExit(code)


def run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=ROOT, check=check, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        env=env,
    )


def compose_files(local: bool | None = None, backend_profile: str | None = None) -> list[str]:
    if local is None:
        local = read_json(RUNTIME_PATH, {}).get("ai_mode") == "local"
    profile = backend_profile or read_backend_capabilities()["profile"]
    if profile not in BACKEND_PROFILE_COMPOSE:
        print(
            f"[hatch] Unsupported backend capability profile '{profile}'; using core.",
            file=sys.stderr,
        )
        profile = "core"
    files = ["-f", str(ROOT / "docker-compose.easy.yml")]
    compose_file = BACKEND_PROFILE_COMPOSE[profile]
    if compose_file:
        files += ["-f", str(ROOT / compose_file)]
    if local:
        files += ["-f", str(ROOT / "docker-compose.local-ai.yml")]
        runtime = read_json(RUNTIME_PATH, {})
        if runtime.get("primary_model_id"):
            files += ["--profile", "local-primary"]
        if runtime.get("triage_model_id"):
            files += ["--profile", "local-triage"]
    return files


def compose(action: str, extra: list[str] | None = None) -> None:
    environment = os.environ.copy()
    models = {model["id"]: model for model in catalog()}
    runtime = read_json(RUNTIME_PATH, {})
    primary = models.get(runtime.get("primary_model_id"))
    triage = models.get(runtime.get("triage_model_id"))
    if primary:
        environment["HATCH_PRIMARY_MODEL_FILE"] = primary["filename"]
    if triage:
        environment["HATCH_TRIAGE_MODEL_FILE"] = triage["filename"]
    run(
        ["docker", "compose", *compose_files(), action, *(extra or [])],
        env=environment,
    )


def host_os() -> str:
    value = platform.system().lower()
    return {"darwin": "macos"}.get(value, value if value in {"linux", "windows"} else "unknown")


def host_arch() -> str:
    value = platform.machine().lower()
    return {"amd64": "x86_64", "aarch64": "arm64"}.get(value, value)


def total_ram_gb() -> float:
    if sys.platform.startswith("linux"):
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024 / 1024, 2)
    if sys.platform == "darwin":
        return round(int(run(["sysctl", "-n", "hw.memsize"], capture=True).stdout) / 1024**3, 2)
    if os.name == "nt":
        import ctypes  # noqa: PLC0415
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended", ctypes.c_ulonglong),
            ]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return round(status.total_phys / 1024**3, 2)
    return 0


def port_status(port: int) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return "available" if sock.connect_ex(("127.0.0.1", port)) != 0 else "occupied"


def model_buckets(ram: float, disk: float) -> dict[str, list[str]]:
    result = {"recommended": [], "compatible": [], "not_recommended": []}
    for model in catalog():
        supported = host_os() in model["supported_os"] and host_arch() in {
            "arm64" if arch == "aarch64" else arch for arch in model["supported_arch"]
        }
        if not supported or ram < model["min_ram_gb"] or disk < model["disk_required_gb"]:
            result["not_recommended"].append(model["id"])
        elif ram >= model["recommended_ram_gb"]:
            result["recommended"].append(model["id"])
        else:
            result["compatible"].append(model["id"])
    return result


def migrate_legacy_probe() -> bool:
    """Copy a valid legacy probe into the canonical directory once."""
    canonical = PROBE_DIR / "hardware_probe_latest.json"
    legacy = CONFIG_DIR / "hardware_probe_latest.json"
    if canonical.exists() or not legacy.is_file():
        return False
    snapshot = read_json(legacy, None)
    if not isinstance(snapshot, dict) or snapshot.get("sanitised") is not True:
        return False
    write_json(canonical, snapshot)
    return True


def cmd_probe(_: argparse.Namespace) -> None:
    ensure_home()
    migrate_legacy_probe()
    disk = round(shutil.disk_usage(MODELS_DIR).free / 1024**3, 2)
    ram = total_ram_gb()
    generated_at = datetime.now(timezone.utc).isoformat()
    buckets = model_buckets(ram, disk)
    snapshot = {
        "schema_version": 1, "generated_at": generated_at,
        "source": "hatch_host_probe", "sanitised": True,
        "platform": {
            "os_family": host_os(), "os_name": platform.system(),
            "os_version_major": platform.release().split(".")[0], "arch": host_arch(),
        },
        "cpu": {
            "logical_cores": os.cpu_count() or 0, "physical_cores": 0,
            "model_summary": platform.processor() or None,
        },
        "memory": {"total_gb": ram, "available_gb": 0},
        "storage": {"hatch_home_free_gb": disk, "models_dir_free_gb": disk},
        "gpu": {
            "detected": False, "vendor": None, "model_summary": None,
            "vram_gb": 0, "detection_confidence": "unknown",
        },
        "docker": {
            "docker_available": shutil.which("docker") is not None,
            "docker_running": docker_running(),
            "compose_available": compose_available(),
        },
        "ports": {
            str(port): {"status": port_status(port), "purpose": purpose}
            for port, purpose in {
                3000: "frontend", 8000: "backend",
                8080: "llm_primary", 8081: "llm_triage",
            }.items()
        },
        "model_support": {
            "recommended_model_ids": buckets["recommended"],
            "compatible_model_ids": buckets["compatible"],
            "not_recommended_model_ids": buckets["not_recommended"],
        },
        "warnings": [],
    }
    write_json(PROBE_DIR / "hardware_probe_latest.json", snapshot)
    print(f"Hardware probe saved. RAM: {ram} GB; model storage free: {disk} GB")


def docker_running() -> bool:
    if not shutil.which("docker"):
        return False
    return run(["docker", "info"], check=False, capture=True).returncode == 0


def compose_available() -> bool:
    if not shutil.which("docker"):
        return False
    return run(["docker", "compose", "version"], check=False, capture=True).returncode == 0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cmd_models_list(_: argparse.Namespace) -> None:
    snapshot = read_json(PROBE_DIR / "hardware_probe_latest.json", {})
    if not snapshot:
        snapshot = read_json(CONFIG_DIR / "hardware_probe_latest.json", {})
    support = snapshot.get("model_support", {})
    for model in catalog():
        bucket = next(
            (name for name, ids in support.items() if model["id"] in ids),
            "not_probed",
        ).replace("_model_ids", "")
        status = "ready" if (MODELS_DIR / model["filename"]).is_file() else "not downloaded"
        print(f"{model['id']}: {bucket}; {status}; {model['download_size_gb']} GB")


def download_model(model: dict[str, Any]) -> None:
    ensure_home()
    destination = MODELS_DIR / model["filename"]
    if destination.exists() and sha256(destination) == model["sha256"]:
        print(f"{model['display_name']} is already ready.")
        return
    url = model["download_url_template"].format(source_revision=model["source_revision"])
    partial = destination.with_suffix(destination.suffix + ".part")
    print(f"Downloading {model['display_name']} ({model['download_size_gb']} GB)…")
    try:
        urllib.request.urlretrieve(url, partial)
        if sha256(partial) != model["sha256"]:
            fail(f"Checksum verification failed for {model['filename']}")
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)


def cmd_models_install(args: argparse.Namespace) -> None:
    available = {model["id"]: model for model in catalog()}
    ids = args.model_ids or []
    if not ids:
        cmd_models_list(args)
        entered = input("Model IDs to install (comma-separated): ").strip()
        ids = [value.strip() for value in entered.split(",") if value.strip()]
    unknown = set(ids) - set(available)
    if unknown:
        fail(f"Unknown model IDs: {', '.join(sorted(unknown))}")
    total = sum(available[model_id]["download_size_gb"] for model_id in ids)
    if not args.yes and input(f"Download about {total:.2f} GB? [y/N] ").lower() != "y":
        fail("Cancelled.", 2)
    for model_id in ids:
        download_model(available[model_id])
    write_json(INTENT_PATH, {
        "schema_version": 1, "ai_mode": "local", "selected_model_ids": ids,
        "provider": None, "provider_metadata": {}, "restart_required": True,
    })
    print("Models are ready. Run: hatch apply-ai-config")


def cmd_models_remove(args: argparse.Namespace) -> None:
    available = {model["id"]: model for model in catalog()}
    model = available.get(args.model_id)
    if model is None:
        fail(f"Unknown model ID: {args.model_id}")
    runtime = read_json(RUNTIME_PATH, {})
    intent = read_json(INTENT_PATH, {})
    active = args.model_id in {
        runtime.get("primary_model_id"),
        runtime.get("triage_model_id"),
        *intent.get("selected_model_ids", []),
    }
    if active and not (args.clear_ai or args.degrade or args.replace_with):
        fail("Model is active. Use --replace-with, --degrade, or --clear-ai.")
    if active:
        selected = [
            value for value in intent.get("selected_model_ids", [])
            if value != args.model_id
        ]
        if args.replace_with:
            replacement = available.get(args.replace_with)
            if replacement is None:
                fail(f"Unknown replacement model ID: {args.replace_with}")
            if not (MODELS_DIR / replacement["filename"]).is_file():
                fail("Replacement model is not ready.")
            selected.append(args.replace_with)
        if args.clear_ai:
            next_intent = {
                "schema_version": 1, "ai_mode": "not_configured",
                "selected_model_ids": [], "provider": None,
                "provider_metadata": {}, "restart_required": True,
            }
            next_runtime = base_runtime("not_configured")
        else:
            if not selected:
                fail("No valid fallback remains; use --clear-ai.")
            next_intent = {
                **intent, "ai_mode": "local",
                "selected_model_ids": list(dict.fromkeys(selected)),
                "restart_required": True,
            }
            next_runtime = runtime_for_local(next_intent["selected_model_ids"])
        # Persist the safe replacement/fallback before deleting the file.
        write_json(INTENT_PATH, next_intent)
        write_json(RUNTIME_PATH, next_runtime)
    path = MODELS_DIR / model["filename"]
    if not args.yes and input(f"Remove {path.name}? [y/N] ").lower() != "y":
        fail("Cancelled.", 2)
    path.unlink(missing_ok=True)
    print(f"Removed {model['display_name']}")


def runtime_for_local(ids: list[str]) -> dict[str, Any]:
    available = {model["id"]: model for model in catalog()}
    ready = [
        model_id for model_id in ids
        if model_id in available and (MODELS_DIR / available[model_id]["filename"]).is_file()
    ]
    primaries = [value for value in ready if available[value]["role"] == "combined_capable_primary"]
    triages = [value for value in ready if available[value]["role"] == "triage"]
    primary = next((value for value in primaries if "8b-" in value), None)
    primary = primary or next((value for value in primaries if "4b-" in value), None)
    triage = triages[0] if triages else None
    if primary:
        combined = triage is None
        quality = "balanced_local" if "8b-" in primary else "compact_local"
        if combined:
            quality = "balanced_local_combined" if "8b-" in primary else "compact_local_combined"
        return {
            "schema_version": 1, "ai_mode": "local", "quality_mode": quality,
            "primary_model_id": primary, "triage_model_id": triage,
            "effective_routing": {"primary": primary, "triage": triage or primary},
            "provider": None,
            "feature_gates": {
                "cv_tailoring": True, "cover_letter_generation": True,
                "coach_interview_prep": True,
            },
            "warnings": ["Primary model is also serving triage tasks."] if combined else [],
        }
    if triage:
        return {
            "schema_version": 1, "ai_mode": "local", "quality_mode": "triage_only",
            "primary_model_id": None, "triage_model_id": triage,
            "effective_routing": {"primary": None, "triage": triage},
            "provider": None,
            "feature_gates": {
                "cv_tailoring": False, "cover_letter_generation": False,
                "coach_interview_prep": False,
            },
            "warnings": ["Quality-sensitive features are disabled in triage-only mode."],
        }
    fail("No selected, checksum-verified model files are ready.")


def cmd_apply(args: argparse.Namespace) -> None:
    ensure_home()
    intent = read_json(INTENT_PATH, {"ai_mode": "not_configured"})
    mode = intent.get("ai_mode", "not_configured")
    if mode == "local":
        runtime = runtime_for_local(intent.get("selected_model_ids", []))
    elif mode == "cloud":
        provider = canonical_provider(intent.get("provider"))
        env_name = provider_env(provider)
        if not env_name or env_name not in read_env(SECRETS_PATH):
            fail(f"Cloud secret is missing. Run: hatch secrets set {provider}")
        runtime = base_runtime("cloud", provider=provider)
    elif mode == "custom":
        runtime = base_runtime("custom")
    else:
        runtime = base_runtime("not_configured")
    write_json(RUNTIME_PATH, runtime)
    restart = bool(getattr(args, "restart", False))
    intent["provider"] = canonical_provider(intent.get("provider")) if intent.get("provider") else None
    intent["restart_required"] = not restart
    write_json(INTENT_PATH, intent)
    print(f"Applied AI mode: {runtime['ai_mode']}")
    if restart:
        compose("up", ["-d", "--build"])
    elif not args.no_restart:
        print("Restart required. Run: hatch restart")


def base_runtime(mode: str, provider: str | None = None) -> dict[str, Any]:
    enabled = mode in {"cloud", "custom"}
    return {
        "schema_version": 1, "ai_mode": mode, "quality_mode": mode,
        "primary_model_id": None, "triage_model_id": None,
        "effective_routing": {"primary": None, "triage": None},
        "provider": provider,
        "feature_gates": {
            "cv_tailoring": enabled, "cover_letter_generation": enabled,
            "coach_interview_prep": enabled,
        },
        "warnings": [],
    }


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                result[key] = value
    except FileNotFoundError:
        pass
    return result


def write_env(values: dict[str, str]) -> None:
    if any("\n" in key or "\n" in value for key, value in values.items()):
        fail("Secret values must not contain newlines.")
    SECRETS_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = SECRETS_PATH.with_suffix(".tmp")
    temporary.write_text("".join(f"{key}={value}\n" for key, value in sorted(values.items())))
    os.chmod(temporary, 0o600)
    os.replace(temporary, SECRETS_PATH)


def provider_env(provider: str) -> str:
    provider = canonical_provider(provider)
    try:
        return PROVIDERS[provider]
    except KeyError:
        fail(f"Unsupported provider: {provider}. Choose: {', '.join(sorted(PROVIDERS))}")


def canonical_provider(provider: str | None) -> str:
    value = (provider or "").strip().lower()
    return PROVIDER_ALIASES.get(value, value)


def cmd_secrets(args: argparse.Namespace) -> None:
    values = read_env(SECRETS_PATH)
    if args.secret_action == "status":
        for provider, env_name in sorted(PROVIDERS.items()):
            print(f"{provider}: {'configured' if values.get(env_name) else 'not configured'}")
    elif args.secret_action == "set":
        provider = canonical_provider(args.provider)
        env_name = provider_env(provider)
        value = getpass.getpass(f"{env_name}: ").strip()
        if not value or "\n" in value or "\r" in value:
            fail("Secret must be non-empty and contain no newlines.")
        values[env_name] = value
        write_env(values)
        print(f"{provider}: configured")
    elif args.secret_action == "unset":
        provider = canonical_provider(args.provider)
        env_name = provider_env(provider)
        if not args.yes and input(f"Remove {provider} secret? [y/N] ").lower() != "y":
            fail("Cancelled.", 2)
        values.pop(env_name, None)
        write_env(values)
        print(f"{provider}: removed")


def cmd_status(_: argparse.Namespace) -> None:
    runtime = read_json(RUNTIME_PATH, base_runtime("not_configured"))
    capabilities = read_backend_capabilities()
    result = run(["docker", "compose", *compose_files(), "ps", "--format", "json"], check=False, capture=True)
    print("Hatch status")
    print(f"Services: {'available' if result.returncode == 0 else 'stopped or unavailable'}")
    print(f"AI mode: {runtime.get('ai_mode', 'not_configured')}")
    print(f"Backend capability profile: {capabilities['profile']}")
    print(f"Local models: {sum(1 for model in catalog() if (MODELS_DIR / model['filename']).is_file())} ready")
    print("Optional backend capabilities:")
    enabled = set(capabilities["enabled"])
    print(f"  Browser automation: {'installed' if 'browser' in enabled else 'not installed'}")
    print(f"  Local embeddings: {'installed' if 'local-embeddings' in enabled else 'not installed'}")
    print(
        "  Perception/advanced coach extras: "
        f"{'installed' if 'perception' in enabled else 'not installed'}"
    )


def cmd_capabilities_list(_: argparse.Namespace) -> None:
    current = read_backend_capabilities()["profile"]
    print("Backend capability profiles:")
    print("  core              Smallest backend image. Recommended for most users.")
    print("  browser           Adds Playwright/browser automation for supported imports.")
    print("  local-embeddings  Adds local semantic embedding packages.")
    print("  full              Adds browser, local embeddings, perception, and advanced coach packages.")
    print("")
    print(f"Current profile: {current}")


def cmd_capabilities_status(_: argparse.Namespace) -> None:
    capabilities = read_backend_capabilities()
    profile = capabilities["profile"]
    enabled = set(capabilities["enabled"])
    print(f"Backend capability profile: {profile}")
    print(
        "Enabled backend packages: "
        f"{', '.join(capabilities['enabled']) if capabilities['enabled'] else 'none'}"
    )
    print("")
    print("Available optional backend capabilities:")
    print(f"  Browser automation: {'installed' if 'browser' in enabled else 'not installed'}")
    print(f"  Local embeddings: {'installed' if 'local-embeddings' in enabled else 'not installed'}")
    print(
        "  Perception/advanced coach extras: "
        f"{'installed' if 'perception' in enabled else 'not installed'}"
    )
    print("")
    print("Enable commands:")
    print("  hatch capabilities enable browser")
    print("  hatch capabilities enable local-embeddings")
    print("  hatch capabilities enable full")


def _confirm_capability_change(current: str, target: str, args: argparse.Namespace) -> None:
    if args.yes:
        return
    print(f"This will switch the backend capability profile from {current} to {target}.")
    print("It may download/build a larger backend image with optional backend dependencies.")
    if args.restart_all:
        print("The full selected stack will be recreated.")
    elif args.no_restart:
        print("Services will not be restarted until you run hatch start or hatch restart.")
    else:
        print("The frontend and local model services will not be restarted.")
    if input("Continue? [y/N] ").lower() != "y":
        fail("Cancelled.", 2)


def cmd_capabilities_enable(args: argparse.Namespace) -> None:
    profile = args.profile
    if profile not in BACKEND_PROFILE_ENABLED:
        fail(
            "Unsupported backend capability profile: "
            f"{profile}. Choose: {', '.join(BACKEND_PROFILE_ENABLED)}"
        )
    current = read_backend_capabilities()["profile"]
    _confirm_capability_change(current, profile, args)
    write_backend_capabilities(profile, updated_by="hatch_cli")
    print(f"Backend capability profile set to: {profile}")
    if args.no_restart:
        print("Restart required. Run: hatch restart")
        return
    if args.restart_all:
        print("Recreating selected Hatch stack...")
        compose("up", ["-d", "--build"])
    else:
        print("Recreating backend with selected capability profile...")
        compose("up", ["-d", "--build", "backend"])
    cmd_capabilities_status(args)


def cmd_capabilities_disable(args: argparse.Namespace) -> None:
    args.profile = "core"
    cmd_capabilities_enable(args)


def cmd_doctor(_: argparse.Namespace) -> None:
    checks = {
        "Docker installed": shutil.which("docker") is not None,
        "Docker running": docker_running(),
        "Docker Compose": compose_available(),
        "Install directory": ROOT.exists(),
        "Config directory": CONFIG_DIR.exists(),
        "Profile": (ROOT / "data" / "profile.yaml").exists(),
    }
    for label, passed in checks.items():
        print(f"{label}: {'OK' if passed else 'needs attention'}")
    if not all(checks.values()):
        raise SystemExit(1)


def cmd_update(args: argparse.Namespace) -> None:
    install = read_json(INSTALL_PATH, {})
    source = Path(install.get("source_dir", ROOT)).resolve()
    if source != ROOT or not install.get("managed", False):
        fail("This is not a managed easy-install checkout. Update it manually.")
    dirty = run(["git", "status", "--porcelain"], capture=True).stdout.strip()
    if dirty:
        fail("Managed checkout has uncommitted changes; update refused.")
    commands = [["git", "fetch", "--all", "--tags"], ["git", "pull", "--ff-only"]]
    if args.dry_run:
        profile = read_backend_capabilities()["profile"]
        print(
            "Would back up config/data, fetch the configured branch, validate "
            f"Compose for backend profile '{profile}', and restart services."
        )
        return
    backup = BACKUPS_DIR / f"update-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    backup.mkdir(parents=True)
    for path in (CONFIG_DIR, ROOT / "data"):
        if path.exists():
            shutil.copytree(path, backup / path.name, dirs_exist_ok=True)
    for command in commands:
        run(command)
    run(["docker", "compose", *compose_files(), "config", "--quiet"])
    if not args.no_restart:
        compose("up", ["-d", "--build"])


def cmd_uninstall(args: argparse.Namespace) -> None:
    run(["docker", "compose", *compose_files(), "down"], check=False)
    shim = HATCH_HOME / "bin" / ("hatch.cmd" if os.name == "nt" else "hatch")
    shim.unlink(missing_ok=True)
    purge = any((args.purge_config, args.purge_models, args.purge_secrets, args.purge_data, args.purge_all))
    if not purge:
        print(f"Hatch services removed. User data preserved at {HATCH_HOME}")
        return
    if not args.yes:
        if input(f"Type DELETE HATCH DATA to remove selected data under {HATCH_HOME}: ") != "DELETE HATCH DATA":
            fail("Confirmation did not match.", 2)
    if args.purge_all:
        shutil.rmtree(HATCH_HOME)
        return
    if args.purge_models:
        shutil.rmtree(MODELS_DIR, ignore_errors=True)
    if args.purge_secrets:
        SECRETS_PATH.unlink(missing_ok=True)
    if args.purge_config:
        for path in CONFIG_DIR.glob("*"):
            if path != SECRETS_PATH:
                path.unlink(missing_ok=True)
    if args.purge_data:
        shutil.rmtree(ROOT / "data", ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="hatch")
    sub = root.add_subparsers(dest="command", required=True)
    for name in ("start", "stop", "restart", "logs", "status", "doctor", "probe"):
        sub.add_parser(name)
    apply_parser = sub.add_parser("apply-ai-config")
    apply_parser.add_argument("--yes", action="store_true")
    restart = apply_parser.add_mutually_exclusive_group()
    restart.add_argument("--restart", action="store_true")
    restart.add_argument("--no-restart", action="store_true")
    models = sub.add_parser("models")
    models_sub = models.add_subparsers(dest="models_action", required=True)
    models_sub.add_parser("list")
    install = models_sub.add_parser("install")
    install.add_argument("model_ids", nargs="*")
    install.add_argument("--yes", action="store_true")
    remove = models_sub.add_parser("remove")
    remove.add_argument("model_id")
    removal = remove.add_mutually_exclusive_group()
    removal.add_argument("--clear-ai", action="store_true")
    removal.add_argument("--degrade", action="store_true")
    removal.add_argument("--replace-with")
    remove.add_argument("--yes", action="store_true")
    secrets = sub.add_parser("secrets")
    secrets_sub = secrets.add_subparsers(dest="secret_action", required=True)
    secrets_sub.add_parser("status")
    set_secret = secrets_sub.add_parser("set")
    set_secret.add_argument("provider")
    unset_secret = secrets_sub.add_parser("unset")
    unset_secret.add_argument("provider")
    unset_secret.add_argument("--yes", action="store_true")
    update = sub.add_parser("update")
    update.add_argument("--dry-run", action="store_true")
    update.add_argument("--no-restart", action="store_true")
    capabilities = sub.add_parser("capabilities")
    capabilities_sub = capabilities.add_subparsers(dest="capabilities_action", required=True)
    capabilities_sub.add_parser("list")
    capabilities_sub.add_parser("status")
    enable = capabilities_sub.add_parser("enable")
    enable.add_argument("profile", choices=sorted(BACKEND_PROFILE_ENABLED))
    enable.add_argument("--yes", action="store_true")
    enable_restart = enable.add_mutually_exclusive_group()
    enable_restart.add_argument("--no-restart", action="store_true")
    enable_restart.add_argument("--restart-all", action="store_true")
    disable = capabilities_sub.add_parser("disable")
    disable.add_argument("--yes", action="store_true")
    disable_restart = disable.add_mutually_exclusive_group()
    disable_restart.add_argument("--no-restart", action="store_true")
    disable_restart.add_argument("--restart-all", action="store_true")
    uninstall = sub.add_parser("uninstall")
    uninstall.add_argument("--yes", action="store_true")
    uninstall.add_argument("--purge-config", action="store_true")
    uninstall.add_argument("--purge-models", action="store_true")
    uninstall.add_argument("--purge-secrets", action="store_true")
    uninstall.add_argument("--purge-data", action="store_true")
    uninstall.add_argument("--purge-all", action="store_true")
    return root


def main() -> None:
    args = parser().parse_args()
    ensure_home()
    if args.command == "start":
        compose("up", ["-d", "--build"])
    elif args.command == "stop":
        compose("down")
    elif args.command == "restart":
        compose("up", ["-d", "--build", "--force-recreate"])
    elif args.command == "logs":
        compose("logs", ["-f"])
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "probe":
        cmd_probe(args)
    elif args.command == "models":
        {
            "list": cmd_models_list,
            "install": cmd_models_install,
            "remove": cmd_models_remove,
        }[args.models_action](args)
    elif args.command == "apply-ai-config":
        cmd_apply(args)
    elif args.command == "secrets":
        cmd_secrets(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "capabilities":
        {
            "list": cmd_capabilities_list,
            "status": cmd_capabilities_status,
            "enable": cmd_capabilities_enable,
            "disable": cmd_capabilities_disable,
        }[args.capabilities_action](args)
    elif args.command == "uninstall":
        cmd_uninstall(args)


if __name__ == "__main__":
    main()
