from __future__ import annotations

import json
import math
import os
import re
import shutil
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmarks.coach import phase2_checks
from benchmarks.coach.phase2_adapter import build_prompt
from benchmarks.coach.runner import RunRequest, run_benchmark
from benchmarks.coach.suite_loader import SuiteValidationError, load_suite

PHASE2_ROOT = (
    Path(__file__).resolve().parents[3] / "benchmarks" / "coach" / "fixtures" / "phase2_v1"
)
_PERSONAL_EMAIL = re.compile(r"@[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE)
_PHONE = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"
)
_FORBIDDEN_MARKERS = ("arvind soni", "gmail", "outlook", "hotmail")


class _FakeLlamaHandler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        del args

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        system = request["messages"][0]["content"]
        payload = json.loads(request["messages"][1]["content"])
        match = re.search(r"BENCH_TASK=([a-z_]+)", system)
        assert match is not None
        task = match.group(1)
        if task == "explain":
            output = {"tips": ["Use the same wording as the excerpts."]}
        elif task == "brief_enhance":
            output = {
                "talking_points": [
                    {
                        "story_id": payload["stories"][0]["story_id"],
                        "text": "Open with the result and the team count.",
                    }
                ],
                "watch_outs": [],
            }
        elif task == "debrief_extract":
            output = {"questions": ["What would you change next time?"]}
        else:
            output = {"competencies": ["delivery leadership"]}
        content = json.dumps(output)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for start in range(0, len(content), 8):
            event = {
                "choices": [{"delta": {"content": content[start : start + 8]}}],
            }
            self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
            self.wfile.flush()
        final = {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 18},
            "timings": {"predicted_per_second": 40.0},
        }
        self.wfile.write(f"data: {json.dumps(final)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


@pytest.fixture
def fake_server(monkeypatch: pytest.MonkeyPatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeLlamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("HATCH_BENCH_SERVER_PID", str(os.getpid()))
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _strings(value: object) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return [value] if isinstance(value, str) else []


def _copy_suite(tmp_path: Path, endpoint: str) -> Path:
    target = tmp_path / "phase2_v1"
    shutil.copytree(PHASE2_ROOT, target)
    shutil.copy(PHASE2_ROOT.parent / "stopwords_en.txt", target.parent)
    models_path = target / "models.json"
    payload = json.loads(models_path.read_text(encoding="utf-8"))
    for model in payload["models"]:
        model["endpoint"] = endpoint
    models_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def _brief_case() -> dict:
    return {
        "brief_id": "brief-test",
        "input_fingerprint": "sha256:" + "1" * 64,
        "header": {
            "company": "Northwind Freight",
            "role": "Delivery Lead",
            "round_type": "behavioural",
        },
        "stories": [
            {
                "story_id": "story-migration",
                "title": "Safe migration",
                "text": "I led four teams and cut lead time from 9 to 4 days.",
                "competencies": ["delivery"],
                "score": 0.8,
            }
        ],
        "watch_outs": [
            {
                "fingerprint": "sha256:" + "a" * 64,
                "dimension": "specificity",
                "evidence": "Two sessions lacked a number.",
            }
        ],
    }


def _brief_output(story_id: str, text: str) -> dict:
    return {
        "talking_points": [{"story_id": story_id, "text": text}],
        "watch_outs": [],
    }


def test_suite_manifest_loads_48_cases_with_split() -> None:
    suite = load_suite(PHASE2_ROOT)

    assert suite.suite_id == "coach_phase2_v1"
    assert suite.fixture_kind == "phase2"
    assert len(suite.scenarios) == 48
    assert Counter(item.stage for item in suite.scenarios.values()) == {
        "explain": 15,
        "brief_enhance": 15,
        "debrief_extract": 10,
        "competency_extract": 8,
    }
    assert Counter(suite.split.values()) == {"tuning": 16, "holdout": 32}
    assert set(suite.split) == set(suite.scenarios)


def test_every_case_validates_against_its_task_schema() -> None:
    suite = load_suite(PHASE2_ROOT)

    for scenario in suite.scenarios.values():
        assert scenario.stage in phase2_checks.PHASE2_STAGES
        assert scenario.stage in phase2_checks.TASK_TIERS
        phase2_checks.validate_case_input(scenario.stage, scenario.input)


def test_a_third_of_each_task_is_near_its_input_maximum() -> None:
    suite = load_suite(PHASE2_ROOT)

    for stage in phase2_checks.PHASE2_STAGES:
        cases = [item for item in suite.scenarios.values() if item.stage == stage]
        threshold = 0.8 * phase2_checks.INPUT_MAX_CHARS[stage]
        sized = sum(
            phase2_checks.input_size_chars(stage, item.input) >= threshold
            for item in cases
        )
        assert sized >= math.ceil(len(cases) / 3), stage


def test_tier_t_cases_fit_the_context_budget() -> None:
    suite = load_suite(PHASE2_ROOT)

    for scenario in suite.scenarios.values():
        tier = phase2_checks.TASK_TIERS[scenario.stage]
        if tier != "T":
            continue
        system, user = build_prompt(scenario.stage, scenario.input)
        assert len(system) // 4 <= 300
        assert len(user) // 4 <= 1_200
        assert phase2_checks.TASK_OUTPUT_CAPS[tier] == 512


def test_tier_limits_and_deadlines_match_the_spec() -> None:
    assert phase2_checks.TASK_OUTPUT_CAPS == {"T": 512, "S": 600, "L": 600}
    assert phase2_checks.TIER_MAX_DEADLINE_SECONDS == {"T": 60, "S": 180, "L": 300}
    assert phase2_checks.TASK_TIERS == {
        "explain": "S",
        "brief_enhance": "S",
        "debrief_extract": "T",
        "competency_extract": "T",
    }


def test_fixture_text_has_no_personal_or_local_data() -> None:
    for path in sorted(PHASE2_ROOT.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for value in _strings(payload):
            normalized = value.casefold()
            assert not _PERSONAL_EMAIL.search(value), f"{path.name}: email"
            assert not _PHONE.search(value), f"{path.name}: phone"
            assert not any(marker in normalized for marker in _FORBIDDEN_MARKERS)
            assert not value.startswith("/"), f"{path.name}: absolute path"
            assert "data/" not in value, f"{path.name}: data path"


def test_phase2_models_are_loopback_and_loader_rejects_remote(
    tmp_path: Path,
) -> None:
    models = json.loads(
        (PHASE2_ROOT / "models.json").read_text(encoding="utf-8")
    )["models"]
    by_id = {item["id"]: item for item in models}
    assert by_id["phase2-tier-t"]["endpoint"] == "http://127.0.0.1:8081"
    assert by_id["phase2-tier-t"]["context_size"] == 2048
    assert by_id["phase2-tier-s"]["endpoint"] == "http://127.0.0.1:8080"
    assert by_id["phase2-tier-s"]["context_size"] == 16384

    remote = _copy_suite(tmp_path, "http://example.com:8080")
    with pytest.raises(SuiteValidationError, match="invalid Coach fixture contract"):
        load_suite(remote)


def test_grounding_accepts_supplied_ids_numbers_and_names() -> None:
    case = _brief_case()
    output = _brief_output(
        "story-migration", "Lead with the four teams and the 9 to 4 day result."
    )

    assert phase2_checks.grounding_violations("brief_enhance", output, case) == ()


def test_grounding_rejects_unknown_story_id() -> None:
    violations = phase2_checks.grounding_violations(
        "brief_enhance",
        _brief_output("story-unknown", "Lead with the four teams."),
        _brief_case(),
    )

    assert any("unknown_story_id" in item for item in violations)


def test_grounding_rejects_number_absent_from_story() -> None:
    violations = phase2_checks.grounding_violations(
        "brief_enhance",
        _brief_output("story-migration", "Lead with the 200 day result."),
        _brief_case(),
    )

    assert any("number_not_in_source" in item for item in violations)


def test_grounding_rejects_capitalised_name_absent_from_story() -> None:
    violations = phase2_checks.grounding_violations(
        "brief_enhance",
        _brief_output("story-migration", "Lead with the Northwind result."),
        _brief_case(),
    )

    assert any("name_not_in_source" in item for item in violations)


def test_grounding_rejects_over_limit_text() -> None:
    over_long = " ".join(["word"] * 41)
    violations = phase2_checks.grounding_violations(
        "explain",
        {"tips": [over_long]},
        {
            "dimension": "specificity",
            "rubric_description": "Name the system and the number.",
            "excerpts": [
                {
                    "excerpt_id": "ex-1",
                    "text": "I named the system and the number.",
                    "session_date": "2026-09-01",
                    "difficulty": "realistic",
                }
            ],
        },
    )

    assert any(item.startswith("schema:") for item in violations)


def test_output_contracts_enforce_task_limits() -> None:
    phase2_checks.validate_output("explain", {"tips": ["Name the system first."]})

    with pytest.raises(ValidationError):
        phase2_checks.validate_output("explain", {"tips": ["word " * 41]})
    with pytest.raises(ValidationError):
        phase2_checks.validate_output(
            "competency_extract",
            {"competencies": ["one", "two", "three", "four", "five"]},
        )


@pytest.mark.asyncio
async def test_phase2_bench_path_runs_all_four_stages_against_fake_server(
    tmp_path: Path, fake_server: str
) -> None:
    suite_path = _copy_suite(tmp_path, fake_server)
    request = RunRequest(
        suite_path=suite_path,
        output_root=tmp_path / "results",
        profile_name="phase2",
        model_ids=("phase2-tier-s",),
        command="pytest",
    )

    summary = await run_benchmark(request)

    assert len(summary.results) == 48
    assert {item.attempt.stage for item in summary.results} == set(
        phase2_checks.PHASE2_STAGES
    )
    assert all(item.status == "completed" for item in summary.results)
    for result in summary.results:
        assert result.metrics["latency_ms"] >= 0
        assert result.metrics["ttft_ms"] >= 0
        assert result.metrics["tokens_per_second"] > 0
        assert result.metrics["peak_rss_bytes"] > 0
        assert result.metrics["schema_valid"] is True
        assert result.metrics["grounding_violations"] == 0
