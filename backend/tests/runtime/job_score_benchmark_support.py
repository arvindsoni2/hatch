"""Percentiles and derived comparisons over observed, never fabricated, scores."""

from math import ceil


def percentile(samples, percent):
    """Empirical nearest-rank percentile (rank=ceil(p*n), one based)."""
    if not samples or not 0 < percent <= 100:
        raise ValueError("nonempty samples and percentile in (0, 100] required")
    return sorted(samples)[ceil(percent * len(samples) / 100) - 1]


def summarize(rows):
    count = len(rows)
    comparable = [row for row in rows if "new_score" in row and "legacy_score" in row]
    timings = {
        f"{mode}_p{p}_ms": percentile([row[f"{mode}_latency_ms"] for row in rows], p)
        for mode in ("legacy", "new")
        for p in (50, 95)
    }
    return {
        "case_count": count,
        "schema_pass_count": len(comparable),
        "legacy_accuracy": sum(
            r["legacy_shortlist"] == r["expected_shortlist"] for r in rows
        )
        / count,
        "new_accuracy": sum(r["new_shortlist"] == r["expected_shortlist"] for r in rows)
        / count,
        "shortlist_agreement": sum(
            r["new_shortlist"] == r["legacy_shortlist"] for r in rows
        )
        / count,
        "delta_within_tolerance": sum(
            abs(r["new_score"] - r["legacy_score"]) <= 0.1 for r in comparable
        )
        / len(comparable),
        "delta_exceptions": [
            r["id"] for r in comparable if abs(r["new_score"] - r["legacy_score"]) > 0.1
        ],
        "timings": timings,
        "p50_ratio": timings["new_p50_ms"] / timings["legacy_p50_ms"],
        "p95_ratio": timings["new_p95_ms"] / timings["legacy_p95_ms"],
        "measurement_kind": "offline_local_keyword_real_database",
        "provider_gate_completed": False,
        "remote_cost_and_token_thresholds": "unmeasured",
    }
