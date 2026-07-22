"""Separate command-line entry point for the Coach benchmark harness."""
from __future__ import annotations

import argparse
import asyncio
import shlex
import sys
from pathlib import Path

from .contracts import CoachRunSummary
from .reporting import write_report
from .runner import RunRequest, resume_benchmark, run_benchmark
from .suite_loader import SuiteValidationError, load_suite

_PROFILES = ("contract-smoke", "acceptance-smoke", "standard", "extended")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark local models on Hatch Coach")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="Validate a Coach benchmark suite")
    validate.add_argument("--suite", required=True, type=Path)

    smoke = commands.add_parser("smoke", help="Run deterministic Coach contract smoke")
    _add_run_arguments(
        smoke,
        profiles=("contract-smoke",),
        default="contract-smoke",
        require_models=False,
    )

    run = commands.add_parser("run", help="Run or resume a Coach benchmark")
    _add_run_arguments(
        run, profiles=_PROFILES[1:], default="standard", require_models=True
    )

    report = commands.add_parser("report", help="Regenerate a privacy-safe report")
    report.add_argument("--run", required=True, type=Path)
    return parser


def _add_run_arguments(
    parser: argparse.ArgumentParser,
    *,
    profiles: tuple[str, ...],
    default: str,
    require_models: bool,
) -> None:
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument(
        "--models",
        required=require_models,
        help="Comma-separated suite model IDs; smoke defaults to every suite model",
    )
    parser.add_argument("--profile", choices=profiles, default=default)
    parser.add_argument("--resume", help="Existing run ID under --output-root")
    parser.add_argument("--retry-timeouts", action="store_true")
    parser.add_argument("--call-timeout-seconds", type=float)
    parser.add_argument("--model-timeout-seconds", type=float)
    parser.add_argument("--run-timeout-seconds", type=float)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/benchmarks/coach/results"),
    )


def _model_ids(value: str) -> tuple[str, ...]:
    identifiers = tuple(item.strip() for item in value.split(",") if item.strip())
    if not identifiers:
        raise ValueError("at least one Coach model ID is required")
    return identifiers


def _command_text(args: argparse.Namespace, model_ids: tuple[str, ...]) -> str:
    parts = [
        "python",
        "-m",
        "benchmarks.coach",
        args.command,
        "--suite",
        str(args.suite),
        "--models",
        ",".join(model_ids),
        "--profile",
        args.profile,
        "--output-root",
        str(args.output_root),
    ]
    for option in ("call", "model", "run"):
        value = getattr(args, f"{option}_timeout_seconds")
        if value is not None:
            parts.extend([f"--{option}-timeout-seconds", str(value)])
    if args.resume:
        parts.extend(["--resume", args.resume])
    if args.retry_timeouts:
        parts.append("--retry-timeouts")
    return shlex.join(parts)


def exit_code_for_summary(summary: CoachRunSummary) -> int:
    if summary.state.startswith("invalid_harness_"):
        return 5
    if summary.state.startswith("incomplete_"):
        return 4
    if summary.state == "completed_with_model_outcomes":
        return 3
    return 0


async def _run(args: argparse.Namespace) -> int:
    output_root = args.output_root.expanduser().resolve()
    if args.retry_timeouts and not args.resume:
        raise ValueError("--retry-timeouts requires --resume")
    if args.resume:
        if any(
            value is not None
            for value in (
                args.call_timeout_seconds,
                args.model_timeout_seconds,
                args.run_timeout_seconds,
            )
        ):
            raise ValueError("timeout overrides cannot change when resuming a run")
        summary = await resume_benchmark(
            output_root / args.resume,
            retry_timeouts=args.retry_timeouts,
        )
    else:
        model_ids = (
            _model_ids(args.models)
            if args.models is not None
            else tuple(model.id for model in load_suite(args.suite).models)
        )
        request = RunRequest(
            suite_path=args.suite,
            output_root=output_root,
            profile_name=args.profile,
            model_ids=model_ids,
            command=_command_text(args, model_ids),
            call_timeout_seconds=args.call_timeout_seconds,
            model_timeout_seconds=args.model_timeout_seconds,
            run_timeout_seconds=args.run_timeout_seconds,
        )
        summary = await run_benchmark(request)
    run_dir = output_root / summary.run_id
    write_report(summary, run_dir / "report.md")
    print(f"Coach benchmark {summary.run_id}: {summary.state}; report=report.md")
    return exit_code_for_summary(summary)


def _report(run_dir: Path) -> int:
    resolved = run_dir.expanduser().resolve()
    summary = CoachRunSummary.model_validate_json(
        (resolved / "summary.json").read_text(encoding="utf-8")
    )
    write_report(summary, resolved / "report.md")
    print(f"Regenerated Coach report for {summary.run_id}: report.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            suite = load_suite(args.suite)
            print(
                f"Valid Coach suite {suite.suite_id}: "
                f"{len(suite.scenarios)} scenarios, {len(suite.models)} models"
            )
            return 0
        if args.command in {"smoke", "run"}:
            return asyncio.run(_run(args))
        if args.command == "report":
            return _report(args.run)
    except SuiteValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(type(exc).__name__, file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 2
