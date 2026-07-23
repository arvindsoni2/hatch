from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks import cli as writing_cli
from benchmarks.coach import cli
from benchmarks.coach.contracts import CoachRunSummary

ROOT = Path(__file__).resolve().parents[4]
SUITE_PATH = ROOT / "backend/benchmarks/coach/fixtures/v1"


def _summary(state: str = "completed") -> CoachRunSummary:
    return CoachRunSummary(
        run_id="run-1",
        suite_id="hatch-coach-v1",
        suite_version="1.0.0",
        profile="acceptance-smoke",
        state=state,
        scheduled=0,
        terminal=0,
    )


def test_parser_exposes_only_coach_commands_and_bounded_timeout_flags() -> None:
    parser = cli.build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if action.__class__.__name__ == "_SubParsersAction"
    )
    assert set(subparsers.choices) == {"validate", "smoke", "run", "report"}

    args = parser.parse_args(
        [
            "run",
            "--suite",
            str(SUITE_PATH),
            "--models",
            "qwen35-4b,qwen35-9b",
            "--profile",
            "standard",
            "--resume",
            "run-1",
            "--retry-timeouts",
            "--call-timeout-seconds",
            "60",
            "--model-timeout-seconds",
            "120",
            "--run-timeout-seconds",
            "180",
        ]
    )
    assert args.retry_timeouts is True
    assert args.call_timeout_seconds == 60
    assert args.model_timeout_seconds == 120
    assert args.run_timeout_seconds == 180

    smoke_args = parser.parse_args(["smoke", "--suite", str(SUITE_PATH)])
    assert smoke_args.models is None
    assert smoke_args.profile == "contract-smoke"
    assert smoke_args.output_root == Path("../data/benchmarks/coach/results")


def test_existing_writing_parser_is_unchanged() -> None:
    assert writing_cli.build_parser().parse_args(
        ["smoke", "--case", "x"]
    ).command == "smoke"


def test_validate_reports_suite_counts(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["validate", "--suite", str(SUITE_PATH)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Valid Coach suite hatch-coach-model-quality-v1" in output
    assert "5 models" in output


def test_run_dispatches_request_and_reports_relative_run_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured = {}

    async def fake_run(request):
        captured["request"] = request
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        return _summary()

    monkeypatch.setattr(cli, "run_benchmark", fake_run)
    exit_code = cli.main(
        [
            "run",
            "--suite",
            str(SUITE_PATH),
            "--models",
            "qwen35-4b",
            "--profile",
            "acceptance-smoke",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert captured["request"].model_ids == ("qwen35-4b",)
    assert captured["request"].command.startswith("python -m benchmarks.coach run")
    output = capsys.readouterr().out
    assert "run-1" in output
    assert str(tmp_path.resolve()) not in output


def test_smoke_defaults_to_all_manifest_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = {}

    async def fake_run(request):
        captured["request"] = request
        (tmp_path / "run-1").mkdir()
        return _summary().model_copy(update={"profile": "contract-smoke"})

    monkeypatch.setattr(cli, "run_benchmark", fake_run)
    exit_code = cli.main(
        [
            "smoke",
            "--suite",
            str(SUITE_PATH),
            "--output-root",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert captured["request"].profile_name == "contract-smoke"
    assert captured["request"].model_ids == (
        "qwen35-4b",
        "qwen35-9b",
        "qwen3-8b",
        "gemma4-e2b",
        "gemma4-e4b",
    )


def test_resume_dispatches_retry_timeouts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    captured = {}

    async def fake_resume(path, retry_timeouts=False):
        captured.update(path=path, retry=retry_timeouts)
        return _summary()

    monkeypatch.setattr(cli, "resume_benchmark", fake_resume)
    exit_code = cli.main(
        [
            "run",
            "--suite",
            str(SUITE_PATH),
            "--models",
            "qwen35-4b",
            "--profile",
            "acceptance-smoke",
            "--resume",
            "run-1",
            "--retry-timeouts",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert captured == {"path": run_dir, "retry": True}


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("completed", 0),
        ("completed_with_model_outcomes", 3),
        ("incomplete_deadline", 4),
        ("incomplete_interrupted", 4),
        ("invalid_harness_privacy", 5),
        ("invalid_harness_integrity", 5),
    ],
)
def test_terminal_exit_codes(state: str, expected: int) -> None:
    assert cli.exit_code_for_summary(_summary(state)) == expected


def test_timeout_override_above_profile_bound_returns_argument_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(
        [
            "run",
            "--suite",
            str(SUITE_PATH),
            "--models",
            "qwen35-4b",
            "--profile",
            "acceptance-smoke",
            "--call-timeout-seconds",
            "601",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert exit_code == 2
    assert "locked profile bound" in capsys.readouterr().err


def test_retry_timeouts_requires_resume(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(
        [
            "run",
            "--suite",
            str(SUITE_PATH),
            "--models",
            "qwen35-4b",
            "--profile",
            "acceptance-smoke",
            "--retry-timeouts",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert exit_code == 2
    assert "requires --resume" in capsys.readouterr().err


def test_report_command_regenerates_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(_summary().model_dump(mode="json")), encoding="utf-8"
    )

    exit_code = cli.main(["report", "--run", str(run_dir)])

    assert exit_code == 0
    assert (run_dir / "report.md").is_file()
    output = capsys.readouterr().out
    assert "report.md" in output
    assert str(tmp_path.resolve()) not in output
