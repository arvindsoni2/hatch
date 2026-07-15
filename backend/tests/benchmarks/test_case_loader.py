from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmarks.case_loader import CaseValidationError, hash_file, load_case
from benchmarks.contracts import ModelSpec


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def synthetic_case(tmp_path: Path) -> Path:
    case_dir = tmp_path / "synthetic-delivery"
    case_dir.mkdir()
    _write_json(
        case_dir / "case.json",
        {
            "case_id": "synthetic-delivery",
            "cv_length_tolerance": 0.1,
            "seeds": [11, 23, 41],
            "models": [
                {
                    "id": "qwen35-4b",
                    "runtime": "llamacpp",
                    "model": "Qwen_Qwen3.5-4B-Q4_K_M.gguf",
                    "endpoint": "http://127.0.0.1:8080",
                    "context_size": 16384,
                },
                {
                    "id": "gemma4-e2b",
                    "runtime": "ollama",
                    "model": "gemma4:e2b",
                    "endpoint": "http://localhost:11434",
                    "context_size": 16384,
                },
            ],
        },
    )
    _write_json(
        case_dir / "master_cv.json",
        {
            "personal": {"full_name": "Alex Example"},
            "summary_variants": {"delivery": "Delivery Manager."},
            "skills": {"delivery": {"category": "Delivery", "items": ["Scrum"]}},
            "experience": [
                {
                    "role": "Delivery Manager",
                    "company": "Example Ltd",
                    "period": "2020 - Present",
                    "achievements": [{"text": "Led a Scrum delivery team."}],
                }
            ],
            "education": [],
            "certifications": ["PSM I"],
        },
    )
    (case_dir / "job_description.txt").write_text(
        "Delivery Manager with Scrum and Kanban experience.", encoding="utf-8"
    )
    _write_json(
        case_dir / "jd_analysis.json",
        {
            "role_title": "Delivery Manager",
            "requirements": {"must_have": ["Scrum", "Kanban"]},
            "ats_keywords": {"methodologies": ["Scrum", "Kanban"]},
            "company_context": {"company_name": "Target Ltd", "sector": "software"},
        },
    )
    _write_json(
        case_dir / "expected_facts.json",
        {
            "roles": [
                {
                    "role": "Delivery Manager",
                    "company": "Example Ltd",
                    "period": "2020 - Present",
                    "achievement_count": 1,
                }
            ],
            "education": [],
            "certifications": ["PSM I"],
            "allowed_numeric_tokens": ["2020"],
            "approved_vocabulary": [],
        },
    )
    return case_dir


def test_load_case_validates_files_and_hashes(synthetic_case: Path) -> None:
    case = load_case(synthetic_case)

    assert case.case_id == "synthetic-delivery"
    assert case.jd_analysis.role_title == "Delivery Manager"
    assert [model.id for model in case.models] == ["qwen35-4b", "gemma4-e2b"]
    assert set(case.input_hashes) == {
        "case.json",
        "master_cv.json",
        "job_description.txt",
        "jd_analysis.json",
        "expected_facts.json",
    }
    assert case.input_hashes["job_description.txt"] == hash_file(
        synthetic_case / "job_description.txt"
    )


def test_load_case_reports_all_missing_files(tmp_path: Path) -> None:
    case_dir = tmp_path / "incomplete"
    case_dir.mkdir()

    with pytest.raises(CaseValidationError) as exc_info:
        load_case(case_dir)

    message = str(exc_info.value)
    assert "case.json" in message
    assert "master_cv.json" in message
    assert "expected_facts.json" in message


def test_model_spec_rejects_non_loopback_endpoint() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        ModelSpec(
            id="remote",
            runtime="ollama",
            model="remote-model",
            endpoint="https://example.com",
            context_size=16384,
        )


def test_model_spec_accepts_ipv6_loopback() -> None:
    model = ModelSpec(
        id="local",
        runtime="ollama",
        model="local-model",
        endpoint="http://[::1]:11434",
        context_size=16384,
    )

    assert model.id == "local"


def test_private_benchmark_directory_is_ignored() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    ignore_text = (repo_root / ".gitignore").read_text(encoding="utf-8")

    assert "data/benchmarks/" in ignore_text.splitlines()
