from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks import cli


def test_parser_exposes_five_subcommands() -> None:
    parser = cli.build_parser()
    subparsers = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
    )

    assert set(subparsers.choices) == {"validate", "init-case", "smoke", "run", "report"}


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

    assert exit_code == 2
    assert "missing required files" in capsys.readouterr().err
