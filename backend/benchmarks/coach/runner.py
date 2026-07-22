"""Sequential, resumable Coach benchmark execution with bounded deadlines."""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from pydantic import Field

from app.config import settings
from app.services.profile_service import current_profile_hash
from benchmarks.adapters import BenchmarkLLMClient
from benchmarks.contracts import ModelSpec, StrictModel

from .artifacts import (
    atomic_write_json,
    atomic_write_text,
    git_state,
    hash_file,
    hash_sqlite_state,
    stable_identity,
)
from .contracts import (
    CoachProfile,
    CoachRunSummary,
    DimensionResult,
    GateFinding,
    ScenarioResult,
    ScheduleEntry,
)
from .production_adapter import (
    CoachProductionAdapter,
    HarnessFailureClient,
    ScenarioContext,
)
from .profiles import profile_for
from .scoring import classify_model, rank_models, score_execution
from .suite_loader import LoadedCoachSuite, load_suite
from .validators import validate_execution


class RunRequest(StrictModel):
    suite_path: Path
    output_root: Path
    profile_name: Literal[
        "contract-smoke", "acceptance-smoke", "standard", "extended"
    ]
    model_ids: tuple[str, ...] = Field(min_length=1)
    command: str = Field(min_length=1)
    call_timeout_seconds: float | None = Field(default=None, gt=0)
    model_timeout_seconds: float | None = Field(default=None, gt=0)
    run_timeout_seconds: float | None = Field(default=None, gt=0)


@asynccontextmanager
async def _default_adapter_factory(
    spec: ModelSpec, seed: int
) -> AsyncIterator[object]:
    client = BenchmarkLLMClient(spec, seed)
    try:
        yield client
    finally:
        await client.aclose()


@dataclass(frozen=True)
class RunnerDependencies:
    adapter_factory: Callable[[ModelSpec, int], Any] = _default_adapter_factory
    production_adapter: Any = None
    monotonic: Callable[[], float] = time.monotonic

    def adapter(self) -> Any:
        return self.production_adapter or CoachProductionAdapter()


def build_schedule(
    suite: LoadedCoachSuite,
    profile: CoachProfile,
    model_ids: Sequence[str],
) -> tuple[ScheduleEntry, ...]:
    known = {item.id for item in suite.models}
    unknown = set(model_ids) - known
    if unknown:
        raise ValueError("unknown Coach model: " + ", ".join(sorted(unknown)))
    scenario_ids = profile.scenario_ids or tuple(suite.scenarios)
    schedule: list[ScheduleEntry] = []
    for model_id in model_ids:
        for repetition in range(1, profile.repetitions + 1):
            seed = suite.seeds[(repetition - 1) % len(suite.seeds)]
            for scenario_id in scenario_ids:
                scenario = suite.scenario(scenario_id)
                schedule.append(
                    ScheduleEntry(
                        attempt_id=f"{model_id}--{scenario_id}--r{repetition}",
                        model_id=model_id,
                        scenario_id=scenario_id,
                        stage=scenario.stage,
                        qualification_scope=scenario.qualification_scope,
                        repetition=repetition,
                        seed=seed,
                    )
                )
    return tuple(schedule)


def _relative(path: Path) -> str:
    return Path(os.path.relpath(path.resolve(), Path.cwd().resolve())).as_posix()


def _database_path() -> Path | None:
    url = settings.DATABASE_URL
    if not url.startswith("sqlite"):
        return None
    parsed = urlparse(url)
    raw = unquote(parsed.path or "")
    if raw.startswith("//"):
        raw = raw[1:]
    elif raw.startswith("/"):
        raw = raw[1:]
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else Path.cwd() / path


def _protected_hashes() -> dict[str, str]:
    database = _database_path()
    return {
        "profile": current_profile_hash() or "not_recorded",
        "database": (
            hash_sqlite_state(database)
            if database is not None and database.exists()
            else "not_recorded"
        ),
    }


def _identity_payload(
    suite: LoadedCoachSuite,
    profile: CoachProfile,
    request: RunRequest,
) -> dict[str, Any]:
    timeouts = _timeout_limits(request, profile)
    return {
        "suite_id": suite.suite_id,
        "suite_version": suite.version,
        "input_hashes": suite.input_hashes,
        "profile": profile.model_dump(mode="json"),
        "model_ids": list(request.model_ids),
        "timeouts": {
            "call": timeouts[0],
            "model": timeouts[1],
            "run": timeouts[2],
        },
    }


def _timeout_limits(
    request: RunRequest, profile: CoachProfile
) -> tuple[float, float, float]:
    values = (
        request.call_timeout_seconds or float(profile.call_timeout_seconds),
        request.model_timeout_seconds or float(profile.model_timeout_seconds),
        request.run_timeout_seconds or float(profile.run_timeout_seconds),
    )
    defaults = (
        profile.call_timeout_seconds,
        profile.model_timeout_seconds,
        profile.run_timeout_seconds,
    )
    if any(value > maximum for value, maximum in zip(values, defaults)):
        raise ValueError("timeout override exceeds the locked profile bound")
    if not values[0] <= values[1] <= values[2]:
        raise ValueError("timeouts must be ordered call <= model <= run")
    return values


def _initial_artifacts(
    run_dir: Path,
    run_id: str,
    request: RunRequest,
    suite: LoadedCoachSuite,
    profile: CoachProfile,
    schedule: tuple[ScheduleEntry, ...],
) -> dict[str, Any]:
    identity_payload = _identity_payload(suite, profile, request)
    models = {item.id: item for item in suite.models}
    protected = _protected_hashes()
    prompt_hashes = {
        path.relative_to(Path.cwd()).as_posix(): hash_file(path)
        for path in sorted((Path.cwd() / "app/prompts").glob("*.j2"))
        if any(name in path.name for name in ("question", "answer", "rubric", "report", "research", "drill"))
    }
    skill_hashes = {
        path.relative_to(Path.cwd()).as_posix(): hash_file(path)
        for path in (
            Path.cwd() / "app/skills/company-research/SKILL.md",
            Path.cwd() / "app/skills/interview-prep/SKILL.md",
        )
        if path.is_file()
    }
    manifest = {
        "run_id": run_id,
        "suite_id": suite.suite_id,
        "suite_version": suite.version,
        "profile": profile.model_dump(mode="json"),
        "models": [
            {
                "id": model_id,
                "runtime": models[model_id].runtime,
                "endpoint": str(models[model_id].endpoint),
            }
            for model_id in request.model_ids
        ],
        "seeds": list(suite.seeds),
        "input_hashes": suite.input_hashes,
        "prompt_hashes": prompt_hashes,
        "skill_hashes": skill_hashes,
        "git": git_state(Path.cwd()),
        "protected_hashes_before": protected,
        "protected_hashes_after": protected,
        "command": request.command,
        "state": "running",
    }
    run_manifest = {
        "run_id": run_id,
        "identity": stable_identity(identity_payload),
        "identity_payload": identity_payload,
        "suite_path": _relative(request.suite_path),
        "request": request.model_dump(mode="json", exclude={"suite_path", "output_root"}),
        "schedule": [item.model_dump(mode="json") for item in schedule],
    }
    atomic_write_json(run_dir / "manifest.json", manifest)
    atomic_write_json(run_dir / "run_manifest.json", run_manifest)
    atomic_write_json(
        run_dir / "progress.json",
        {"scheduled": len(schedule), "terminal": 0, "completed_attempt_ids": []},
    )
    atomic_write_json(run_dir / "aggregate.json", {"capabilities": [], "ranking": []})
    atomic_write_text(run_dir / "report.md", f"# Coach benchmark {run_id}\n\nRun in progress.\n")
    return manifest


def _result_path(run_dir: Path, attempt: ScheduleEntry) -> Path:
    return (
        run_dir
        / "scenarios"
        / attempt.model_id
        / attempt.scenario_id
        / f"repetition-{attempt.repetition}.json"
    )


def _status(outcome: str) -> str:
    return {
        "completed": "completed",
        "withheld_insufficient_evidence": "withheld_insufficient_evidence",
        "fallback_deterministic": "fallback",
        "unavailable": "unavailable",
        "invalid_output": "invalid",
        "failed": "failed",
    }.get(outcome, "failed")


def _scenario_result(
    attempt: ScheduleEntry,
    execution: Any,
    duration_ms: int,
) -> ScenarioResult:
    scenario = execution[0]
    stage_execution = execution[1]
    validation = validate_execution(scenario, stage_execution)
    score = score_execution(scenario, stage_execution, validation)
    calibration_in_range: int | None = None
    calibration_applicable: int | None = None
    calibration_error: str | None = None
    if scenario.stage == "answer_evaluation" and stage_execution.output.get(
        "evaluation_state"
    ) == "completed":
        ranges = {
            key: value
            for key, value in scenario.expected.score_ranges.items()
            if key != "overall"
        }
        observed_scores = stage_execution.output.get("scores", {})
        calibration_applicable = len(ranges)
        calibration_in_range = sum(
            key in observed_scores and low <= observed_scores[key] <= high
            for key, (low, high) in ranges.items()
        )
        overall_range = scenario.expected.score_ranges.get("overall")
        overall = stage_execution.output.get("overall")
        if overall_range and isinstance(overall, int | float):
            centre = (
                Decimal(str(overall_range[0])) + Decimal(str(overall_range[1]))
            ) / Decimal(2)
            calibration_error = str(abs(Decimal(str(overall)) - centre))
    return ScenarioResult(
        attempt=attempt,
        status=_status(stage_execution.diagnostic.outcome),
        stage_outcome=stage_execution.diagnostic.outcome,
        duration_ms=duration_ms,
        prompt_metadata=stage_execution.prompt_metadata,
        attempt_count=stage_execution.provider_attempt_count,
        repair_count=stage_execution.repair_count,
        gates=[
            GateFinding(code=item.code, blocking=item.blocking)
            for item in validation.findings
        ],
        dimensions={
            name: DimensionResult(
                score=value,
                weight="renormalized",
                applicable=value is not None,
            )
            for name, value in score.dimensions.items()
        },
        quality_score=score.quality_score,
        calibration_in_range=calibration_in_range,
        calibration_applicable=calibration_applicable,
        calibration_error=calibration_error,
        output_excerpt=_bounded_value(stage_execution.output),
    )


def _bounded_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 6:
        return "[bounded]"
    if isinstance(value, str):
        return value if len(value) <= 500 else value[:497] + "..."
    if isinstance(value, list):
        return [_bounded_value(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, dict):
        return {
            str(key): _bounded_value(item, depth=depth + 1)
            for key, item in list(value.items())[:30]
        }
    return value


def _timeout_result(
    attempt: ScheduleEntry, timeout_stage: Literal["call", "model", "whole_run"]
) -> ScenarioResult:
    return ScenarioResult(
        attempt=attempt,
        status="timeout",
        stage_outcome="unavailable",
        duration_ms=0,
        timeout_stage=timeout_stage,
        gates=[GateFinding(code="coach_stage_timeout", blocking=False)],
        exclusion_reason=f"{timeout_stage} deadline expired",
    )


def _state(
    schedule: tuple[ScheduleEntry, ...],
    results: list[ScenarioResult],
    *,
    deadline: bool,
    interrupted: bool,
    protected_changed: bool,
) -> str:
    if protected_changed:
        return "invalid_harness_integrity"
    harness_failed = any(
        item.attempt.qualification_scope == "harness_contract"
        and any(gate.blocking for gate in item.gates)
        for item in results
    )
    if harness_failed:
        return "invalid_harness_integrity"
    if deadline and len(results) < len(schedule):
        return "incomplete_deadline"
    if interrupted and len(results) < len(schedule):
        return "incomplete_interrupted"
    adverse = any(
        item.attempt.qualification_scope == "model_capability"
        and (
            item.status not in {"completed", "withheld_insufficient_evidence"}
            or any(gate.blocking for gate in item.gates)
        )
        for item in results
    )
    return "completed_with_model_outcomes" if adverse else "completed"


def _write_progress(
    run_dir: Path,
    schedule: tuple[ScheduleEntry, ...],
    results: list[ScenarioResult],
) -> None:
    atomic_write_json(
        run_dir / "progress.json",
        {
            "scheduled": len(schedule),
            "terminal": len(results),
            "completed_attempt_ids": [item.attempt.attempt_id for item in results],
        },
    )


def _write_summary(
    run_dir: Path,
    run_id: str,
    suite: LoadedCoachSuite,
    profile: CoachProfile,
    schedule: tuple[ScheduleEntry, ...],
    results: list[ScenarioResult],
    *,
    deadline: bool,
    interrupted: bool,
    protected_changed: bool,
) -> CoachRunSummary:
    state = _state(
        schedule,
        results,
        deadline=deadline,
        interrupted=interrupted,
        protected_changed=protected_changed,
    )
    capabilities = []
    ranking = []
    if profile.allow_ranking and state in {
        "completed",
        "completed_with_model_outcomes",
    }:
        model_ids = list(dict.fromkeys(item.model_id for item in schedule))
        capabilities = [
            classify_model(model_id, results, state) for model_id in model_ids
        ]
        ranked = rank_models(capabilities)
        ranks = {item.model_id: item.rank for item in ranked}
        capabilities = [
            item.model_copy(update={"rank": ranks.get(item.model_id)})
            for item in capabilities
        ]
        ranking = [item.model_id for item in ranked]
    summary = CoachRunSummary(
        run_id=run_id,
        suite_id=suite.suite_id,
        suite_version=suite.version,
        profile=profile.name,
        state=state,
        scheduled=len(schedule),
        terminal=len(results),
        results=results,
        capabilities=capabilities,
        ranking=ranking,
    )
    atomic_write_json(run_dir / "summary.json", summary.model_dump(mode="json"))
    atomic_write_json(
        run_dir / "aggregate.json",
        {
            "state": summary.state,
            "capabilities": [item.model_dump(mode="json") for item in summary.capabilities],
            "ranking": summary.ranking,
        },
    )
    atomic_write_text(
        run_dir / "report.md",
        f"# Coach benchmark {run_id}\n\nState: `{summary.state}`\n\n"
        f"Terminal attempts: {summary.terminal}/{summary.scheduled}.\n",
    )
    _write_progress(run_dir, schedule, results)
    return summary


async def _execute_run(
    request: RunRequest,
    suite: LoadedCoachSuite,
    profile: CoachProfile,
    schedule: tuple[ScheduleEntry, ...],
    run_dir: Path,
    run_id: str,
    manifest: dict[str, Any],
    dependencies: RunnerDependencies,
    prior_results: list[ScenarioResult],
) -> CoachRunSummary:
    results = list(prior_results)
    completed = {item.attempt.attempt_id for item in results}
    models = {item.id: item for item in suite.models}
    context = ScenarioContext.from_suite(suite)
    adapter = dependencies.adapter()
    started = dependencies.monotonic()
    call_limit, model_limit, run_limit = _timeout_limits(request, profile)
    deadline = False
    interrupted = False
    stop_run = False
    try:
        for model_id in request.model_ids:
            if stop_run:
                break
            model_started = dependencies.monotonic()
            model_attempts = [item for item in schedule if item.model_id == model_id]
            for attempt in model_attempts:
                if attempt.attempt_id in completed:
                    continue
                run_remaining = run_limit - (dependencies.monotonic() - started)
                model_remaining = model_limit - (
                    dependencies.monotonic() - model_started
                )
                if run_remaining <= 0:
                    deadline = True
                    stop_run = True
                    break
                if model_remaining <= 0:
                    deadline = True
                    break
                timeout = min(call_limit, model_remaining, run_remaining)
                timeout_stage: Literal["call", "model", "whole_run"] = "call"
                if run_remaining <= min(call_limit, model_remaining):
                    timeout_stage = "whole_run"
                elif model_remaining <= call_limit:
                    timeout_stage = "model"
                scenario = suite.scenario(attempt.scenario_id)
                call_started = dependencies.monotonic()
                try:
                    if scenario.forced_failure:
                        client_context = _single_client(
                            HarnessFailureClient(scenario.forced_failure)
                        )
                    else:
                        client_context = dependencies.adapter_factory(
                            models[model_id], attempt.seed
                        )
                    async with client_context as client:
                        async with asyncio.timeout(timeout):
                            stage_execution = await adapter.execute(
                                scenario, client, context
                            )
                    result = _scenario_result(
                        attempt,
                        (scenario, stage_execution),
                        int((dependencies.monotonic() - call_started) * 1000),
                    )
                except TimeoutError:
                    result = _timeout_result(attempt, timeout_stage)
                    if timeout_stage != "call":
                        deadline = True
                        stop_run = timeout_stage == "whole_run"
                except Exception as exc:
                    result = ScenarioResult(
                        attempt=attempt,
                        status="failed",
                        stage_outcome="failed",
                        duration_ms=int(
                            (dependencies.monotonic() - call_started) * 1000
                        ),
                        gates=[GateFinding(code="coach_stage_failed", blocking=True)],
                        exclusion_reason=type(exc).__name__,
                    )
                results.append(result)
                atomic_write_json(
                    _result_path(run_dir, attempt), result.model_dump(mode="json")
                )
                _write_progress(run_dir, schedule, results)
                if deadline and timeout_stage in {"model", "whole_run"}:
                    break
    except BaseException:
        interrupted = True
        summary = _write_summary(
            run_dir,
            run_id,
            suite,
            profile,
            schedule,
            results,
            deadline=deadline,
            interrupted=True,
            protected_changed=False,
        )
        del summary
        raise
    protected_after = _protected_hashes()
    protected_changed = protected_after != manifest["protected_hashes_before"]
    manifest.update(
        {
            "protected_hashes_after": protected_after,
            "state": "finished",
        }
    )
    atomic_write_json(run_dir / "manifest.json", manifest)
    return _write_summary(
        run_dir,
        run_id,
        suite,
        profile,
        schedule,
        results,
        deadline=deadline,
        interrupted=interrupted,
        protected_changed=protected_changed,
    )


@asynccontextmanager
async def _single_client(client: object) -> AsyncIterator[object]:
    yield client


async def run_benchmark(
    request: RunRequest,
    dependencies: RunnerDependencies | None = None,
) -> CoachRunSummary:
    dependencies = dependencies or RunnerDependencies()
    suite = load_suite(request.suite_path)
    profile = profile_for(request.profile_name)
    _timeout_limits(request, profile)
    schedule = build_schedule(suite, profile, request.model_ids)
    run_id = uuid.uuid4().hex
    run_dir = request.output_root / run_id
    manifest = _initial_artifacts(
        run_dir, run_id, request, suite, profile, schedule
    )
    return await _execute_run(
        request,
        suite,
        profile,
        schedule,
        run_dir,
        run_id,
        manifest,
        dependencies,
        [],
    )


async def resume_benchmark(
    run_dir: Path,
    retry_timeouts: bool = False,
    dependencies: RunnerDependencies | None = None,
) -> CoachRunSummary:
    dependencies = dependencies or RunnerDependencies()
    raw = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    identity_payload = raw["identity_payload"]
    if raw.get("identity") != stable_identity(identity_payload):
        raise ValueError("run identity mismatch")
    suite_path = (Path.cwd() / raw["suite_path"]).resolve()
    suite = load_suite(suite_path)
    profile = profile_for(raw["request"]["profile_name"])
    request = RunRequest(
        suite_path=suite_path,
        output_root=run_dir.parent,
        **raw["request"],
    )
    current_identity = _identity_payload(suite, profile, request)
    if current_identity != identity_payload:
        raise ValueError("run identity mismatch")
    schedule = tuple(ScheduleEntry.model_validate(item) for item in raw["schedule"])
    results: list[ScenarioResult] = []
    for attempt in schedule:
        path = _result_path(run_dir, attempt)
        if path.is_file():
            result = ScenarioResult.model_validate_json(path.read_text(encoding="utf-8"))
            if retry_timeouts and result.status == "timeout":
                path.unlink()
            else:
                results.append(result)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    return await _execute_run(
        request,
        suite,
        profile,
        schedule,
        run_dir,
        raw["run_id"],
        manifest,
        dependencies,
        results,
    )
