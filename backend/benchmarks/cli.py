"""Command-line entry point for local writing model benchmarks."""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from .adapters import BenchmarkLLMClient
from .case_loader import CaseValidationError, load_case, load_suite
from .contracts import BenchmarkSummary
from .reporting import write_report, write_staged_report
from .runner import benchmark_profile, run_benchmark
from .staged_runner import (
    ProtectedStateChangedError,
    run_stage_suite,
    stage_metrics_from_progress,
)

_DEFAULT_MODELS = [
    {
        "id": "qwen35-4b",
        "runtime": "llamacpp",
        "model": "Qwen_Qwen3.5-4B-Q4_K_M.gguf",
        "endpoint": "http://127.0.0.1:8080",
        "context_size": 16384,
    },
    {
        "id": "qwen35-9b",
        "runtime": "ollama",
        "model": "qwen3.5:9b",
        "endpoint": "http://127.0.0.1:11434",
        "context_size": 16384,
    },
    {
        "id": "qwen3-8b",
        "runtime": "ollama",
        "model": "qwen3:8b",
        "endpoint": "http://127.0.0.1:11434",
        "context_size": 16384,
    },
    {
        "id": "gemma4-e2b",
        "runtime": "ollama",
        "model": "gemma4:e2b",
        "endpoint": "http://127.0.0.1:11434",
        "context_size": 16384,
    },
    {
        "id": "gemma4-e4b",
        "runtime": "ollama",
        "model": "gemma4:e4b",
        "endpoint": "http://127.0.0.1:11434",
        "context_size": 16384,
    },
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark local CV and cover-letter models")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="Validate a benchmark case without inference")
    validate.add_argument("--case", required=True, type=Path)

    validate_suite = commands.add_parser(
        "validate-suite",
        help="Validate the synthetic representative suite without inference",
    )
    validate_suite.add_argument("--suite", required=True, type=Path)

    initialise = commands.add_parser("init-case", help="Create a private benchmark case")
    initialise.add_argument("--case-id", required=True)
    initialise.add_argument("--destination", required=True, type=Path)
    initialise.add_argument("--master-cv", required=True, type=Path)
    initialise.add_argument("--job-description", required=True, type=Path)
    initialise.add_argument("--jd-analysis", required=True, type=Path)
    initialise.add_argument(
        "--expected-facts",
        type=Path,
        help="Optional reviewed facts JSON; otherwise derive protected facts from master CV",
    )

    smoke = commands.add_parser("smoke", help="Check every configured local model")
    smoke.add_argument("--case", required=True, type=Path)

    run = commands.add_parser("run", help="Run a complete benchmark")
    run.add_argument("--case", required=True, type=Path)
    run.add_argument("--models", required=True)
    run.add_argument("--repetitions", type=int, default=3)
    run.add_argument("--profile", choices=["acceptance-smoke", "extended"], default="extended")
    run.add_argument("--resume", help="Resume an existing benchmark run ID")
    run.add_argument(
        "--retry-timeouts",
        action="store_true",
        help="Retry timed-out/interrupted repetitions when resuming",
    )
    run.add_argument("--output-root", type=Path, default=Path("../data/benchmarks/results"))

    staged = commands.add_parser(
        "staged-run",
        help="Run or resume the representative staged model selection",
    )
    staged.add_argument("--suite", required=True, type=Path)
    staged.add_argument("--output-root", type=Path, default=Path("data/benchmarks/results"))
    staged.add_argument("--resume", help="Resume an existing staged run ID")
    staged.add_argument(
        "--defer-stage-c",
        action="store_true",
        help="Record benchmark_deferred instead of starting Stage C",
    )
    staged.add_argument(
        "--restart-evidence",
        action="append",
        default=[],
        type=Path,
        help="Fresh service-restart evidence; provide once per official run",
    )

    report = commands.add_parser("report", help="Regenerate Markdown from summary JSON")
    report.add_argument("--run", required=True, type=Path)
    return parser


def _init_case(args: argparse.Namespace) -> int:
    destination: Path = args.destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=False)
    sources = {
        "master_cv.json": args.master_cv,
        "job_description.txt": args.job_description,
        "jd_analysis.json": args.jd_analysis,
    }
    if args.expected_facts is not None:
        sources["expected_facts.json"] = args.expected_facts
    for target_name, source in sources.items():
        shutil.copyfile(Path(source).expanduser().resolve(), destination / target_name)
    if args.expected_facts is None:
        master = json.loads((destination / "master_cv.json").read_text(encoding="utf-8"))
        (destination / "expected_facts.json").write_text(
            json.dumps(_derive_expected_facts(master), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    manifest = {
        "case_id": args.case_id,
        "cv_length_tolerance": 0.1,
        "seeds": [11, 23, 41],
        "models": _DEFAULT_MODELS,
    }
    (destination / "case.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Created private benchmark case at {destination}")
    return 0


def _derive_expected_facts(master: dict) -> dict:
    roles = []
    for experience in master.get("experience", []):
        if not isinstance(experience, dict):
            continue
        roles.append(
            {
                "role": str(experience.get("role", "")),
                "company": str(experience.get("company", "")),
                "period": str(experience.get("period") or experience.get("dates") or ""),
                "achievement_count": len(experience.get("achievements", [])),
            }
        )
    education_fields = ("qualification", "institution", "year", "field", "location", "details")
    education = [
        {key: entry[key] for key in education_fields if key in entry and entry[key] not in (None, "", [])}
        for entry in master.get("education", [])
        if isinstance(entry, dict)
    ]
    flattened = json.dumps(master, ensure_ascii=False)
    numeric_tokens = list(
        dict.fromkeys(
            re.findall(
                r"(?:[£$€¥][\d,]+(?:\.\d+)?(?:[KMBkm+]*)|"
                r"\b\d[\d,]*(?:\.\d+)?(?:[KMBkm%+]*)(?!\w))",
                flattened,
                flags=re.IGNORECASE,
            )
        )
    )
    return {
        "roles": roles,
        "education": education,
        "certifications": [str(item) for item in master.get("certifications", [])],
        "allowed_numeric_tokens": numeric_tokens,
        "approved_vocabulary": [],
    }


def _run_command_text(args: argparse.Namespace) -> str:
    parts = [
        "python -m benchmarks run",
        f"--case {args.case}",
        f"--models {args.models}",
        f"--repetitions {args.repetitions}",
        f"--profile {args.profile}",
    ]
    if args.resume:
        parts.append(f"--resume {args.resume}")
    if args.retry_timeouts:
        parts.append("--retry-timeouts")
    parts.append(f"--output-root {args.output_root}")
    return " ".join(parts)


async def _smoke(case_path: Path) -> int:
    case = load_case(case_path)
    failures = 0
    for spec in case.models:
        client = BenchmarkLLMClient(spec, case.seeds[0], timeout_seconds=300)
        try:
            result = await client.complete_json(
                "Return a JSON object and do not explain.",
                'Return exactly {"ok": true}.',
                max_tokens=32,
            )
            ok = result.get("ok") is True
            print(f"{spec.id}: {'available' if ok else 'invalid response'}")
            failures += int(not ok)
        except Exception as exc:
            failures += 1
            print(f"{spec.id}: unavailable ({type(exc).__name__}: {exc})")
        finally:
            await client.aclose()
    return 1 if failures else 0


async def _run(args: argparse.Namespace) -> int:
    started_at = datetime.now(UTC).isoformat()
    case = load_case(args.case)
    model_ids = [item.strip() for item in args.models.split(",") if item.strip()]
    output_root = args.output_root.expanduser().resolve()
    private_root = (Path(__file__).resolve().parents[2] / "data" / "benchmarks").resolve()
    if not output_root.is_relative_to(private_root):
        print(
            f"WARNING: output path {output_root} is outside ignored {private_root}",
            file=sys.stderr,
        )
    profile = benchmark_profile(args.profile)
    summary = await run_benchmark(
        case,
        model_ids=model_ids,
        repetitions=args.repetitions,
        output_root=output_root,
        profile=profile,
        resume_run_id=args.resume,
        retry_timeouts=args.retry_timeouts,
    )
    run_dir = output_root / summary.run_id
    write_report(summary, run_dir / "report.md")
    ended_at = datetime.now(UTC).isoformat()
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    commands = list(manifest.get("commands") or [])
    commands.append(
        {
            "command": _run_command_text(args),
            "exit_code": _exit_code_for_summary(summary, manifest),
            "started_at": started_at,
            "ended_at": ended_at,
        }
    )
    manifest["commands"] = commands
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Benchmark complete: {run_dir}")
    return _exit_code_for_summary(summary, manifest)


async def _staged_run(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    output_root = args.output_root.expanduser().resolve()
    result = await run_stage_suite(
        suite,
        output_root=output_root,
        resume_run_id=args.resume,
        defer_stage_c=args.defer_stage_c,
        restart_evidence=args.restart_evidence,
    )
    run_dir = output_root / result.run_id
    write_staged_report(
        result,
        stage_metrics_from_progress(run_dir),
        run_dir / "report.md",
        protected_hashes_unchanged=True,
    )
    print(
        f"Staged benchmark {result.run_id}: {result.state}; "
        f"decision={result.decision.decision}"
    )
    return 4 if result.state == "incomplete_interrupted" else 0


def _exit_code_for_summary(summary: BenchmarkSummary, manifest: dict | None = None) -> int:
    if manifest and manifest.get("protected_hashes", {}).get("unchanged") is False:
        return 5
    if summary.completion_state == "incomplete_deadline":
        return 4
    if summary.completion_state == "incomplete_interrupted":
        return 4
    if any(model.failed or model.unavailable or model.timeout or model.interrupted for model in summary.models):
        return 3
    return 0


def _report(run_dir: Path) -> int:
    resolved = run_dir.expanduser().resolve()
    summary = BenchmarkSummary.model_validate_json(
        (resolved / "summary.json").read_text(encoding="utf-8")
    )
    write_report(summary, resolved / "report.md")
    print(f"Wrote {resolved / 'report.md'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init-case":
            return _init_case(args)
        if args.command == "validate":
            case = load_case(args.case)
            print(f"Valid case {case.case_id}: {', '.join(item.id for item in case.models)}")
            return 0
        if args.command == "validate-suite":
            suite = load_suite(args.suite)
            print(
                f"Valid suite {suite.suite_id}: {len(suite.cases)} cases, "
                f"{len(suite.models)} models"
            )
            return 0
        if args.command == "smoke":
            return asyncio.run(_smoke(args.case))
        if args.command == "run":
            return asyncio.run(_run(args))
        if args.command == "staged-run":
            return asyncio.run(_staged_run(args))
        if args.command == "report":
            return _report(args.run)
    except CaseValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ProtectedStateChangedError as exc:
        print(str(exc), file=sys.stderr)
        return 5
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
