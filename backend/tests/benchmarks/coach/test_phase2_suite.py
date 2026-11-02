from __future__ import annotations

import json
import math
import os
import re
import shutil
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmarks.coach import phase2_adapter, phase2_checks
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


def _ungrounded_output(task: str, payload: dict) -> dict:
    if task == "explain":
        return {"tips": ["Open with Zephyr and the 999 day result."]}
    if task == "brief_enhance":
        return {
            "talking_points": [
                {"story_id": "story-unknown", "text": "Open with the result."}
            ],
            "watch_outs": [],
        }
    if task == "debrief_extract":
        return {"questions": ["What did Zephyr say about 999?"]}
    return {"competencies": ["delivery at Zephyr"]}


class _FakeLlamaHandler(BaseHTTPRequestHandler):
    mode = "valid"
    delay = 0.0

    def log_message(self, *args: object) -> None:
        del args

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        if request.get("stream_options", {}).get("include_usage") is not True:
            self.send_response(400)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.delay:
            time.sleep(self.delay)
        system = request["messages"][0]["content"]
        payload = json.loads(request["messages"][1]["content"])
        match = re.search(r"BENCH_TASK=([a-z_]+)", system)
        assert match is not None
        task = match.group(1)
        if self.mode == "bad_json":
            content = "this is not json"
        elif self.mode == "ungrounded":
            content = json.dumps(_ungrounded_output(task, payload))
        else:
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
        try:
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
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture
def fake_server_factory(monkeypatch: pytest.MonkeyPatch):
    servers: list[tuple[ThreadingHTTPServer, threading.Thread]] = []

    def start(mode: str = "valid", delay: float = 0.0) -> str:
        handler = type(
            "FakeLlamaHandler", (_FakeLlamaHandler,), {"mode": mode, "delay": delay}
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_address[1]}"

    monkeypatch.setenv("HATCH_BENCH_SERVER_PID", str(os.getpid()))
    try:
        yield start
    finally:
        for server, thread in servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


@pytest.fixture
def fake_server(fake_server_factory):
    return fake_server_factory("valid")


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


_STAGE_PREFIX = {
    "explain": "explain_",
    "brief_enhance": "brief_enhance_",
    "debrief_extract": "debrief_extract_",
    "competency_extract": "competency_extract_",
}


def _single_case_suite(tmp_path: Path, endpoint: str, stage: str) -> Path:
    target = _copy_suite(tmp_path, endpoint)
    suite_path = target / "suite.json"
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    name = next(
        item for item in suite["scenario_files"] if item.startswith(_STAGE_PREFIX[stage])
    )
    for item in suite["scenario_files"]:
        if item != name:
            (target / item).unlink()
    scenario_id = json.loads((target / name).read_text(encoding="utf-8"))[
        "scenario_id"
    ]
    suite["scenario_files"] = [name]
    suite["split"] = {scenario_id: "tuning"}
    suite_path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    return target


async def _run_single_case(suite_path: Path, output_root: Path):
    return await run_benchmark(
        RunRequest(
            suite_path=suite_path,
            output_root=output_root,
            profile_name="phase2",
            model_ids=("phase2-tier-s",),
            command="pytest",
        )
    )


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


def test_grounding_allowlists_star_and_rubric_words() -> None:
    case = {
        "dimension": "structure",
        "rubric_description": "Signals situation, task, action and result in order.",
        "excerpts": [
            {
                "excerpt_id": "ex-1",
                "text": "I named the system and the number.",
                "session_date": "2026-09-01",
                "difficulty": "realistic",
            }
        ],
    }
    output = {
        "tips": [
            "Open with the system you worked on, then give one number. "
            "Use the STAR structure for the Situation."
        ]
    }

    assert phase2_checks.grounding_violations("explain", output, case) == ()


def test_explain_excerpts_are_capped_at_two() -> None:
    excerpt = {
        "excerpt_id": "ex-1",
        "text": "I named the system and the number.",
        "session_date": "2026-09-01",
        "difficulty": "realistic",
    }
    with pytest.raises(ValidationError):
        phase2_checks.validate_case_input(
            "explain",
            {
                "dimension": "structure",
                "rubric_description": "Signals situation, task, action and result.",
                "excerpts": [excerpt, excerpt, excerpt],
            },
        )


@pytest.mark.asyncio
async def test_phase2_bench_path_marks_bad_json_invalid(
    tmp_path: Path, fake_server_factory
) -> None:
    suite_path = _single_case_suite(
        tmp_path / "bad_json", fake_server_factory("bad_json"), "explain"
    )

    summary = await _run_single_case(suite_path, tmp_path / "bad_json_results")

    result = summary.results[0]
    assert result.status == "invalid"
    assert result.metrics["schema_valid"] is False
    assert any(
        gate.code == "coach_stage_failed" and gate.blocking for gate in result.gates
    )


@pytest.mark.asyncio
async def test_phase2_bench_path_marks_ungrounded_output_invalid(
    tmp_path: Path, fake_server_factory
) -> None:
    suite_path = _single_case_suite(
        tmp_path / "ungrounded", fake_server_factory("ungrounded"), "brief_enhance"
    )

    summary = await _run_single_case(suite_path, tmp_path / "ungrounded_results")

    result = summary.results[0]
    assert result.status == "invalid"
    assert result.metrics["schema_valid"] is True
    assert result.metrics["grounding_violations"] > 0
    assert any(
        gate.code == "coach_stage_failed" and gate.blocking for gate in result.gates
    )


@pytest.mark.asyncio
async def test_phase2_bench_path_times_out_instead_of_hanging(
    tmp_path: Path,
    fake_server_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        phase2_adapter,
        "TIER_MAX_DEADLINE_SECONDS",
        {"T": 0.02, "S": 0.02, "L": 0.02},
    )
    suite_path = _single_case_suite(
        tmp_path / "timeout",
        fake_server_factory("valid", delay=0.2),
        "debrief_extract",
    )

    summary = await _run_single_case(suite_path, tmp_path / "timeout_results")

    result = summary.results[0]
    assert result.status == "timeout"
    assert result.timeout_stage in {"call", "model"}


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
