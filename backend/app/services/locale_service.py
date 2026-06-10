"""Locale pack service — loads YAML locale definitions and provides locale config."""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Locale packs: try repo-root (local dev) then /app/locales (Docker bind-mount)
def _find_locales_dir() -> Path:
    candidates = [
        Path(__file__).resolve().parents[3] / "locales",  # local: .../Job_Pilot_v2/locales
        Path("/app/locales"),                               # Docker bind-mount
        Path(__file__).resolve().parents[2] / "locales",  # fallback: backend/locales
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # return first candidate even if missing (triggers warning in _load_all)

_LOCALES_DIR = _find_locales_dir()


class LocaleNotFoundError(ValueError):
    pass


@lru_cache(maxsize=None)
def _load_all() -> dict[str, dict[str, Any]]:
    """Load and cache all locale YAML files from the locales/ directory."""
    packs: dict[str, dict[str, Any]] = {}
    if not _LOCALES_DIR.exists():
        logger.warning("locales/ directory not found at %s", _LOCALES_DIR)
        return packs

    for path in sorted(_LOCALES_DIR.glob("*.yaml")):
        if path.stem.startswith("_"):
            continue  # skip _template.yaml and similar meta files
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "id" not in data:
                logger.warning("Skipping malformed locale file: %s", path)
                continue
            packs[data["id"]] = data
        except yaml.YAMLError as exc:
            logger.warning("Failed to parse locale file %s: %s", path, exc)

    return packs


def get_locale(locale_id: str) -> dict[str, Any]:
    """Return the locale pack for *locale_id*.

    Raises LocaleNotFoundError if the locale is not installed.
    """
    packs = _load_all()
    if locale_id not in packs:
        raise LocaleNotFoundError(f"Locale '{locale_id}' not found. Available: {list(packs)}")
    return packs[locale_id]


def list_locales() -> list[dict[str, Any]]:
    """Return a summary list of all available locales (id, name, flag, currency, default_rate_type)."""
    return [
        {
            "id": pack["id"],
            "name": pack["name"],
            "flag": pack.get("flag", ""),
            "currency": pack.get("currency", ""),
            "currency_symbol": pack.get("currency_symbol", ""),
            "default_rate_type": pack.get("default_rate_type", "annual"),
        }
        for pack in _load_all().values()
    ]


def get_scoring_context(locale_id: str, legal_preferences: dict[str, str]) -> str:
    """Return the scoring_context string with legal_preferences values interpolated.

    Used by scorer_agent to inject locale-aware context into the scoring prompt.
    """
    try:
        pack = get_locale(locale_id)
    except LocaleNotFoundError:
        return ""
    template: str = pack.get("scoring_context", "")
    try:
        return template.format_map(legal_preferences)
    except KeyError as exc:
        logger.debug("scoring_context template missing key %s for locale %s", exc, locale_id)
        return template


def get_job_boards(locale_id: str, *, enabled_only: bool = True) -> list[dict[str, Any]]:
    """Return job board configs for a locale, optionally filtering to enabled ones."""
    try:
        pack = get_locale(locale_id)
    except LocaleNotFoundError:
        return []
    boards: list[dict[str, Any]] = pack.get("job_boards", [])
    if enabled_only:
        return [b for b in boards if b.get("enabled", False)]
    return boards


def get_onboarding_defaults(locale_id: str) -> dict[str, Any]:
    """Return the onboarding_defaults section for a locale."""
    try:
        pack = get_locale(locale_id)
    except LocaleNotFoundError:
        return {}
    return pack.get("onboarding_defaults", {})


_DEFAULT_COACH_FILLERS: list[str] = [
    "um", "uh", "er", "ah", "hmm",
    "basically", "literally", "actually", "honestly",
    "you know", "right", "like", "so",
    "kind of", "sort of",
]


def get_coach_fillers(locale_id: str) -> list[str]:
    """Return the coach filler word list for *locale_id*.

    Falls back to the default English list when the locale pack doesn't define
    a coach.fillers key, or when the locale_id is not found.
    """
    try:
        pack = get_locale(locale_id)
    except LocaleNotFoundError:
        return list(_DEFAULT_COACH_FILLERS)
    fillers = pack.get("coach", {}).get("fillers")
    if not fillers:
        return list(_DEFAULT_COACH_FILLERS)
    return list(fillers)


_DEFAULT_COACH_VOICE = "en_GB-alan-medium"
_DEFAULT_ASR_LANGUAGE = "en"


def get_coach_voice(locale_id: str) -> str:
    """Return the Piper TTS voice identifier for *locale_id*.

    Falls back to en_GB-alan-medium when the locale pack doesn't define coach.voice.
    """
    try:
        pack = get_locale(locale_id)
    except LocaleNotFoundError:
        return _DEFAULT_COACH_VOICE
    return pack.get("coach", {}).get("voice") or _DEFAULT_COACH_VOICE


def get_coach_asr_language(locale_id: str) -> str:
    """Return the Whisper ASR language hint (BCP-47 language code) for *locale_id*.

    Falls back to 'en' when the locale pack doesn't define coach.asr_language.
    """
    try:
        pack = get_locale(locale_id)
    except LocaleNotFoundError:
        return _DEFAULT_ASR_LANGUAGE
    return pack.get("coach", {}).get("asr_language") or _DEFAULT_ASR_LANGUAGE


def get_legal_fields(locale_id: str) -> list[dict[str, Any]]:
    """Return legal_fields definitions for the onboarding wizard."""
    try:
        pack = get_locale(locale_id)
    except LocaleNotFoundError:
        return []
    return pack.get("legal_fields", [])


_LOCALE_TIMEZONES: dict[str, str] = {
    "uk": "Europe/London",
    "ie": "Europe/Dublin",
    "de": "Europe/Berlin",
    "in": "Asia/Kolkata",
    "ae": "Asia/Dubai",
    "us": "America/New_York",
}
_DEFAULT_TIMEZONE = "UTC"


def get_digest_timezone(locale_id: str) -> str:
    """Return the IANA timezone for digest scheduling, derived from locale.

    Falls back to UTC when the locale has no mapping.
    """
    return _LOCALE_TIMEZONES.get(locale_id, _DEFAULT_TIMEZONE)
