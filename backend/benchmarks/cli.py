"""Command-line entry point for local writing model benchmarks."""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

from .adapters import BenchmarkLLMClient
from .case_loader import CaseValidationError, load_case
from .contracts import BenchmarkSummary
from .reporting import write_report
from .runner import run_benchmark

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

    initialise = commands.add_parser("init-case", help="Create a private benchmark case")
    initialise.add_argument("--case-id", required=True)
    initialise.add_argument("--destination", required=True, type=Path)
    initialise.add_argument("--master-cv", required=True, type=Path)
    initialise.add_argument("--job-description", required=True, type=Path)
    initialise.add_argument("--jd-analysis", required=True, type=Path)
    initialise.add_argument("--expected-facts", required=True, type=Path)

    smoke = commands.add_parser("smoke", help="Check every configured local model")
    smoke.add_argument("--case", required=True, type=Path)

    run = commands.add_parser("run", help="Run a complete benchmark")
    run.add_argument("--case", required=True, type=Path)
    run.add_argument("--models", required=True)
    run.add_argument("--repetitions", type=int, default=3)
    run.add_argument("--output-root", type=Path, default=Path("../data/benchmarks/results"))

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
        "expected_facts.json": args.expected_facts,
    }
    for target_name, source in sources.items():
        shutil.copyfile(Path(source).expanduser().resolve(), destination / target_name)
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
    case = load_case(args.case)
    model_ids = [item.strip() for item in args.models.split(",") if item.strip()]
    output_root = args.output_root.expanduser().resolve()
    private_root = (Path(__file__).resolve().parents[2] / "data" / "benchmarks").resolve()
    if not output_root.is_relative_to(private_root):
        print(
            f"WARNING: output path {output_root} is outside ignored {private_root}",
            file=sys.stderr,
        )
    summary = await run_benchmark(
        case,
        model_ids=model_ids,
        repetitions=args.repetitions,
        output_root=output_root,
    )
    run_dir = output_root / summary.run_id
    write_report(summary, run_dir / "report.md")
    print(f"Benchmark complete: {run_dir}")
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
        if args.command == "smoke":
            return asyncio.run(_smoke(args.case))
        if args.command == "run":
            return asyncio.run(_run(args))
        if args.command == "report":
            return _report(args.run)
    except (CaseValidationError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
