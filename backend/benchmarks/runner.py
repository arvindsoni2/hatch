"""Sequential benchmark execution, atomic artifacts, and model aggregation."""
from __future__ import annotations

import json
import asyncio
import statistics
import subprocess
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.services.cl_generator import CoverLetterGenerator, select_tone_variant
from app.services.cv_tailor import CVTailor
from app.services.profile_service import current_profile_hash
from app.services.writing_contracts import (
    EVIDENCE_SCHEMA_VERSION,
    VALIDATION_SCHEMA_VERSION,
    build_evidence_ledger,
    prompt_metadata_records,
)
from app.config import settings

from .adapters import BenchmarkLLMClient, BenchmarkModelUnavailableError, BenchmarkTimeoutError
from .contracts import (
    BenchmarkCase,
    BenchmarkProfile,
    BenchmarkSummary,
    ModelAggregate,
    ModelSpec,
    PairMetrics,
    PairScore,
    Recommendation,
    RepetitionResult,
)
from .scoring import score_pair


_ACCEPTED_BASELINE_MERGE_SHA = "a5a4d729a4dfddcabb2ec4ca54c91120f616f6de"


class Adapter(Protocol):
    raw_responses: list[str]
    observations: list[Any]

    async def complete_json(
        self, system: str, user: str, max_tokens: int = 4096
    ) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


AdapterFactory = Callable[[ModelSpec, int], Adapter]


def _default_adapter_factory(spec: ModelSpec, seed: int) -> Adapter:
    return BenchmarkLLMClient(spec, seed)


class _EmptyAdapter:
    raw_responses: list[str] = []
    observations: list[Any] = []

    async def complete_json(
        self, system: str, user: str, max_tokens: int = 4096
    ) -> dict[str, Any]:
        del system, user, max_tokens
        return {}

    async def aclose(self) -> None:
        return None


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _git_branch() -> str:
    try:
        return subprocess.run(
            ["git", "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip() or "detached"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _working_tree_clean() -> bool | str:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return status == ""
    except (OSError, subprocess.CalledProcessError):
        return "not_recorded"


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _database_path() -> Path | None:
    url = settings.DATABASE_URL
    if not url.startswith("sqlite"):
        return None
    parsed = urlparse(url)
    raw_path = unquote(parsed.path or "")
    if raw_path.startswith("/") and not url.startswith("sqlite:////"):
        raw_path = raw_path.lstrip("/")
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _protected_hashes() -> dict[str, str]:
    profile_hash = current_profile_hash()
    database = _database_path()
    database_hash = _file_sha256(database) if database and database.exists() else None
    return {
        "profile": profile_hash or "not_recorded",
        "database": database_hash or "not_recorded",
    }


def _probe_http(url: str, *, timeout: float = 2.0) -> dict[str, Any]:
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return {"url": url, "status_code": response.status}
    except HTTPError as exc:
        return {"url": url, "status_code": exc.code, "error_type": type(exc).__name__}
    except URLError as exc:
        return {
            "url": url,
            "status_code": "unavailable",
            "error_type": type(exc).__name__,
            "error_message": str(exc.reason),
        }
    except TimeoutError as exc:
        return {
            "url": url,
            "status_code": "unavailable",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def _runtime_health() -> dict[str, dict[str, Any]]:
    return {
        "backend": _probe_http("http://127.0.0.1:8000/api/health"),
        "frontend": _probe_http("http://127.0.0.1:3000"),
    }


def _repository_hashes() -> dict[str, str]:
    backend_root = Path(__file__).resolve().parents[1]
    paths = [
        backend_root / "app/prompts/cv_tailoring.j2",
        backend_root / "app/prompts/cl_generation.j2",
        backend_root / "app/skills/cv-tailoring/SKILL.md",
        backend_root / "app/skills/cover-letter/SKILL.md",
    ]
    return {str(path.relative_to(backend_root)): _file_sha256(path) for path in paths}


def _model_aggregate(model_id: str, results: list[RepetitionResult]) -> ModelAggregate:
    succeeded = [item for item in results if item.status == "succeeded"]
    eligible = [
        item
        for item in succeeded
        if item.score is not None and item.score.eligible and item.score.combined is not None
    ]
    scores = [float(item.score.combined) for item in eligible if item.score and item.score.combined is not None]
    cv_scores = [float(item.score.cv.total) for item in eligible if item.score and item.score.cv]
    cl_scores = [
        float(item.score.cover_letter.total)
        for item in eligible
        if item.score and item.score.cover_letter
    ]
    pair_metrics = [
        item.pair_metrics
        for item in succeeded
        if item.pair_metrics is not None
    ]
    latencies = [
        metrics.eligible_pair_latency_ms
        for metrics in pair_metrics
        if metrics.eligible_pair_latency_ms is not None
    ]
    first_passes = [
        item
        for item in succeeded
        if item.pair_metrics is not None
        and item.pair_metrics.first_pass_hard_gate_passed
    ]
    final_body_counts = [
        item.final_cover_letter_word_count
        for item in succeeded
        if item.final_cover_letter_word_count is not None
    ]
    gate_codes = Counter(
        finding.code
        for item in succeeded
        if item.score is not None
        for finding in item.score.gates
        if finding.blocking
    )
    attempted = len(results)
    repairs = [item.cover_letter_repair_count for item in succeeded]
    prompt_tokens = [
        metrics.prompt_tokens
        for metrics in pair_metrics
        if metrics.prompt_tokens is not None
    ]
    output_tokens = [
        metrics.output_tokens
        for metrics in pair_metrics
        if metrics.output_tokens is not None
    ]
    sparse_results = [
        metrics
        for metrics in pair_metrics
        if metrics.missing_evidence_case
    ]
    return ModelAggregate(
        model_id=model_id,
        attempted=attempted,
        succeeded=len(succeeded),
        failed=sum(item.status == "failed" for item in results),
        unavailable=sum(item.status == "unavailable" for item in results),
        timeout=sum(item.status == "timeout" for item in results),
        interrupted=sum(item.status == "interrupted" for item in results),
        eligible=len(eligible),
        hard_gate_pass_rate=(len(eligible) / attempted if attempted else 0.0),
        median_cv_score=statistics.median(cv_scores) if cv_scores else None,
        median_cover_letter_score=statistics.median(cl_scores) if cl_scores else None,
        median_writing_score=statistics.median(scores) if scores else None,
        writing_score_variance=statistics.pvariance(scores) if len(scores) > 1 else (0.0 if scores else None),
        median_latency_ms=statistics.median(latencies) if latencies else None,
        gate_codes=dict(sorted(gate_codes.items())),
        first_pass_gate_pass_rate=(len(first_passes) / attempted if attempted else 0.0),
        post_repair_gate_pass_rate=(len(eligible) / attempted if attempted else 0.0),
        total_repair_count=sum(item.cover_letter_repair_count for item in succeeded),
        median_final_cover_letter_body_words=(
            statistics.median(final_body_counts) if final_body_counts else None
        ),
        numeric_fidelity_failures=sum(len(item.numeric_fidelity_failures) for item in succeeded),
        total_latency_ms=sum(latencies) if latencies else None,
        successful_response_rate=(len(succeeded) / attempted if attempted else 0.0),
        schema_success_rate=(
            sum(metrics.schema_succeeded for metrics in pair_metrics) / attempted
            if attempted
            else 0.0
        ),
        mean_repair_count=statistics.mean(repairs) if repairs else 0.0,
        median_repair_count=statistics.median(repairs) if repairs else 0.0,
        unsupported_candidate_claims=sum(
            metrics.unsupported_candidate_claims for metrics in pair_metrics
        ),
        unsupported_numeric_tokens=sum(
            metrics.unsupported_numeric_tokens for metrics in pair_metrics
        ),
        immutable_token_mutations=sum(
            metrics.immutable_token_mutations for metrics in pair_metrics
        ),
        missing_evidence_safe_fallback_rate=(
            sum(item.missing_evidence_safe_fallback for item in sparse_results)
            / len(sparse_results)
            if sparse_results
            else 0.0
        ),
        mean_evidence_coverage=(
            statistics.mean(metrics.evidence_coverage for metrics in pair_metrics)
            if pair_metrics
            else 0.0
        ),
        median_prompt_tokens=(
            statistics.median(prompt_tokens) if prompt_tokens else None
        ),
        median_output_tokens=(
            statistics.median(output_tokens) if output_tokens else None
        ),
    )


def _numeric_fidelity_failures(letter: Any) -> list[str]:
    issues = list(getattr(letter, "validation_issues", []) or [])
    issues.extend(getattr(letter, "grounding_issues", []) or [])
    return [
        issue
        for issue in dict.fromkeys(str(item) for item in issues)
        if "numeric" in issue.lower()
    ]


def _pair_metrics(
    case: BenchmarkCase,
    cv: Any,
    letter: Any,
    pair_score: PairScore,
    observations: list[Any],
    duration_ms: float,
) -> PairMetrics:
    """Derive the PR5 pair contract from production provenance and hard gates."""
    workflow = getattr(
        getattr(letter, "generation_provenance", None),
        "workflow",
        None,
    ) or {}
    attempts = workflow.get("attempts") or []
    first_validation = (
        attempts[0].get("validator_results", {})
        if attempts and isinstance(attempts[0], dict)
        else {}
    )
    cv_blocking = list(getattr(cv, "blocking_issues", []) or [])
    first_passed = bool(
        not cv_blocking
        and first_validation
        and first_validation.get("passed") is True
    )
    numeric_failures = _numeric_fidelity_failures(letter)
    blocking_codes = [
        finding.code
        for finding in pair_score.gates
        if finding.blocking
    ]
    unsupported_codes = {
        "unsupported_candidate_claim",
        "unsupported_numeric_token",
        "production_grounding_failure",
        "role_structure_mismatch",
        "certification_mismatch",
        "education_mismatch",
    }
    unsupported_claims = sum(
        code in unsupported_codes for code in blocking_codes
    )
    unsupported_numeric = sum(
        code == "unsupported_numeric_token" for code in blocking_codes
    )
    immutable_mutations = sum(
        "mutat" in issue.casefold() or "immutable" in issue.casefold()
        for issue in numeric_failures
    )

    ledger = build_evidence_ledger(case.master_cv)
    available_ids = {item.id for item in ledger}
    content_plan = getattr(
        getattr(letter, "generation_provenance", None),
        "content_plan",
        None,
    ) or {}
    used_ids = {
        evidence_id
        for key, values in content_plan.items()
        if key.endswith("_evidence_ids") and isinstance(values, list)
        for evidence_id in values
        if evidence_id in available_ids
    }
    cv_provenance = getattr(cv, "generation_provenance", None)
    for evidence_id in getattr(cv_provenance, "source_evidence_ids", ()) or ():
        if evidence_id in available_ids:
            used_ids.add(evidence_id)

    observation_prompt_tokens = [
        item.prompt_tokens
        for item in observations
        if getattr(item, "prompt_tokens", None) is not None
    ]
    observation_output_tokens = [
        item.completion_tokens
        for item in observations
        if getattr(item, "completion_tokens", None) is not None
    ]
    attempt_prompt_tokens = [
        attempt.get("input_tokens")
        for attempt in attempts
        if isinstance(attempt, dict)
        and isinstance(attempt.get("input_tokens"), int)
    ]
    attempt_output_tokens = [
        attempt.get("output_tokens")
        for attempt in attempts
        if isinstance(attempt, dict)
        and isinstance(attempt.get("output_tokens"), int)
    ]
    prompt_tokens = (
        sum(observation_prompt_tokens)
        if observation_prompt_tokens
        else sum(attempt_prompt_tokens)
        if attempt_prompt_tokens
        else None
    )
    output_tokens = (
        sum(observation_output_tokens)
        if observation_output_tokens
        else sum(attempt_output_tokens)
        if attempt_output_tokens
        else None
    )
    first_pass_latency = (
        float(attempts[0].get("latency_ms", 0))
        if attempts and isinstance(attempts[0], dict)
        else None
    )
    repair_latency = (
        sum(
            float(attempt.get("latency_ms", 0))
            for attempt in attempts[1:]
            if isinstance(attempt, dict)
        )
        if len(attempts) > 1
        else 0.0
    )
    memory_values = [
        getattr(item, "raw_metadata", {}).get("peak_memory_mb")
        for item in observations
        if isinstance(getattr(item, "raw_metadata", None), dict)
        and isinstance(
            getattr(item, "raw_metadata", {}).get("peak_memory_mb"),
            (int, float),
        )
    ]
    final_state = workflow.get("final_state")
    safe_fallback = bool(
        "sparse_evidence" in case.risk_tags
        and final_state == "review_required"
        and not pair_score.eligible
    )
    total_tokens = (
        prompt_tokens + output_tokens
        if prompt_tokens is not None and output_tokens is not None
        else None
    )
    return PairMetrics(
        first_pass_hard_gate_passed=first_passed,
        post_repair_hard_gate_passed=pair_score.eligible,
        schema_succeeded=True,
        unsupported_candidate_claims=unsupported_claims,
        unsupported_numeric_tokens=unsupported_numeric,
        immutable_token_mutations=immutable_mutations,
        missing_evidence_case="sparse_evidence" in case.risk_tags,
        missing_evidence_safe_fallback=safe_fallback,
        evidence_items_available=len(ledger),
        evidence_items_used=len(used_ids),
        evidence_coverage=(len(used_ids) / len(ledger) if ledger else 0.0),
        first_pass_latency_ms=first_pass_latency,
        repair_latency_ms=repair_latency,
        eligible_pair_latency_ms=(
            duration_ms if pair_score.eligible else None
        ),
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        tokens_per_eligible_pair=(
            total_tokens if pair_score.eligible else None
        ),
        peak_memory_mb=max(memory_values) if memory_values else None,
        normalized_combined_quality=(
            pair_score.combined if pair_score.eligible else None
        ),
    )


def _ranking_key(item: ModelAggregate) -> tuple[float, float, float, float, str]:
    return (
        -item.hard_gate_pass_rate,
        -(item.median_writing_score if item.median_writing_score is not None else -1.0),
        item.writing_score_variance if item.writing_score_variance is not None else float("inf"),
        item.median_latency_ms if item.median_latency_ms is not None else float("inf"),
        item.model_id,
    )


def _recommend(aggregates: list[ModelAggregate], ranking: list[ModelAggregate]) -> Recommendation:
    limitations = [
        "This result covers one Delivery Manager case and is not a universal model verdict."
    ]
    if not ranking or all(item.eligible == 0 for item in aggregates):
        shared = set(aggregates[0].gate_codes) if aggregates else set()
        for item in aggregates[1:]:
            shared &= set(item.gate_codes)
        if shared and all(item.succeeded > 0 for item in aggregates):
            return Recommendation(
                classification="prompt_or_skill_change",
                rationale=["All responding models share blocking failures: " + ", ".join(sorted(shared))],
                limitations=limitations,
            )
        return Recommendation(
            classification="inconclusive",
            rationale=["No model produced an eligible writing pair."],
            limitations=limitations,
        )

    if any(item.failed or item.unavailable for item in aggregates):
        limitations.append("At least one repetition failed or was unavailable.")

    winner = ranking[0]
    baseline = next((item for item in aggregates if item.model_id == "qwen35-4b"), None)
    if winner.model_id == "qwen35-4b":
        return Recommendation(
            classification="keep_current_model",
            rationale=["The current Qwen3.5 4B baseline ranks first under the safety-first rules."],
            limitations=limitations,
        )
    if baseline is None or baseline.eligible == 0 or winner.hard_gate_pass_rate > baseline.hard_gate_pass_rate:
        rationale = [f"{winner.model_id} has the strongest safety-first benchmark result."]
    else:
        rationale = [f"{winner.model_id} has the highest median eligible writing score."]
    return Recommendation(
        classification="model_change",
        rationale=rationale,
        limitations=limitations,
    )


def _profile_from_name(name: str) -> BenchmarkProfile:
    if name == "acceptance-smoke":
        return BenchmarkProfile(
            name="acceptance-smoke",
            call_timeout_seconds=20 * 60,
            model_timeout_seconds=45 * 60,
            whole_run_timeout_seconds=3 * 60 * 60,
        )
    if name == "extended":
        return BenchmarkProfile(
            name="extended",
            call_timeout_seconds=20 * 60,
            model_timeout_seconds=90 * 60,
            whole_run_timeout_seconds=12 * 60 * 60,
        )
    raise ValueError(f"unknown benchmark profile: {name}")


def benchmark_profile(name: str) -> BenchmarkProfile:
    return _profile_from_name(name)


def _progress_payload(
    *,
    run_id: str,
    case: BenchmarkCase,
    model_ids: list[str],
    repetitions: int,
    profile: BenchmarkProfile,
    by_model: dict[str, list[RepetitionResult]],
    completion_state: str,
) -> dict[str, Any]:
    models: dict[str, dict[str, Any]] = {}
    for model_id in model_ids:
        results = by_model.get(model_id, [])
        completed = sum(item.status == "succeeded" for item in results)
        if not results:
            execution_status = "not_started"
        elif any(item.status == "timeout" for item in results):
            execution_status = "timeout"
        elif any(item.status == "interrupted" for item in results):
            execution_status = "interrupted"
        elif any(item.status == "failed" for item in results):
            execution_status = "failed"
        elif any(item.status == "unavailable" for item in results):
            execution_status = "unavailable"
        elif len(results) >= repetitions:
            execution_status = "completed"
        else:
            execution_status = "running"
        models[model_id] = {
            "availability": (
                "unavailable" if any(item.status == "unavailable" for item in results) else "available"
            ),
            "execution_status": execution_status,
            "completed_repetitions": completed,
            "attempted_repetitions": len(results),
            "requested_repetitions": repetitions,
            "eligible_for_ranking": any(item.eligible_for_ranking for item in results),
        }
    return {
        "run_id": run_id,
        "case_id": case.case_id,
        "benchmark_profile": profile.name,
        "completion_state": completion_state,
        "models": models,
    }


def _summary_from_results(
    *,
    run_id: str,
    case: BenchmarkCase,
    model_ids: list[str],
    repetitions: int,
    profile: BenchmarkProfile,
    by_model: dict[str, list[RepetitionResult]],
    completion_state: str,
) -> BenchmarkSummary:
    aggregates = [_model_aggregate(model_id, by_model[model_id]) for model_id in model_ids]
    ranking = sorted(aggregates, key=_ranking_key)
    recommendation = (
        Recommendation(
            classification="inconclusive",
            rationale=[
                "Acceptance-smoke validates the benchmark and writing contract; it does not select a model."
            ],
            limitations=[
                "This result covers one repetition per model and is PR1 contract evidence only."
            ],
        )
        if profile.name == "acceptance-smoke"
        else _recommend(aggregates, ranking)
    )
    return BenchmarkSummary(
        run_id=run_id,
        case_id=case.case_id,
        created_at=datetime.now(UTC).isoformat(),
        benchmark_profile=profile.name,
        repetitions=repetitions,
        selected_models=model_ids,
        completion_state=completion_state,  # type: ignore[arg-type]
        models=aggregates,
        ranking=ranking,
        recommendation=recommendation,
    )


def _manifest_payload(
    *,
    run_id: str,
    case: BenchmarkCase,
    model_ids: list[str],
    repetitions: int,
    profile: BenchmarkProfile,
    available: dict[str, ModelSpec],
    clean_before: bool | str,
    protected_before: dict[str, str],
    completion_state: str,
    commands: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    protected_after = _protected_hashes()
    writing_prompt_metadata = prompt_metadata_records()
    return {
        "run_id": run_id,
        "benchmark_profile": profile.name,
        "case_id": case.case_id,
        "case_hash": case.input_hashes,
        "accepted_baseline_merge_sha": _ACCEPTED_BASELINE_MERGE_SHA,
        "source_commit_sha": _git_commit(),
        "repository_commit": _git_commit(),
        "branch": _git_branch(),
        "working_tree_clean_before": clean_before,
        "working_tree_clean_after": _working_tree_clean(),
        "requested_repetitions": repetitions,
        "timeout_settings": profile.model_dump(mode="json", exclude={"name"}),
        "commands": commands or [],
        "tests": {"passed": "not_recorded", "failed": "not_recorded", "skipped": "not_recorded"},
        "protected_hashes": {
            "before": protected_before,
            "after": protected_after,
            "unchanged": protected_before == protected_after,
        },
        "pre_run_protected_hashes": protected_before,
        "post_run_protected_hashes": protected_after,
        "health": _runtime_health(),
        "prompt_versions": {
            prompt_id: metadata["prompt_version"]
            for prompt_id, metadata in writing_prompt_metadata.items()
        },
        "schema_versions": {
            "benchmark_result": "pr1-acceptance-profile",
            "evidence_ledger": EVIDENCE_SCHEMA_VERSION,
            "writing_validation": VALIDATION_SCHEMA_VERSION,
            **{
                prompt_id: metadata["schema_version"]
                for prompt_id, metadata in writing_prompt_metadata.items()
            },
        },
        "skill_versions": {
            "cover-letter": "pr1-cover-letter-contract",
        },
        "models": [available[item].model_dump(mode="json") for item in model_ids],
        "model_list": model_ids,
        "completion_state": completion_state,
    }


def _write_run_outputs(
    *,
    run_dir: Path,
    summary: BenchmarkSummary,
    run_id: str,
    case: BenchmarkCase,
    model_ids: list[str],
    repetitions: int,
    profile: BenchmarkProfile,
    by_model: dict[str, list[RepetitionResult]],
    available: dict[str, ModelSpec],
    clean_before: bool | str,
    protected_before: dict[str, str],
    completion_state: str,
    commands: list[dict[str, Any]] | None = None,
) -> None:
    from .reporting import write_report

    _atomic_write_json(run_dir / "summary.json", summary.model_dump(mode="json"))
    _atomic_write_json(run_dir / "aggregate.json", summary.model_dump(mode="json"))
    _atomic_write_json(
        run_dir / "progress.json",
        _progress_payload(
            run_id=run_id,
            case=case,
            model_ids=model_ids,
            repetitions=repetitions,
            profile=profile,
            by_model=by_model,
            completion_state=completion_state,
        ),
    )
    _atomic_write_json(
        run_dir / "run_manifest.json",
        _manifest_payload(
            run_id=run_id,
            case=case,
            model_ids=model_ids,
            repetitions=repetitions,
            profile=profile,
            available=available,
            clean_before=clean_before,
            protected_before=protected_before,
            completion_state=completion_state,
            commands=commands,
        ),
    )
    write_report(summary, run_dir / "report.md")


def _execution_status_for_result(result: RepetitionResult) -> str:
    if result.status == "succeeded":
        return "completed"
    return result.status


def _model_result_payload(result: RepetitionResult) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    payload["execution_status"] = _execution_status_for_result(result)
    payload["availability"] = result.availability
    payload["eligible_for_ranking"] = result.eligible_for_ranking
    if result.cover_letter:
        paragraphs = result.cover_letter.get("body_paragraphs") or []
        payload["paragraph_word_counts"] = [
            len(str(paragraph).split()) for paragraph in paragraphs if isinstance(paragraph, str)
        ]
        payload["repair_types"] = list(result.cover_letter.get("validation_issues") or [])
        payload["validation_status"] = result.cover_letter.get("validation_status")
        payload["blocking_issues"] = [
            gate.model_dump(mode="json")
            for gate in (result.score.gates if result.score else [])
            if gate.blocking
        ]
        payload["advisory_issues"] = list(result.cover_letter.get("grounding_issues") or [])
    else:
        payload["paragraph_word_counts"] = []
        payload["repair_types"] = []
        payload["validation_status"] = None
        payload["blocking_issues"] = []
        payload["advisory_issues"] = []
    payload["numeric_fidelity_issues"] = result.numeric_fidelity_failures
    payload["writing_quality_score"] = (
        result.score.cover_letter.total
        if result.score and result.score.cover_letter is not None
        else None
    )
    return payload


async def run_benchmark(
    case: BenchmarkCase,
    *,
    model_ids: list[str],
    repetitions: int,
    output_root: Path,
    adapter_factory: AdapterFactory = _default_adapter_factory,
    run_id: str | None = None,
    profile: BenchmarkProfile | None = None,
    resume_run_id: str | None = None,
    retry_timeouts: bool = False,
) -> BenchmarkSummary:
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")
    if repetitions > len(case.seeds):
        raise ValueError(
            f"case defines {len(case.seeds)} seeds but {repetitions} repetitions were requested"
        )
    profile = profile or _profile_from_name("extended")
    available = {item.id: item for item in case.models}
    unknown = [item for item in model_ids if item not in available]
    if unknown:
        raise ValueError("unknown benchmark model ids: " + ", ".join(unknown))
    make_client: AdapterFactory
    if adapter_factory is _default_adapter_factory:
        def make_client(spec: ModelSpec, seed: int) -> BenchmarkLLMClient:
            return BenchmarkLLMClient(
                spec,
                seed,
                timeout_seconds=profile.call_timeout_seconds,
            )
    else:
        make_client = adapter_factory

    run_id = resume_run_id or run_id or f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = output_root / run_id
    writing_prompt_metadata = prompt_metadata_records()
    active_prompt_metadata = {
        prompt_id: writing_prompt_metadata[prompt_id]
        for prompt_id in (
            "cv_tailoring",
            "cover_letter_generation",
            "shared_factuality_contract",
            "shared_numeric_fidelity_contract",
        )
    }
    clean_before = _working_tree_clean()
    protected_before = _protected_hashes()
    _atomic_write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "case_id": case.case_id,
            "git_commit": _git_commit(),
            "input_hashes": case.input_hashes,
            "repository_hashes": _repository_hashes(),
            "prompt_versions": {
                prompt_id: metadata["prompt_version"]
                for prompt_id, metadata in writing_prompt_metadata.items()
            },
            "schema_versions": {
                "evidence_ledger": EVIDENCE_SCHEMA_VERSION,
                "writing_validation": VALIDATION_SCHEMA_VERSION,
                **{
                    prompt_id: metadata["schema_version"]
                    for prompt_id, metadata in writing_prompt_metadata.items()
                },
            },
            "models": [available[item].model_dump(mode="json") for item in model_ids],
            "seeds": case.seeds[:repetitions],
        },
    )

    by_model: dict[str, list[RepetitionResult]] = {model_id: [] for model_id in model_ids}
    started_run = time.monotonic()
    completion_state = "completed"

    if resume_run_id:
        progress_path = run_dir / "progress.json"
        if not progress_path.exists():
            raise ValueError(f"cannot resume unknown benchmark run: {resume_run_id}")
        previous = json.loads(progress_path.read_text(encoding="utf-8"))
        if previous.get("benchmark_profile") != profile.name:
            raise ValueError("cannot resume benchmark with a different profile")
        if previous.get("case_id") != case.case_id:
            raise ValueError("cannot resume benchmark with a different case")
        for model_id in model_ids:
            for repetition in range(1, repetitions + 1):
                path = run_dir / "runs" / model_id / f"{repetition:02d}" / "result.json"
                if not path.exists():
                    continue
                result = RepetitionResult.model_validate_json(path.read_text(encoding="utf-8"))
                if retry_timeouts and result.status in {"timeout", "interrupted"}:
                    continue
                by_model[model_id].append(result)

    async def execute_repetition(
        spec: ModelSpec, repetition: int, seed: int, client: Adapter
    ) -> RepetitionResult:
        started = time.monotonic()
        try:
            tailor = CVTailor(client, master_cv_loader=lambda: deepcopy_dict(case.master_cv))
            cv = await tailor.tailor(case.jd_analysis, variant="A")
            letter = await CoverLetterGenerator(client).generate(
                case.jd_analysis,
                cv,
                dict(case.master_cv.get("personal", {})),
                variant=select_tone_variant(case.jd_analysis),
                jd_text=case.job_description,
            )
            pair_score = score_pair(case, cv, letter)
            eligible = bool(pair_score.eligible and pair_score.combined is not None)
            exclusion = None if eligible else "blocked_by_hard_gate"
            provenance = letter.generation_provenance
            duration_ms = (time.monotonic() - started) * 1000
            pair_metrics = _pair_metrics(
                case,
                cv,
                letter,
                pair_score,
                list(client.observations),
                duration_ms,
            )
            result = RepetitionResult(
                model_id=spec.id,
                repetition=repetition,
                seed=seed,
                status="succeeded",
                availability="available",
                execution_status="completed",
                duration_ms=duration_ms,
                cv=cv.model_dump(mode="json"),
                cover_letter=letter.model_dump(mode="json"),
                score=pair_score,
                pair_metrics=pair_metrics,
                eligible_for_ranking=eligible,
                writing_quality_exclusion_reason=exclusion,
                first_pass_cover_letter_word_count=letter.first_pass_word_count or letter.word_count,
                final_cover_letter_word_count=letter.word_count,
                cover_letter_repair_count=letter.repair_count,
                numeric_fidelity_failures=_numeric_fidelity_failures(letter),
                observations=[
                    item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
                    for item in client.observations
                ],
                prompt_metadata=active_prompt_metadata,
                workflow_diagnostics=(
                    provenance.workflow if provenance is not None else None
                ),
            )
            return result
        except BenchmarkModelUnavailableError as exc:
            result = RepetitionResult(
                model_id=spec.id,
                repetition=repetition,
                seed=seed,
                status="unavailable",
                availability="unavailable",
                execution_status="unavailable",
                duration_ms=(time.monotonic() - started) * 1000,
                observations=[
                    item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
                    for item in client.observations
                ],
                prompt_metadata=active_prompt_metadata,
                writing_quality_exclusion_reason="model_unavailable",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return result
        except BenchmarkTimeoutError as exc:
            result = RepetitionResult(
                model_id=spec.id,
                repetition=repetition,
                seed=seed,
                status="timeout",
                availability="available",
                execution_status="timeout",
                timeout_stage="call",
                duration_ms=(time.monotonic() - started) * 1000,
                observations=[
                    item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
                    for item in client.observations
                ],
                prompt_metadata=active_prompt_metadata,
                writing_quality_exclusion_reason="call_timeout",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return result
        except Exception as exc:  # typed artifact boundary; remaining models continue
            result = RepetitionResult(
                model_id=spec.id,
                repetition=repetition,
                seed=seed,
                status="failed",
                availability="available",
                execution_status="failed",
                duration_ms=(time.monotonic() - started) * 1000,
                observations=[
                    item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
                    for item in client.observations
                ],
                prompt_metadata=active_prompt_metadata,
                writing_quality_exclusion_reason="execution_failed",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return result

    def persist_result(client: Adapter, result: RepetitionResult) -> None:
        artifact_dir = run_dir / "runs" / result.model_id / f"{result.repetition:02d}"
        _atomic_write_json(artifact_dir / "result.json", result.model_dump(mode="json"))
        _atomic_write_json(artifact_dir / "raw_responses.json", client.raw_responses)
        _atomic_write_json(
            run_dir / "models" / result.model_id / f"repetition-{result.repetition:03d}.json",
            _model_result_payload(result),
        )

    def refresh_outputs(state: str) -> BenchmarkSummary:
        summary = _summary_from_results(
            run_id=run_id,
            case=case,
            model_ids=model_ids,
            repetitions=repetitions,
            profile=profile,
            by_model=by_model,
            completion_state=state,
        )
        _write_run_outputs(
            run_dir=run_dir,
            summary=summary,
            run_id=run_id,
            case=case,
            model_ids=model_ids,
            repetitions=repetitions,
            profile=profile,
            by_model=by_model,
            available=available,
            clean_before=clean_before,
            protected_before=protected_before,
            completion_state=state,
        )
        return summary

    refresh_outputs("running")

    for model_id in model_ids:
        spec = available[model_id]
        for repetition, seed in enumerate(case.seeds[:repetitions], start=1):
            if any(item.repetition == repetition for item in by_model[model_id]):
                continue
            if time.monotonic() - started_run >= profile.whole_run_timeout_seconds:
                completion_state = "incomplete_deadline"
                return refresh_outputs(completion_state)
            client: Adapter | None = make_client(spec, seed)
            try:
                result = await asyncio.wait_for(
                    execute_repetition(spec, repetition, seed, client),
                    timeout=profile.model_timeout_seconds,
                )
            except asyncio.CancelledError as exc:
                result = RepetitionResult(
                    model_id=model_id,
                    repetition=repetition,
                    seed=seed,
                    status="interrupted",
                    availability="available",
                    execution_status="interrupted",
                    duration_ms=0.0,
                    observations=[
                        item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
                        for item in client.observations
                    ],
                    prompt_metadata=active_prompt_metadata,
                    writing_quality_exclusion_reason="run_interrupted",
                    error_type=type(exc).__name__,
                    error_message="benchmark run was interrupted",
                )
                by_model[model_id].append(result)
                try:
                    await asyncio.shield(client.aclose())
                except Exception:
                    pass
                closed_client = client
                client = None
                persist_result(closed_client, result)
                return refresh_outputs("incomplete_interrupted")
            except TimeoutError as exc:
                result = RepetitionResult(
                    model_id=model_id,
                    repetition=repetition,
                    seed=seed,
                    status="timeout",
                    availability="available",
                    execution_status="timeout",
                    timeout_stage="model",
                    duration_ms=profile.model_timeout_seconds * 1000,
                    prompt_metadata=active_prompt_metadata,
                    writing_quality_exclusion_reason="model_timeout",
                    error_type=type(exc).__name__,
                    error_message=f"{model_id} exceeded {profile.model_timeout_seconds} second model timeout",
                )
            finally:
                if client is not None:
                    await client.aclose()

            by_model[model_id].append(result)
            persist_result(client or _EmptyAdapter(), result)
            if result.status in {"failed", "unavailable", "timeout", "interrupted"}:
                completion_state = "completed_with_model_outcomes"
            all_attempted = all(len(by_model[item]) >= repetitions for item in model_ids)
            refresh_outputs(completion_state if all_attempted else "running")

    return refresh_outputs(completion_state)


def deepcopy_dict(value: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(value)
