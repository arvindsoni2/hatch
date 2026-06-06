"""Tests for UAE and Ireland locale packs loading correctly via the locale service."""
from __future__ import annotations


from app.services.locale_service import (
    get_locale,
    list_locales,
)


class TestAELocale:
    def test_ae_locale_loads(self):
        locale = get_locale("ae")
        assert locale["id"] == "ae"
        assert locale["name"] == "United Arab Emirates"
        assert locale["currency"] == "AED"

    def test_ae_has_legal_fields(self):
        locale = get_locale("ae")
        legal_fields = locale.get("legal_fields", [])
        field_ids = [f["id"] for f in legal_fields]
        assert "visa_status" in field_ids

    def test_ae_has_job_boards(self):
        locale = get_locale("ae")
        boards = locale.get("job_boards", [])
        board_names = [b["name"] for b in boards]
        assert "bayt" in board_names
        assert "linkedin" in board_names

    def test_ae_scoring_defaults(self):
        locale = get_locale("ae")
        scoring = locale.get("scoring_defaults", {})
        assert scoring.get("shortlist_threshold") == 0.70

    def test_ae_in_all_locales(self):
        all_locales = list_locales()
        ids = [lc["id"] for lc in all_locales]
        assert "ae" in ids


class TestIELocale:
    def test_ie_locale_loads(self):
        locale = get_locale("ie")
        assert locale["id"] == "ie"
        assert locale["name"] == "Ireland"
        assert locale["currency"] == "EUR"

    def test_ie_has_legal_fields(self):
        locale = get_locale("ie")
        legal_fields = locale.get("legal_fields", [])
        field_ids = [f["id"] for f in legal_fields]
        assert "work_permit" in field_ids
        assert "contract_type" in field_ids

    def test_ie_has_job_boards(self):
        locale = get_locale("ie")
        boards = locale.get("job_boards", [])
        board_names = [b["name"] for b in boards]
        assert "irishjobs" in board_names
        assert "linkedin" in board_names

    def test_ie_scoring_defaults(self):
        locale = get_locale("ie")
        scoring = locale.get("scoring_defaults", {})
        assert scoring.get("shortlist_threshold") == 0.75

    def test_ie_in_all_locales(self):
        all_locales = list_locales()
        ids = [lc["id"] for lc in all_locales]
        assert "ie" in ids
