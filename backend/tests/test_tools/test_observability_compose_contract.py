"""Static contracts for the opt-in local observability profile."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def _compose(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def test_core_compose_does_not_start_or_configure_telemetry() -> None:
    services = _compose("docker-compose.yml")["services"]
    backend_environment = services["backend"]["environment"]

    assert "otel-collector" not in services
    assert all("OBSERVABILITY" not in value for value in backend_environment)
    assert all("OTEL_" not in value for value in backend_environment)


def test_core_image_does_not_install_optional_observability_sdk() -> None:
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    core_stage = dockerfile.split("FROM runtime-base AS core", 1)[1].split(
        "FROM runtime-base AS browser",
        1,
    )[0]
    core_requirements = (ROOT / "backend" / "requirements-core.txt").read_text(
        encoding="utf-8"
    )

    assert "observability-builder" not in core_stage
    assert "requirements-observability" not in core_stage
    assert "opentelemetry" not in core_requirements.casefold()


def test_observability_overlay_is_explicit_and_locally_scoped() -> None:
    services = _compose("docker-compose.observability.yml")["services"]
    backend = services["backend"]
    collector = services["otel-collector"]

    assert backend["build"]["target"] == "observability"
    assert backend["environment"]["HATCH_BACKEND_PROFILE"] == "observability"
    assert backend["environment"]["HATCH_OBSERVABILITY_ENABLED"] == "1"
    assert backend["environment"]["HATCH_OTLP_ENDPOINT"] == "http://otel-collector:4317"
    assert collector["image"] == "otel/opentelemetry-collector-contrib:0.153.0"
    assert collector["profiles"] == ["observability"]
    assert collector["ports"] == ["127.0.0.1:8889:8889"]
    assert collector["networks"] == ["hatch"]


def test_collector_accepts_otlp_and_exports_only_local_debug_data() -> None:
    config = yaml.safe_load(
        (ROOT / "infrastructure" / "observability" / "otel-collector.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert (
        config["receivers"]["otlp"]["protocols"]["grpc"]["endpoint"] == "0.0.0.0:4317"
    )
    assert set(config["exporters"]) == {"debug", "prometheus"}
    assert config["service"]["pipelines"]["traces"]["exporters"] == ["debug"]
    assert config["service"]["pipelines"]["metrics"]["exporters"] == [
        "debug",
        "prometheus",
    ]
