"""Tests for locale pack loading and validation — covers all target regions."""
from __future__ import annotations

import pytest

from app.services.locale_service import get_locale, list_locales, LocaleNotFoundError, get_coach_fillers


class TestLocaleService:
    """Verify all target locale packs load correctly."""

    def test_list_locales_includes_all_four_targets(self):
        locales = list_locales()
        locale_ids = [loc["id"] for loc in locales]
        assert "uk" in locale_ids, "UK locale missing"
        assert "in" in locale_ids, "India locale missing"
        assert "ae" in locale_ids, "UAE locale missing"
        assert "ie" in locale_ids, "Ireland locale missing"

    def test_uae_locale_has_required_fields(self):
        locale = get_locale("ae")
        assert locale["currency"] == "AED"
        assert locale["currency_symbol"] == "د.إ"
        assert any(f["id"] == "visa_status" for f in locale["legal_fields"]), \
            "UAE locale must have visa_status legal field"
        assert any(b["name"] == "bayt" for b in locale["job_boards"]), \
            "UAE locale must include Bayt.com"

    def test_ireland_locale_has_required_fields(self):
        locale = get_locale("ie")
        assert locale["currency"] == "EUR"
        assert locale["currency_symbol"] == "€"
        assert any(f["id"] == "work_permit" for f in locale["legal_fields"]), \
            "Ireland locale must have work_permit legal field"
        assert any(b["name"] == "irishjobs" for b in locale["job_boards"]), \
            "Ireland locale must include IrishJobs.ie"

    def test_uk_locale_still_loads(self):
        locale = get_locale("uk")
        assert locale["currency"] == "GBP"
        assert any(f["id"] == "ir35_preference" for f in locale["legal_fields"])

    def test_india_locale_still_loads(self):
        locale = get_locale("in")
        assert locale["currency"] == "INR"
        assert any(f["id"] == "notice_period" for f in locale["legal_fields"])

    def test_invalid_locale_raises_error(self):
        with pytest.raises(LocaleNotFoundError):
            get_locale("xx")

    def test_all_locales_have_job_boards(self):
        for locale in list_locales():
            if locale["id"].startswith("_"):
                continue
            config = get_locale(locale["id"])
            assert len(config.get("job_boards", [])) > 0, \
                f"Locale {locale['id']} has no job boards"

    def test_all_locales_have_rate_types(self):
        for locale in list_locales():
            if locale["id"].startswith("_"):
                continue
            config = get_locale(locale["id"])
            assert len(config.get("rate_types", [])) > 0, \
                f"Locale {locale['id']} has no rate types"

    def test_all_locales_have_scoring_defaults(self):
        for locale in list_locales():
            if locale["id"].startswith("_"):
                continue
            config = get_locale(locale["id"])
            defaults = config.get("scoring_defaults", {})
            weights = defaults.get("weights", {})
            assert "skill_match" in weights, \
                f"Locale {locale['id']} missing skill_match weight"
            assert "shortlist_threshold" in defaults, \
                f"Locale {locale['id']} missing shortlist_threshold"


class TestLocaleCoachFillers:
    """Coach filler word lists are available per locale with graceful fallback."""

    def test_get_coach_fillers_returns_list_for_uk(self) -> None:
        fillers = get_coach_fillers("uk")
        assert isinstance(fillers, list)
        assert len(fillers) > 0
        assert "um" in fillers

    def test_get_coach_fillers_all_active_locales(self) -> None:
        """Every active locale pack defines a non-empty coach.fillers list."""
        for locale in list_locales():
            if locale["id"].startswith("_"):
                continue
            fillers = get_coach_fillers(locale["id"])
            assert isinstance(fillers, list), f"Locale {locale['id']}: coach.fillers is not a list"
            assert len(fillers) > 0, f"Locale {locale['id']}: coach.fillers is empty"

    def test_get_coach_fillers_fallback_for_unknown_locale(self) -> None:
        """An unknown locale ID falls back to the default English filler list."""
        fillers = get_coach_fillers("xx")
        assert isinstance(fillers, list)
        assert len(fillers) > 0
        assert "um" in fillers

    def test_get_coach_fillers_german_locale_includes_german_words(self) -> None:
        """German locale coach.fillers includes German filler words (äh, also, eigentlich)."""
        fillers = get_coach_fillers("de")
        german_fillers = {"äh", "ähm", "also", "eigentlich"}
        assert german_fillers & set(fillers), \
            f"German locale should include German fillers but got: {fillers}"

    def test_get_coach_fillers_pack_specific_not_mixed(self) -> None:
        """get_coach_fillers returns exactly the fillers defined in the locale pack."""
        uk_fillers = get_coach_fillers("uk")
        de_fillers = get_coach_fillers("de")
        # German pack should include äh; UK pack should not
        assert "äh" in de_fillers
        assert "äh" not in uk_fillers
