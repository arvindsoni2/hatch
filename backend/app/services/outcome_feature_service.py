"""Deterministic, privacy-safe feature extraction for outcome learning."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

_NOISE = {
    "junior", "mid", "middle", "senior", "sr", "lead", "principal", "staff",
    "head", "director", "contract", "contractor", "temporary", "remote", "hybrid",
    "month", "months", "fixed", "term",
}


def normalise_role_family(title: str | None) -> str:
    if not title:
        return "unknown"
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b\d+\s*(?:month|months|year|years)\b", " ", text)
    tokens = re.sub(r"[^a-z0-9]+", " ", text).split()
    kept = [token for token in tokens if token not in _NOISE and not token.isdigit()]
    return " ".join(kept[:6]) or "unknown"


def freshness(posted_at: datetime | None, scraped_at: datetime | None, now: datetime | None = None) -> tuple[int | None, str]:
    source_date = posted_at or scraped_at
    if source_date is None:
        return None, "unknown"
    now = now or datetime.utcnow()
    days = max(0, (now.date() - source_date.date()).days)
    if days <= 3:
        bucket = "0_3_days"
    elif days <= 7:
        bucket = "4_7_days"
    elif days <= 14:
        bucket = "8_14_days"
    elif days <= 30:
        bucket = "15_30_days"
    else:
        bucket = "31_plus_days"
    return days, bucket
