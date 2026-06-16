"""Transparent empirical-Bayesian outcome learning and score caching."""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.tools.profile_loader import load_profile
from ..models.application import Application
from ..models.application_outcome import ApplicationOutcome
from ..models.application_score_snapshot import ApplicationScoreSnapshot
from ..models.job import JobPosting
from ..models.job_score import JobScore
from ..models.opportunity_score import OpportunityScore
from ..schemas.profile import OutcomeLearningConfig
from .outcome_feature_service import freshness, normalise_role_family

MODEL_VERSION = "outcome-v1"
SIGNAL_WEIGHTS = {"source": 0.30, "role_family": 0.25, "seniority": 0.10, "working_pattern": 0.15, "employment_type": 0.10, "freshness": 0.10}
POSITIVE = {"recruiter_response", "interview", "offer", "accepted"}
EXCLUDED = {"withdrawn", "declined"}


async def _dataset(db: AsyncSession, config: OutcomeLearningConfig, now: datetime) -> list[dict[str, Any]]:
    rows = (await db.execute(
        select(Application, ApplicationScoreSnapshot, ApplicationOutcome)
        .join(ApplicationScoreSnapshot, ApplicationScoreSnapshot.application_id == Application.id)
        .outerjoin(ApplicationOutcome, ApplicationOutcome.application_id == Application.id)
        .where(Application.applied_date.is_not(None))
        .order_by(Application.id)
    )).all()
    grouped: dict[str, dict[str, Any]] = {}
    for app, snapshot, outcome in rows:
        if config.learning_since and app.applied_date < config.learning_since.replace(tzinfo=None):
            continue
        item = grouped.setdefault(app.id, {"app": app, "snapshot": snapshot, "outcomes": set()})
        if outcome:
            item["outcomes"].add(outcome.outcome_type)
    resolved: list[dict[str, Any]] = []
    for item in grouped.values():
        app, outcomes = item["app"], item["outcomes"]
        if outcomes & EXCLUDED:
            continue
        if outcomes & POSITIVE:
            positive = True
        elif "rejected" in outcomes or (now - app.applied_date).days >= config.no_response_after_days:
            positive = False
        else:
            continue
        age_days = max(0, (now - app.applied_date).days)
        item.update(positive=positive, weight=0.5 ** (age_days / config.recency_half_life_days))
        resolved.append(item)
    return resolved


def _confidence(raw: int, effective: float, minimum: int, has_contributions: bool = True) -> str:
    if raw < minimum:
        return "insufficient"
    if effective < 20:
        return "low"
    if effective >= 50 and raw >= 75 and has_contributions:
        return "high"
    return "medium"


def _rates(rows: list[dict[str, Any]]) -> tuple[float, float, float]:
    positive = sum(r["weight"] for r in rows if r["positive"])
    negative = sum(r["weight"] for r in rows if not r["positive"])
    return (1.0 + positive) / (2.0 + positive + negative), positive, negative


def calculate_for_features(base_fit_score: float, features: dict[str, str], rows: list[dict[str, Any]], config: OutcomeLearningConfig) -> dict[str, Any]:
    raw_count = len(rows)
    effective = sum(r["weight"] for r in rows)
    global_rate, _, _ = _rates(rows)
    if not rows:
        global_rate = 0.0
    if not config.enabled or raw_count < config.minimum_total_applications:
        return {"base_fit_score": base_fit_score, "outcome_adjustment": 0.0, "opportunity_score": base_fit_score, "confidence": "insufficient", "raw_sample_size": raw_count, "effective_sample_size": round(effective, 6), "reasons": [], "signal_contributions": {}}
    contributions: dict[str, float] = {}
    reasons: list[dict[str, Any]] = []
    for signal in config.enabled_signals:
        value = features.get(signal) or "unknown"
        segment = [r for r in rows if getattr(r["snapshot"], "freshness_bucket" if signal == "freshness" else signal, "unknown") == value]
        if len(segment) < config.minimum_segment_size:
            continue
        segment_rate, _, _ = _rates(segment)
        contribution = max(-config.maximum_signal_adjustment, min(config.maximum_signal_adjustment, (segment_rate - global_rate) * SIGNAL_WEIGHTS[signal]))
        contribution = round(contribution, 6)
        contributions[signal] = contribution
        if abs(contribution) >= 0.005:
            direction = "positive" if contribution > 0 else "negative"
            reasons.append({"signal": signal, "value": value, "direction": direction, "contribution": contribution, "segment_rate": round(segment_rate, 6), "baseline_rate": round(global_rate, 6), "sample_size": len(segment), "message": f"Applications with this {signal.replace('_', ' ')} have received {'more' if contribution > 0 else 'fewer'} responses in your recent history."})
    adjustment = max(-config.maximum_score_adjustment, min(config.maximum_score_adjustment, sum(contributions.values())))
    adjustment = round(adjustment, 6)
    reasons.sort(key=lambda reason: abs(reason["contribution"]), reverse=True)
    return {"base_fit_score": round(base_fit_score, 6), "outcome_adjustment": adjustment, "opportunity_score": round(max(0.0, min(1.0, base_fit_score + adjustment)), 6), "confidence": _confidence(raw_count, effective, config.minimum_total_applications, bool(contributions)), "raw_sample_size": raw_count, "effective_sample_size": round(effective, 6), "reasons": reasons[:3], "signal_contributions": contributions}


def _variant_analytics(rows: list[dict[str, Any]], field: str, config: OutcomeLearningConfig) -> tuple[list[dict], dict | None]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = getattr(row["snapshot"], field)
        if value:
            grouped[value].append(row)
    stats = []
    for variant, items in sorted(grouped.items()):
        rate, _, _ = _rates(items)
        responses = sum(1 for item in items if item["positive"])
        effective = sum(item["weight"] for item in items)
        stats.append({"variant": variant, "total": len(items), "resolved": len(items), "responses": responses, "response_rate": round(responses / len(items), 6), "smoothed_response_rate": round(rate, 6), "effective_sample_size": round(effective, 6), "confidence": _confidence(len(items), effective, config.minimum_segment_size)})
    eligible = sorted((s for s in stats if s["resolved"] >= config.minimum_segment_size), key=lambda s: s["smoothed_response_rate"], reverse=True)
    recommendation = None
    if len(eligible) >= 2 and eligible[0]["smoothed_response_rate"] - eligible[1]["smoothed_response_rate"] >= 0.05:
        recommendation = {"document_type": "cv" if field == "cv_variant" else "cover_letter", "recommended_variant": eligible[0]["variant"], "reason": f"{('CV' if field == 'cv_variant' else 'Cover-letter')} variant {eligible[0]['variant']} has had a higher response rate in recent applications. This is correlation, not causation.", "sample_size": eligible[0]["resolved"], "confidence": eligible[0]["confidence"]}
    return stats, recommendation


async def recompute_active_jobs(db: AsyncSession, limit: int | None = None) -> dict[str, Any]:
    started = time.monotonic()
    config = load_profile().outcome_learning
    if not config.enabled:
        await db.execute(delete(OpportunityScore))
        await db.flush()
        return {"jobs_scanned": 0, "scores_created": 0, "scores_updated": 0, "scores_unchanged": 0, "insufficient_data": True, "model_version": MODEL_VERSION, "duration_ms": int((time.monotonic() - started) * 1000)}
    rows = await _dataset(db, config, datetime.utcnow())
    query = select(JobPosting, JobScore).join(JobScore, JobScore.job_id == JobPosting.id).where(JobPosting.is_active.is_(True)).order_by(JobPosting.id)
    if limit is not None:
        query = query.limit(limit)
    jobs = (await db.execute(query)).all()
    counters = {"jobs_scanned": len(jobs), "scores_created": 0, "scores_updated": 0, "scores_unchanged": 0}
    for job, score in jobs:
        _, freshness_bucket = freshness(job.posted_at, job.scraped_at)
        features = {"source": job.source or "unknown", "role_family": normalise_role_family(job.title), "seniority": job.seniority or "unknown", "working_pattern": job.working_pattern or "unknown", "employment_type": job.employment_type or "unknown", "freshness": freshness_bucket}
        result = calculate_for_features(score.overall_score, features, rows, config)
        cached = await db.scalar(select(OpportunityScore).where(OpportunityScore.job_id == job.id))
        values = {**result, "model_version": MODEL_VERSION, "calculated_at": datetime.utcnow()}
        if cached is None:
            db.add(OpportunityScore(job_id=job.id, **values))
            counters["scores_created"] += 1
        else:
            changed = any(getattr(cached, key) != value for key, value in result.items())
            for key, value in values.items():
                setattr(cached, key, value)
            counters["scores_updated" if changed else "scores_unchanged"] += 1
    await db.flush()
    return {**counters, "insufficient_data": len(rows) < config.minimum_total_applications, "model_version": MODEL_VERSION, "duration_ms": int((time.monotonic() - started) * 1000)}


async def build_summary(db: AsyncSession) -> dict[str, Any]:
    config = load_profile().outcome_learning
    rows = await _dataset(db, config, datetime.utcnow())
    effective = sum(row["weight"] for row in rows)
    positive = sum(1 for row in rows if row["positive"])
    global_rate, _, _ = _rates(rows)
    if not rows:
        global_rate = 0.0
    latest = await db.scalar(select(OpportunityScore.calculated_at).order_by(OpportunityScore.calculated_at.desc()).limit(1))
    reasons = [reason for reason_list in (await db.scalars(select(OpportunityScore.reasons))).all() for reason in (reason_list or [])]
    unique = {(r["signal"], r["value"], r["direction"]): r for r in reasons}.values()
    cv_stats, cv_rec = _variant_analytics(rows, "cv_variant", config)
    cl_stats, cl_rec = _variant_analytics(rows, "cl_variant", config)
    return {"enabled": config.enabled, "model_version": MODEL_VERSION, "confidence": _confidence(len(rows), effective, config.minimum_total_applications, bool(reasons)), "resolved_applications": len(rows), "effective_sample_size": round(effective, 6), "positive_responses": positive, "global_response_rate": round(global_rate, 6), "minimum_required": config.minimum_total_applications, "additional_required": max(0, config.minimum_total_applications - len(rows)), "learning_since": config.learning_since, "top_positive_signals": sorted((r for r in unique if r["direction"] == "positive"), key=lambda r: r["contribution"], reverse=True)[:3], "top_negative_signals": sorted((r for r in unique if r["direction"] == "negative"), key=lambda r: r["contribution"])[:3], "variant_recommendations": [r for r in (cv_rec, cl_rec) if r], "variant_performance": {"cv": cv_stats, "cover_letter": cl_stats}, "last_recomputed_at": latest}
