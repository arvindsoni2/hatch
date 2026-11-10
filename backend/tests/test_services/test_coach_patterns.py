"""Deterministic practice-pattern derivation (spec §7.1, Appendix A)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from app.services.coach_conversational_progress import ProgressSnapshot
from app.services.coach_readiness.contracts import PatternPolicy
from app.services.coach_readiness.patterns import derive_patterns, explain_pattern

CONTRACT = "coach_conversational_report_v1"


def _snap(
    session_id: str,
    level: str,
    *,
    completed_at: datetime,
    dimension: str = "specificity",
    role_family: str | None = "Delivery Lead",
    interview_type: str | None = "behavioural",
    contract: str = CONTRACT,
    difficulty: str | None = "realistic",
    priorities: tuple[dict, ...] = (),
) -> ProgressSnapshot:
    return ProgressSnapshot(
        session_id=session_id,
        compatibility_key=f"key-{session_id}",
        activity_version=1,
        completed_at=completed_at,
        session_level=level,
        dimensions={dimension: level},
        role_family=role_family,
        role_level="senior",
        interview_type=interview_type,
        evaluation_contract_version=contract,
        difficulty=difficulty,
        priorities=priorities,
    )


def _find(patterns, dimension: str = "specificity"):
    return next(item for item in patterns if item.dimension == dimension)


def test_attempts_in_one_session_do_not_recur() -> None:
    moment = datetime(2026, 5, 1)
    first = _snap("session-1", "developing", completed_at=moment)
    retried = replace(
        first, activity_version=2, dimensions={"specificity": "needs_work"}
    )

    patterns = derive_patterns(
        [first, retried], frozenset(), PatternPolicy(), datetime(2026, 5, 2)
    )

    pattern = _find(patterns)
    assert pattern.kind == "forming"
    assert len(pattern.supporting) == 1


def test_difficulty_not_in_group() -> None:
    patterns = derive_patterns(
        [
            _snap(
                "easy", "developing", completed_at=datetime(2026, 5, 1),
                difficulty="supportive",
            ),
            _snap(
                "hard", "needs_work", completed_at=datetime(2026, 5, 2),
                difficulty="challenging",
            ),
        ],
        frozenset(),
        PatternPolicy(),
        datetime(2026, 5, 3),
    )

    assert len(patterns) == 1
    assert _find(patterns).kind == "focus"
    assert {item.difficulty for item in _find(patterns).supporting} == {
        "supportive", "challenging"
    }


def test_contract_versions_never_merge() -> None:
    patterns = derive_patterns(
        [
            _snap("v1-a", "developing", completed_at=datetime(2026, 5, 1)),
            _snap("v1-b", "needs_work", completed_at=datetime(2026, 5, 2)),
            _snap(
                "v2-a", "developing", completed_at=datetime(2026, 5, 3),
                contract="coach_conversational_report_v2",
            ),
            _snap(
                "v2-b", "needs_work", completed_at=datetime(2026, 5, 4),
                contract="coach_conversational_report_v2",
            ),
        ],
        frozenset(),
        PatternPolicy(),
        datetime(2026, 5, 5),
    )

    assert len(patterns) == 2
    assert {item.group.contract_version for item in patterns} == {
        CONTRACT, "coach_conversational_report_v2"
    }


def test_latest_three_kept_regardless_of_age_then_marked_stale() -> None:
    snapshots = [
        _snap("old-strong", "strong", completed_at=datetime(2026, 1, 1)),
        _snap("weak-1", "developing", completed_at=datetime(2026, 3, 1)),
        _snap("weak-2", "needs_work", completed_at=datetime(2026, 4, 1)),
        _snap("weak-3", "developing", completed_at=datetime(2026, 5, 1)),
    ]

    stale = _find(
        derive_patterns(snapshots, frozenset(), PatternPolicy(), datetime(2026, 9, 1))
    )
    fresh = _find(
        derive_patterns(snapshots, frozenset(), PatternPolicy(), datetime(2026, 5, 2))
    )

    assert stale.kind == "focus"
    assert [item.session_id for item in stale.supporting] == [
        "weak-1", "weak-2", "weak-3"
    ]
    assert stale.stale is True
    assert fresh.stale is False


def test_dismissal_reappears_on_new_support() -> None:
    first_two = [
        _snap("a", "developing", completed_at=datetime(2026, 5, 1)),
        _snap("b", "needs_work", completed_at=datetime(2026, 5, 2)),
    ]
    now = datetime(2026, 5, 3)
    original = _find(derive_patterns(first_two, frozenset(), PatternPolicy(), now))

    dismissed = _find(
        derive_patterns(
            first_two, frozenset({original.fingerprint}), PatternPolicy(), now
        )
    )
    assert dismissed.dismissed is True

    new_support = _find(
        derive_patterns(
            [*first_two, _snap("c", "developing", completed_at=now)],
            frozenset({original.fingerprint}),
            PatternPolicy(),
            datetime(2026, 5, 4),
        )
    )
    assert new_support.fingerprint != original.fingerprint
    assert new_support.dismissed is False

    undone = _find(
        derive_patterns(first_two, frozenset(), PatternPolicy(), now)
    )
    assert undone.dismissed is False


def test_trend_labels_respect_difficulty() -> None:
    def one(oldest: str, newest: str, old_diff: str, new_diff: str):
        return _find(
            derive_patterns(
                [
                    _snap(
                        "old", oldest, completed_at=datetime(2026, 5, 1),
                        difficulty=old_diff,
                    ),
                    _snap(
                        "new", newest, completed_at=datetime(2026, 5, 2),
                        difficulty=new_diff,
                    ),
                ],
                frozenset(),
                PatternPolicy(),
                datetime(2026, 5, 3),
            )
        )

    easier = one("needs_work", "developing", "realistic", "supportive")
    harder_decline = one(
        "interview_ready", "developing", "realistic", "challenging"
    )
    improving = one("developing", "interview_ready", "realistic", "realistic")
    declining = one("interview_ready", "developing", "realistic", "supportive")

    assert easier.trend_label == "easier_difficulty"
    assert harder_decline.trend_label == "harder_difficulty"
    assert improving.trend_label == "improving"
    assert declining.trend_label == "getting_weaker"


def test_why_is_deterministic_and_uses_stored_excerpts_only() -> None:
    snapshots = [
        _snap(
            "a", "developing", completed_at=datetime(2026, 5, 1),
            priorities=({"dimension": "specificity", "next_action": "Name the result."},),
        ),
        _snap(
            "b", "needs_work", completed_at=datetime(2026, 5, 2),
            priorities=(
                {"dimension": "specificity", "next_action": "Give one figure."},
                {"dimension": "clarity", "next_action": "Use shorter sentences."},
            ),
        ),
    ]
    pattern = _find(
        derive_patterns(snapshots, frozenset(), PatternPolicy(), datetime(2026, 5, 3))
    )

    why = explain_pattern(pattern, snapshots)
    again = explain_pattern(pattern, snapshots)

    assert why == again
    assert [item.text for item in why.excerpts] == [
        "Give one figure.", "Name the result."
    ]
    assert explain_pattern(replace(pattern, stale=True), snapshots) is None
