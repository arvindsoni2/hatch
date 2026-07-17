from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks import cli
from benchmarks.contracts import BenchmarkSummary, ModelAggregate, Recommendation


def test_parser_exposes_five_subcommands() -> None:
    parser = cli.build_parser()
    subparsers = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
    )

    assert set(subparsers.choices) == {"validate", "init-case", "smoke", "run", "report"}


def test_run_parser_accepts_acceptance_profile_and_resume() -> None:
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "run",
            "--case",
            "/tmp/case",
            "--models",
            "qwen35-4b",
            "--repetitions",
            "1",
            "--profile",
            "acceptance-smoke",
            "--resume",
            "run-123",
        ]
    )

    assert args.profile == "acceptance-smoke"
    assert args.resume == "run-123"


def test_acceptance_exit_code_allows_model_timeout_outcomes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_run_benchmark(*args, **kwargs) -> BenchmarkSummary:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "run_manifest.json").write_text(
            json.dumps({"commands": [{"command": "original", "exit_code": 0}]}),
            encoding="utf-8",
        )
        return BenchmarkSummary(
            run_id="run-1",
            case_id="delivery-manager",
            created_at="2026-07-16T12:00:00+00:00",
            benchmark_profile="acceptance-smoke",
            repetitions=1,
            selected_models=["qwen35-4b"],
            completion_state="completed_with_model_outcomes",
            models=[
                ModelAggregate(
                    model_id="qwen35-4b",
                    attempted=1,
                    succeeded=0,
                    failed=0,
                    unavailable=0,
                    timeout=1,
                    eligible=0,
                    hard_gate_pass_rate=0.0,
                )
            ],
            ranking=[],
            recommendation=Recommendation(
                classification="inconclusive",
                rationale=["No eligible output."],
                limitations=["Single case."],
            ),
        )

    monkeypatch.setattr(cli, "load_case", lambda path: object())
    monkeypatch.setattr(cli, "run_benchmark", fake_run_benchmark)

    exit_code = cli.main(
        [
            "run",
            "--case",
            "/tmp/case",
            "--models",
            "qwen35-4b",
            "--repetitions",
            "1",
            "--profile",
            "acceptance-smoke",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert exit_code == 3
    manifest = json.loads((tmp_path / "run-1" / "run_manifest.json").read_text(encoding="utf-8"))
    assert [command["command"] for command in manifest["commands"]] == [
        "original",
        "python -m benchmarks run --case /tmp/case --models qwen35-4b --repetitions 1 --profile acceptance-smoke --output-root "
        + str(tmp_path),
    ]


def test_run_command_text_records_resume_flags(tmp_path: Path) -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "run",
            "--case",
            "/tmp/case",
            "--models",
            "qwen35-4b",
            "--repetitions",
            "1",
            "--profile",
            "acceptance-smoke",
            "--resume",
            "run-123",
            "--retry-timeouts",
            "--output-root",
            str(tmp_path),
        ]
    )

    assert cli._run_command_text(args) == (
        "python -m benchmarks run --case /tmp/case --models qwen35-4b --repetitions 1 "
        f"--profile acceptance-smoke --resume run-123 --retry-timeouts --output-root {tmp_path}"
    )


def test_init_case_copies_only_declared_inputs(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    inputs = {
        "master_cv.json": {"personal": {"full_name": "Private Person"}},
        "jd_analysis.json": {"role_title": "Delivery Manager"},
        "expected_facts.json": {"roles": []},
    }
    paths: dict[str, Path] = {}
    for name, value in inputs.items():
        path = source / name
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    jd_path = source / "job_description.txt"
    jd_path.write_text("Delivery Manager job", encoding="utf-8")
    destination = tmp_path / "data" / "benchmarks" / "delivery"

    exit_code = cli.main(
        [
            "init-case",
            "--case-id",
            "delivery",
            "--destination",
            str(destination),
            "--master-cv",
            str(paths["master_cv.json"]),
            "--job-description",
            str(jd_path),
            "--jd-analysis",
            str(paths["jd_analysis.json"]),
            "--expected-facts",
            str(paths["expected_facts.json"]),
        ]
    )

    assert exit_code == 0
    assert {item.name for item in destination.iterdir()} == {
        "case.json",
        "master_cv.json",
        "job_description.txt",
        "jd_analysis.json",
        "expected_facts.json",
    }
    manifest = json.loads((destination / "case.json").read_text(encoding="utf-8"))
    assert [model["id"] for model in manifest["models"]] == [
        "qwen35-4b",
        "qwen35-9b",
        "qwen3-8b",
        "gemma4-e2b",
        "gemma4-e4b",
    ]


def test_validate_returns_nonzero_for_invalid_case(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["validate", "--case", str(tmp_path)])

    assert exit_code == 1
    assert "missing required files" in capsys.readouterr().err


def test_init_case_derives_expected_facts_from_master_cv(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    master_path = source / "master_cv.json"
    master_path.write_text(
        json.dumps(
            {
                "experience": [
                    {
                        "role": "Delivery Manager",
                        "company": "Example Ltd",
                        "period": "2020 - Present",
                        "achievements": [
                            {"text": "Led 3 delivery teams and improved flow by 20%."}
                        ],
                    }
                ],
                "education": [
                    {
                        "qualification": "BSc Computing",
                        "institution": "Example University",
                        "year": "2010",
                    }
                ],
                "certifications": ["PSM I"],
            }
        ),
        encoding="utf-8",
    )
    jd_path = source / "job_description.txt"
    jd_path.write_text("Delivery Manager job", encoding="utf-8")
    analysis_path = source / "jd_analysis.json"
    analysis_path.write_text(json.dumps({"role_title": "Delivery Manager"}), encoding="utf-8")
    destination = tmp_path / "data" / "benchmarks" / "derived"

    exit_code = cli.main(
        [
            "init-case",
            "--case-id",
            "derived",
            "--destination",
            str(destination),
            "--master-cv",
            str(master_path),
            "--job-description",
            str(jd_path),
            "--jd-analysis",
            str(analysis_path),
        ]
    )

    assert exit_code == 0
    facts = json.loads((destination / "expected_facts.json").read_text(encoding="utf-8"))
    assert facts["roles"] == [
        {
            "role": "Delivery Manager",
            "company": "Example Ltd",
            "period": "2020 - Present",
            "achievement_count": 1,
        }
    ]
    assert facts["education"][0]["qualification"] == "BSc Computing"
    assert facts["certifications"] == ["PSM I"]
    assert set(facts["allowed_numeric_tokens"]) == {"2020", "3", "20%", "2010"}
