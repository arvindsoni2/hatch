from __future__ import annotations

from contextlib import contextmanager

import pytest

from benchmarks import runner
from benchmarks.runner import run_benchmark
from tests.benchmarks.test_runner import CASE, FakeClient


@pytest.mark.asyncio
async def test_benchmark_pair_uses_controlled_correlation_attributes(
    tmp_path,
    monkeypatch,
) -> None:
    spans: list[tuple[str, dict[str, object]]] = []

    class Span:
        def __init__(self, attributes):
            self.attributes = attributes

        def set_attribute(self, key, value) -> None:
            self.attributes[key] = value

    class Telemetry:
        @contextmanager
        def workflow_span(self, workflow, attributes=None):
            current = dict(attributes or {})
            spans.append((workflow, current))
            yield Span(current)

        @contextmanager
        def stage_span(self, _workflow, _stage, _attributes=None):
            yield Span({})

        def record_model_call(self, **_kwargs) -> None:
            return None

        def record_repair(self, *_args, **_kwargs) -> None:
            return None

        def record_validation_failure(self, *_args, **_kwargs) -> None:
            return None

    telemetry = Telemetry()
    monkeypatch.setattr(runner, "get_telemetry", lambda: telemetry)
    monkeypatch.setattr(
        "app.observability.runtime.get_telemetry",
        lambda: telemetry,
    )
    monkeypatch.setattr(
        runner,
        "_probe_http",
        lambda url: {"url": url, "status_code": 204},
    )
    order: list[tuple[str, int]] = []

    await run_benchmark(
        CASE,
        model_ids=["qwen35-4b"],
        repetitions=1,
        output_root=tmp_path,
        adapter_factory=lambda spec, seed: FakeClient(spec, seed, order),
        run_id="otel-run",
    )

    pair = next(item for item in spans if item[0] == "benchmark_pair")
    assert pair[1] == {
        "hatch.ai.benchmark.run_id": "otel-run",
        "hatch.ai.benchmark.case_id": "synthetic-delivery",
        "hatch.ai.benchmark.seed": 11,
        "hatch.ai.model.id": "qwen35-4b",
        "hatch.ai.prompt.version": "2.0.0",
        "hatch.ai.validation.state": "passed",
        "hatch.ai.attempt.number": 1,
    }
    serialized = str(pair)
    assert "alex@example.test" not in serialized
    assert CASE.job_description not in serialized
