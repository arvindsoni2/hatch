from decimal import Decimal

from benchmarks.coach.scoring import (
    actionability_score,
    fraction_metric,
    normalize_text,
    precision_recall_score,
    weighted_stage_score,
    word_budget_score,
)


def test_fraction_uses_unrounded_decimal_and_half_up_display() -> None:
    metric = fraction_metric(2, 3)
    assert metric.exact == str(Decimal(2) / Decimal(3))
    assert metric.display == "66.7"


def test_fraction_with_empty_denominator_is_na() -> None:
    metric = fraction_metric(0, 0)
    assert metric.exact is None
    assert metric.display == "N/A"


def test_na_dimension_is_excluded_from_weight_normalisation() -> None:
    score = weighted_stage_score(
        {
            "grounding": (Decimal("80"), Decimal("0.6")),
            "tradeoff": (None, Decimal("0.4")),
        }
    )
    assert score == Decimal("80.0")


def test_word_budget_boundaries_are_exact() -> None:
    assert word_budget_score(10, 10, 20, 30) == Decimal("100")
    assert word_budget_score(21, 10, 20, 30) == Decimal("50")
    assert word_budget_score(31, 10, 20, 30) == Decimal("0")


def test_precision_recall_handles_missing_output() -> None:
    assert precision_recall_score(set(), {"expected"}) == Decimal("0.0")
    assert precision_recall_score(set(), set()) is None


def test_normalisation_preserves_configured_evidence_id() -> None:
    assert normalize_text("Use EVID-01, safely!", protected_ids=("EVID-01",)) == (
        "use evid-01 safely"
    )


def test_actionability_rewards_verb_focus_and_measure() -> None:
    assert actionability_score("Practise rollback checks for 15 minutes", [["rollback"]]) == Decimal("100")

