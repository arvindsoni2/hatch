from __future__ import annotations

from pathlib import Path

from benchmarks.coach.suite_loader import load_suite
from app.services.writing_contracts import stable_evidence_id

ROOT = Path(__file__).resolve().parents[4]
V1_SUITE = ROOT / "backend" / "benchmarks" / "coach" / "fixtures" / "v1"


def test_candidate_is_fictional_and_has_grounded_star_evidence() -> None:
    evidence = load_suite(V1_SUITE).candidate_evidence
    assert evidence["candidate"]["full_name"] == "Maya Chen-Fiction"
    assert len(evidence["roles"]) == 2
    assert len({item["evidence_id"] for item in evidence["evidence"]}) >= 6
    assert {"18%", "12", "240", "2023"} <= set(evidence["immutable_numeric_tokens"])
    assert evidence["unsupported_competency"] == "quantum cryptography"


def test_every_candidate_evidence_id_uses_existing_stable_rule() -> None:
    evidence = load_suite(V1_SUITE).candidate_evidence
    for item in evidence["evidence"]:
        assert item["evidence_id"] == stable_evidence_id(
            item["source_path"], item["text"]
        )


def test_job_description_contains_requirements_number_and_attack_fixture() -> None:
    suite = load_suite(V1_SUITE)
    normalized = suite.job_description.casefold()
    assert normalized.count("req-") >= 6
    assert "10,000" in suite.job_description
    assert "ignore previous instructions" in normalized


def test_fixed_research_bundle_uses_stable_source_ids() -> None:
    suite = load_suite(V1_SUITE)
    source_ids = {item["source_id"] for item in suite.company_research_sources["sources"]}
    assert source_ids == {"SRC-OFFICIAL-01", "SRC-OFFICIAL-02", "SRC-NEWS-01"}
    assert set(suite.company_research["source_ids"]) <= source_ids


def test_acceptance_smoke_flags_match_exact_six_scenarios() -> None:
    suite = load_suite(V1_SUITE)
    flagged = {item.scenario_id for item in suite.scenarios.values() if item.acceptance_smoke}
    assert flagged == {
        "qg_01_requirement_coverage",
        "ma_01_supported_star",
        "ma_02_insufficient_evidence",
        "ae_01_strong_answer",
        "ae_02_weak_answer",
        "sr_01_mixed_session_report",
    }


def test_public_fixture_has_no_known_private_identity_or_common_email() -> None:
    raw = "\n".join(path.read_text(encoding="utf-8") for path in sorted(V1_SUITE.rglob("*")) if path.is_file())
    normalized = raw.casefold()
    assert "arvind soni" not in normalized
    assert "@gmail.com" not in normalized
    assert "@outlook.com" not in normalized
    assert "@hotmail.com" not in normalized
