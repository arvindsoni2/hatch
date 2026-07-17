"""Sequential benchmark execution, atomic artifacts, and model aggregation."""
from __future__ import annotations

import json
import statistics
import subprocess
import time
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.services.cl_generator import CoverLetterGenerator, select_tone_variant
from app.services.cv_tailor import CVTailor
from app.services.writing_contracts import (
    EVIDENCE_SCHEMA_VERSION,
    VALIDATION_SCHEMA_VERSION,
    prompt_metadata_records,
)

from .adapters import BenchmarkLLMClient, BenchmarkModelUnavailableError
from .contracts import (
    BenchmarkCase,
    BenchmarkSummary,
    ModelAggregate,
    ModelSpec,
    Recommendation,
    RepetitionResult,
)
from .scoring import score_pair


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


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    latencies = [item.duration_ms for item in succeeded]
    gate_codes = Counter(
        finding.code
        for item in succeeded
        if item.score is not None
        for finding in item.score.gates
        if finding.blocking
    )
    attempted = len(results)
    return ModelAggregate(
        model_id=model_id,
        attempted=attempted,
        succeeded=len(succeeded),
        failed=sum(item.status == "failed" for item in results),
        unavailable=sum(item.status == "unavailable" for item in results),
        eligible=len(eligible),
        hard_gate_pass_rate=(len(eligible) / attempted if attempted else 0.0),
        median_cv_score=statistics.median(cv_scores) if cv_scores else None,
        median_cover_letter_score=statistics.median(cl_scores) if cl_scores else None,
        median_writing_score=statistics.median(scores) if scores else None,
        writing_score_variance=statistics.pvariance(scores) if len(scores) > 1 else (0.0 if scores else None),
        median_latency_ms=statistics.median(latencies) if latencies else None,
        gate_codes=dict(sorted(gate_codes.items())),
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


async def run_benchmark(
    case: BenchmarkCase,
    *,
    model_ids: list[str],
    repetitions: int,
    output_root: Path,
    adapter_factory: AdapterFactory = _default_adapter_factory,
    run_id: str | None = None,
) -> BenchmarkSummary:
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")
    if repetitions > len(case.seeds):
        raise ValueError(
            f"case defines {len(case.seeds)} seeds but {repetitions} repetitions were requested"
        )
    available = {item.id: item for item in case.models}
    unknown = [item for item in model_ids if item not in available]
    if unknown:
        raise ValueError("unknown benchmark model ids: " + ", ".join(unknown))

    run_id = run_id or f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
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
    for model_id in model_ids:
        spec = available[model_id]
        for repetition, seed in enumerate(case.seeds[:repetitions], start=1):
            client = adapter_factory(spec, seed)
            started = time.monotonic()
            artifact_dir = run_dir / "runs" / model_id / f"{repetition:02d}"
            try:
                tailor = CVTailor(client, master_cv_loader=lambda: deepcopy_dict(case.master_cv))
                cv = await tailor.tailor(case.jd_analysis, variant="A")
                letter = await CoverLetterGenerator(client).generate(
                    case.jd_analysis,
                    cv,
                    dict(case.master_cv.get("personal", {})),
                    variant=select_tone_variant(case.jd_analysis),
                )
                pair_score = score_pair(case, cv, letter)
                result = RepetitionResult(
                    model_id=model_id,
                    repetition=repetition,
                    seed=seed,
                    status="succeeded",
                    duration_ms=(time.monotonic() - started) * 1000,
                    cv=cv.model_dump(mode="json"),
                    cover_letter=letter.model_dump(mode="json"),
                    score=pair_score,
                    observations=[
                        item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
                        for item in client.observations
                    ],
                    prompt_metadata=active_prompt_metadata,
                )
            except BenchmarkModelUnavailableError as exc:
                result = RepetitionResult(
                    model_id=model_id,
                    repetition=repetition,
                    seed=seed,
                    status="unavailable",
                    duration_ms=(time.monotonic() - started) * 1000,
                    observations=[
                        item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
                        for item in client.observations
                    ],
                    prompt_metadata=active_prompt_metadata,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            except Exception as exc:  # typed artifact boundary; remaining repetitions continue
                result = RepetitionResult(
                    model_id=model_id,
                    repetition=repetition,
                    seed=seed,
                    status="failed",
                    duration_ms=(time.monotonic() - started) * 1000,
                    observations=[
                        item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
                        for item in client.observations
                    ],
                    prompt_metadata=active_prompt_metadata,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            finally:
                await client.aclose()

            by_model[model_id].append(result)
            _atomic_write_json(artifact_dir / "result.json", result.model_dump(mode="json"))
            _atomic_write_json(artifact_dir / "raw_responses.json", client.raw_responses)

    aggregates = [_model_aggregate(model_id, by_model[model_id]) for model_id in model_ids]
    ranking = sorted(aggregates, key=_ranking_key)
    summary = BenchmarkSummary(
        run_id=run_id,
        case_id=case.case_id,
        created_at=datetime.now(UTC).isoformat(),
        repetitions=repetitions,
        selected_models=model_ids,
        models=aggregates,
        ranking=ranking,
        recommendation=_recommend(aggregates, ranking),
    )
    _atomic_write_json(run_dir / "summary.json", summary.model_dump(mode="json"))
    return summary


def deepcopy_dict(value: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(value)
