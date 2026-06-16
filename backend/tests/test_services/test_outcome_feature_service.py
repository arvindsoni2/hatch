from datetime import datetime

from app.services.outcome_feature_service import freshness, normalise_role_family


def test_role_family_is_deterministic_and_removes_noise() -> None:
    assert normalise_role_family("Senior Platform Engineering Manager") == "platform engineering manager"
    assert normalise_role_family("Contract Delivery Lead - 6 months") == "delivery"
    assert normalise_role_family(None) == "unknown"


def test_freshness_boundaries_and_future_dates() -> None:
    now = datetime(2026, 6, 15)
    assert freshness(datetime(2026, 6, 15), None, now) == (0, "0_3_days")
    assert freshness(datetime(2026, 6, 11), None, now) == (4, "4_7_days")
    assert freshness(datetime(2026, 5, 1), None, now) == (45, "31_plus_days")
    assert freshness(datetime(2026, 6, 20), None, now) == (0, "0_3_days")
    assert freshness(None, None, now) == (None, "unknown")
