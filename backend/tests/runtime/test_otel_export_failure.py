"""Telemetry is observational only and must fail open."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from app.observability.runtime import TelemetryRuntime
from app.runtime.contracts import EvaluationPolicy
from app.runtime.evaluation import EvaluationFinding, EvaluationService
from app.runtime.observability import RuntimeCorrelation, RuntimeTelemetry
from app.runtime.workflow.kernel import WorkflowKernel
from workflow_test_support import synthetic_spec


class _RawSpan:
    def set_attribute(self, *_args: object) -> None:
        return None

    def set_status(self, *_args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_exporter_failure_does_not_change_workflow_result(
    workflow_runtime,
) -> None:
    _unused_kernel, factory = workflow_runtime
    failures = 0
    started: list[dict[str, object]] = []

    class Manager:
        def __enter__(self) -> _RawSpan:
            return _RawSpan()

        def __exit__(self, *_args: object) -> bool:
            nonlocal failures
            failures += 1
            raise RuntimeError("TRANSCRIPT-CANARY at /home/user/private.txt")

    class FailingTracer:
        def start_as_current_span(self, _name: str, **kwargs: object) -> Manager:
            started.append(kwargs)
            return Manager()

    kernel = WorkflowKernel(
        factory,
        lease_duration=timedelta(seconds=30),
        telemetry=RuntimeTelemetry(
            TelemetryRuntime(status="active", tracer=FailingTracer())
        ),
    )
    run = await kernel.start_run(
        synthetic_spec(),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "workflow-contract"},
        mode="new",
    )
    claim = await kernel.claim_next("worker-a", datetime(2030, 1, 1))

    assert run.id
    assert claim is not None
    assert failures == 2
    assert started[0]["attributes"]["hatch.workflow_run_id"] == run.id
    claim_attributes = started[1]["attributes"]
    assert claim_attributes["hatch.workflow_run_id"] == run.id
    assert claim_attributes["hatch.workflow_step_id"]
    assert claim_attributes["hatch.task_attempt_id"] == claim.task_attempt_id
    assert claim_attributes["hatch.task_id"] == "synthetic.workflow"
    assert claim_attributes["hatch.task_version"] == 1
    assert "TRANSCRIPT-CANARY" not in repr(started)


@pytest.mark.asyncio
async def test_slow_exporter_does_not_block_real_workflow(workflow_runtime) -> None:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        SpanExporter,
        SpanExportResult,
    )

    class SlowExporter(SpanExporter):
        def export(self, spans: object) -> SpanExportResult:
            del spans
            time.sleep(0.4)
            return SpanExportResult.SUCCESS

    _unused_kernel, factory = workflow_runtime
    provider = TracerProvider()
    provider.add_span_processor(
        BatchSpanProcessor(
            SlowExporter(),
            schedule_delay_millis=1,
            max_export_batch_size=1,
            export_timeout_millis=1000,
        )
    )
    kernel = WorkflowKernel(
        factory,
        telemetry=RuntimeTelemetry(
            TelemetryRuntime(
                status="active",
                tracer=provider.get_tracer("hatch.runtime.test"),
            )
        ),
    )
    started = time.monotonic()
    run = await kernel.start_run(
        synthetic_spec(),
        input_ref={"input_ref": "synthetic-input"},
        domain_ref={"domain_type": "synthetic", "domain_id": "workflow-contract"},
        mode="new",
    )
    elapsed = time.monotonic() - started
    provider.shutdown()

    assert run.id
    assert elapsed < 0.25


@pytest.mark.asyncio
async def test_evaluation_result_survives_export_failure_with_full_correlation() -> (
    None
):
    failures = 0
    attributes: list[dict[str, object]] = []

    class Manager:
        def __enter__(self) -> _RawSpan:
            return _RawSpan()

        def __exit__(self, *_args: object) -> bool:
            nonlocal failures
            failures += 1
            raise RuntimeError("export_failed")

    class Tracer:
        def start_as_current_span(self, _name: str, **kwargs: object) -> Manager:
            attributes.append(kwargs["attributes"])
            return Manager()

    service = EvaluationService(
        deterministic_validators=(
            lambda _subject: EvaluationFinding.passed("schema_valid"),
        ),
        telemetry=RuntimeTelemetry(TelemetryRuntime(status="active", tracer=Tracer())),
    )
    correlation = RuntimeCorrelation(
        workflow_run_id="run-1",
        workflow_step_id="step-1",
        task_attempt_id="attempt-1",
        execution_id="execution-1",
        task_id="synthetic.evaluate",
        task_version=1,
    )
    result = await service.evaluate(
        object(),
        policy=EvaluationPolicy(max_evaluations=1),
        correlation=correlation,
    )

    assert result.status == "passed"
    assert failures == 1
    assert all(
        attributes[0][key] == value
        for key, value in correlation.trace_attributes().items()
    )
