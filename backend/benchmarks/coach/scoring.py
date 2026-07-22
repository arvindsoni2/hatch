"""Exact deterministic quality scoring for Coach benchmark stage outputs."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations
from typing import Any, Iterable

from .contracts import CoachScenario, FractionMetric
from .production_adapter import StageExecution
from .validators import ValidationResult

_ONE = Decimal("0.1")
_ACTION_VERBS = {
    "build",
    "check",
    "compare",
    "create",
    "define",
    "deliver",
    "draft",
    "explain",
    "identify",
    "measure",
    "practise",
    "prioritise",
    "record",
    "review",
    "run",
    "test",
    "validate",
    "verify",
}
_MEASURABLE = re.compile(
    r"\b\d+(?:\.\d+)?\b|%|\b(?:minute|hour|day|week|deliverable|criterion|criteria|success condition|timebox)s?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScenarioScore:
    dimensions: dict[str, str | None]
    quality_score: str | None


def _round(value: Decimal) -> Decimal:
    return value.quantize(_ONE, rounding=ROUND_HALF_UP)


def _display(value: Decimal | None) -> str | None:
    return None if value is None else format(_round(value), "f")


def fraction_metric(numerator: int, denominator: int) -> FractionMetric:
    if denominator == 0:
        return FractionMetric(numerator=numerator, denominator=0, exact=None, display="N/A")
    exact = Decimal(numerator) / Decimal(denominator)
    return FractionMetric(
        numerator=numerator,
        denominator=denominator,
        exact=str(exact),
        display=format(_round(exact * 100), "f"),
    )


def pct(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(100) * Decimal(numerator) / Decimal(denominator)


def normalize_text(text: str, *, protected_ids: Iterable[str] = ()) -> str:
    value = unicodedata.normalize("NFKC", str(text)).casefold()
    replacements: dict[str, str] = {}
    for index, protected in enumerate(sorted(protected_ids, key=len, reverse=True)):
        token = f"zzprotected{index}zz"
        normalized_id = unicodedata.normalize("NFKC", protected).casefold()
        value = value.replace(normalized_id, token)
        replacements[token] = normalized_id
    value = re.sub(r"[^\w\s]", " ", value)
    value = " ".join(value.split())
    for token, protected in replacements.items():
        value = value.replace(token, protected)
    return value


def token_set(
    text: str,
    stopwords: Iterable[str] = (),
    *,
    protected_ids: Iterable[str] = (),
) -> set[str]:
    stopped = {item.casefold() for item in stopwords}
    return {
        token
        for token in normalize_text(text, protected_ids=protected_ids).split()
        if token not in stopped
    }


def term_group_coverage(text: str, groups: list[list[str]]) -> Decimal | None:
    if not groups:
        return None
    normalized = normalize_text(text)
    matched = sum(
        any(normalize_text(alternative) in normalized for alternative in group)
        for group in groups
    )
    return pct(matched, len(groups))


def precision_recall_score(observed: set[str], expected: set[str]) -> Decimal | None:
    if not observed and not expected:
        return None
    precision = pct(len(observed & expected), len(observed)) if observed else Decimal(0)
    recall = pct(len(observed & expected), len(expected)) if expected else Decimal(100)
    return _round((precision + recall) / Decimal(2))


def weighted_stage_score(
    dimensions: dict[str, tuple[Decimal | None, Decimal]]
) -> Decimal | None:
    applicable = [(score, weight) for score, weight in dimensions.values() if score is not None]
    total_weight = sum((weight for _, weight in applicable), Decimal(0))
    if not applicable or total_weight == 0:
        return None
    return _round(sum(score * weight for score, weight in applicable) / total_weight)


def word_budget_score(words: int, minimum: int, target_max: int, hard_max: int) -> Decimal:
    if words == 0 or words > hard_max:
        return Decimal(0)
    if minimum <= words <= target_max:
        return Decimal(100)
    return Decimal(50)


def actionability_score(text: str, focus_groups: list[list[str]]) -> Decimal:
    tokens = token_set(text)
    verb = Decimal(40) if tokens & _ACTION_VERBS else Decimal(0)
    focus = Decimal(30) if (term_group_coverage(text, focus_groups) or 0) > 0 else Decimal(0)
    measurable = Decimal(30) if _MEASURABLE.search(text) else Decimal(0)
    return verb + focus + measurable


def readability_score(
    text: str,
    *,
    minimum: int = 1,
    maximum: int = 80,
    banned_phrases: Iterable[str] = (),
) -> Decimal:
    words = text.split()
    budget = Decimal(40) if minimum <= len(words) <= maximum else Decimal(0)
    sentences = [item.split() for item in re.split(r"[.!?]+", text) if item.strip()]
    sentence_score = Decimal(20) if all(len(item) <= 45 for item in sentences) else Decimal(0)
    normalized = normalize_text(text)
    generic = Decimal(20) if not any(normalize_text(item) in normalized for item in banned_phrases) else Decimal(0)
    valid = Decimal(20) if text.strip() else Decimal(0)
    return budget + sentence_score + generic + valid


def _question_score(scenario: CoachScenario, output: dict[str, Any]) -> dict[str, Decimal | None]:
    questions = [item for item in output.get("questions", []) if isinstance(item, dict)]
    requirement_ids = {str(item.get("requirement_id")) for item in questions}
    accepted = set(scenario.scoring.accepted_requirement_ids)
    required = set(scenario.scoring.required_requirement_ids)
    precision = pct(len(requirement_ids & accepted), len(requirement_ids)) if requirement_ids else Decimal(0)
    recall = pct(len(requirement_ids & required), len(required)) if required else None
    requirement = precision if recall is None else (precision + recall) / Decimal(2)
    expected_counts = scenario.scoring.expected_category_counts
    actual_counts = {
        category: sum(item.get("category") == category for item in questions)
        for category in set(expected_counts) | {str(item.get("category")) for item in questions}
    }
    distribution = None
    if questions and expected_counts:
        delta = sum(abs(actual_counts.get(key, 0) - expected_counts.get(key, 0)) for key in actual_counts)
        distribution = max(Decimal(0), Decimal(100) * (Decimal(1) - Decimal(delta) / (Decimal(2) * len(questions))))
    specificity_values: list[Decimal] = []
    for item in questions:
        text = str(item.get("text", ""))
        groups = scenario.scoring.specificity_term_groups_by_requirement.get(
            str(item.get("requirement_id")), []
        )
        if (term_group_coverage(text, groups) or 0) > 0:
            specificity_values.append(Decimal(100))
        elif (term_group_coverage(text, scenario.scoring.role_relevance_term_groups) or 0) > 0:
            specificity_values.append(Decimal(50))
        else:
            specificity_values.append(Decimal(0))
    specificity = sum(specificity_values) / len(specificity_values) if specificity_values else None
    similarities: list[Decimal] = []
    for left, right in combinations(questions, 2):
        left_tokens = token_set(str(left.get("text", "")))
        right_tokens = token_set(str(right.get("text", "")))
        union = left_tokens | right_tokens
        similarities.append(Decimal(len(left_tokens & right_tokens)) / len(union) if union else Decimal(0))
    diversity = Decimal(100) * (Decimal(1) - sum(similarities) / len(similarities)) if similarities else None
    clarity_values = []
    for item in questions:
        text = str(item.get("text", ""))
        words = len(text.split())
        clarity_values.append(
            (Decimal(40) if 8 <= words <= 40 else Decimal(0))
            + (Decimal(20) if text.rstrip().endswith("?") else Decimal(0))
            + (Decimal(20) if text.count("?") == 1 else Decimal(0))
            + (
                Decimal(20)
                if not any(normalize_text(term) in normalize_text(text) for term in scenario.scoring.banned_generic_phrases)
                else Decimal(0)
            )
        )
    clarity = sum(clarity_values) / len(clarity_values) if clarity_values else None
    return {
        "requirement_coverage": requirement,
        "category_distribution": distribution,
        "role_jd_specificity": specificity,
        "question_diversity": diversity,
        "clarity_usability": clarity,
    }


def _model_answer_score(scenario: CoachScenario, output: dict[str, Any]) -> dict[str, Decimal | None]:
    observed = set(output.get("evidence_references", []))
    expected = set(scenario.expected.required_evidence_ids)
    star = output.get("star_breakdown", {})
    completeness = Decimal(25) * sum(bool(str(star.get(item, "")).strip()) for item in ("situation", "task", "action", "result"))
    answer = str(output.get("model_answer", ""))
    relevance = term_group_coverage(answer, scenario.expected.required_term_groups)
    specificity_groups = [group for group in scenario.expected.required_term_groups if not any(re.search(r"\d", term) for term in group)]
    metric_groups = [group for group in scenario.expected.required_term_groups if any(re.search(r"\d", term) for term in group)]
    specificity = term_group_coverage(answer, specificity_groups)
    metrics = term_group_coverage(answer, metric_groups)
    specificity_score = weighted_stage_score({"terms": (specificity, Decimal("0.5")), "metrics": (metrics, Decimal("0.5"))})
    words = len(answer.split())
    minimum = scenario.scoring.min_words or 1
    target = scenario.scoring.target_max_words or max(minimum, words)
    hard = scenario.scoring.hard_max_words or max(target, words)
    concise = Decimal("0.6") * word_budget_score(words, minimum, target, hard) + Decimal("0.4") * readability_score(
        answer, minimum=minimum, maximum=hard, banned_phrases=scenario.scoring.banned_generic_phrases
    )
    return {
        "evidence_grounding": precision_recall_score(observed, expected),
        "star_completeness": completeness,
        "relevance": relevance,
        "specificity": specificity_score,
        "conciseness_readability": concise,
    }


def _evaluation_score(scenario: CoachScenario, output: dict[str, Any]) -> dict[str, Decimal | None]:
    ranges = scenario.expected.score_ranges
    scores = output.get("scores", {})
    dimension_ranges = {key: value for key, value in ranges.items() if key != "overall"}
    in_range = sum(key in scores and value[0] <= scores[key] <= value[1] for key, value in dimension_ranges.items())
    band = pct(in_range, len(dimension_ranges))
    overall_range = ranges.get("overall")
    overall = output.get("overall")
    calibration = None
    if overall_range and isinstance(overall, int | float):
        low, high = overall_range
        distance = Decimal(0) if low <= overall <= high else min(abs(Decimal(str(overall)) - Decimal(str(low))), abs(Decimal(str(overall)) - Decimal(str(high))))
        calibration = max(Decimal(0), Decimal(100) - Decimal(20) * distance)
    transcript = str(scenario.input.get("transcript", ""))
    references = [str(item) for item in output.get("evidence_references", [])]
    grounded = pct(sum(normalize_text(item) in normalize_text(transcript) for item in references), len(references)) if references else None
    feedback = " ".join(
        references
        + [str(item) for item in output.get("strengths", [])]
        + [str(item) for item in output.get("improvements", [])]
    )
    recall = term_group_coverage(feedback, scenario.expected.required_term_groups)
    evidence = weighted_stage_score({"precision": (grounded, Decimal("0.5")), "recall": (recall, Decimal("0.5"))})
    strengths = {normalize_text(item) for item in output.get("strengths", [])}
    gaps = {normalize_text(item) for item in output.get("improvements", [])}
    expected_strengths = {normalize_text(item) for item in scenario.expected.expected_strength_tags}
    expected_gaps = {normalize_text(item) for item in scenario.expected.expected_gap_tags}
    tag_scores = [item for item in (precision_recall_score(strengths, expected_strengths), precision_recall_score(gaps, expected_gaps)) if item is not None]
    tags = sum(tag_scores) / len(tag_scores) if tag_scores else None
    follow_up = output.get("follow_up_question")
    expected_follow = scenario.expected.follow_up_required
    follow = None
    if expected_follow is not None:
        present = isinstance(follow_up, str) and bool(follow_up.strip())
        if present == expected_follow:
            topic = term_group_coverage(str(follow_up or ""), scenario.expected.required_term_groups)
            follow = Decimal(100) if not expected_follow or topic in (None, Decimal(100)) else Decimal(50)
        else:
            follow = Decimal(0)
    return {
        "dimension_band_agreement": band,
        "overall_score_calibration": calibration,
        "grounded_feedback_evidence": evidence,
        "strengths_gaps": tags,
        "follow_up_judgement": follow,
    }


def _simple_stage_score(scenario: CoachScenario, output: dict[str, Any]) -> dict[str, Decimal | None]:
    if scenario.stage == "company_research":
        text = " ".join(str(output.get(key, "")) for key in ("description", "sector", "recent_news", "key_products", "tech_stack_signals"))
        facts = term_group_coverage(text, scenario.scoring.fact_groups)
        source_ids = {str(item.get("source_id")) for item in output.get("sources", []) if isinstance(item, dict)}
        allowed = set(scenario.scoring.allowed_source_ids)
        expected = set(scenario.scoring.expected_source_ids)
        source_score = weighted_stage_score({"facts": (facts, Decimal("0.5")), "precision": (pct(len(source_ids & allowed), len(source_ids)) if source_ids else Decimal(0), Decimal("0.25")), "recall": (pct(len(source_ids & expected), len(expected)) if expected else None, Decimal("0.25"))})
        states = ["not_verified", "partially_verified", "verified"]
        actual_state = output.get("verification_state")
        expected_state = scenario.scoring.expected_verification_state
        uncertainty = None if expected_state is None else Decimal(100 if actual_state == expected_state else 50 if actual_state in states and abs(states.index(actual_state) - states.index(expected_state)) == 1 else 0)
        relevance = term_group_coverage(text, scenario.scoring.role_relevance_term_groups)
        required_fields = [output.get(key) for key in ("company_name", "description", "verification_state")]
        usability = Decimal("0.6") * (pct(sum(bool(item) for item in required_fields), len(required_fields)) or 0) + Decimal("0.4") * word_budget_score(len(text.split()), scenario.scoring.min_words or 1, scenario.scoring.target_max_words or 300, scenario.scoring.hard_max_words or 500)
        return {"source_factual_grounding": source_score, "verification_uncertainty": uncertainty, "role_company_relevance": relevance, "conciseness_schema_usability": usability}
    if scenario.stage == "rubric_synthesis":
        dimensions = output.get("dimensions", {})
        aliases = {
            "content": "relevance",
            "structure": "star_structure",
            "delivery": "communication",
            "specificity": "impact_metrics",
        }
        transcript = normalize_text(str(scenario.input.get("transcript", "")))
        focus = scenario.expected.expected_priority_dimensions
        evidence_items = [
            str(item)
            for value in dimensions.values()
            if isinstance(value, dict)
            for item in value.get("evidence", [])
        ]
        grounded_items = {
            item for item in evidence_items if normalize_text(item) in transcript
        }
        focus_with_grounded_evidence = {
            item
            for item in focus
            if any(
                normalize_text(str(evidence)) in transcript
                for evidence in dimensions.get(aliases.get(item, item), {}).get(
                    "evidence", []
                )
            )
        }
        grounded = weighted_stage_score(
            {
                "precision": (
                    pct(len(grounded_items), len(evidence_items))
                    if evidence_items
                    else Decimal(0),
                    Decimal("0.5"),
                ),
                "recall": (
                    pct(len(focus_with_grounded_evidence), len(focus))
                    if focus
                    else None,
                    Decimal("0.5"),
                ),
            }
        )
        drills = [
            str(dimensions.get(aliases.get(item, item), {}).get("drill", ""))
            for item in focus
        ]
        drill = sum(actionability_score(item, [[name] for name in focus]) for item in drills) / len(drills) if drills else None
        observed_focus = str(output.get("focus_for_next_session", ""))
        positions = [normalize_text(observed_focus).find(normalize_text(item)) for item in focus]
        if focus and all(position >= 0 for position in positions) and positions == sorted(positions):
            alignment = Decimal(100)
        elif focus and (set(item for item, position in zip(focus, positions) if position >= 0) == set(focus) or positions[0] >= 0):
            alignment = Decimal(50)
        else:
            alignment = Decimal(0)
        return {"evidence_grounding": grounded, "drill_specificity": drill, "focus_alignment": alignment}
    if scenario.stage == "session_report":
        strengths = {normalize_text(item) for item in output.get("strengths", [])}
        gaps = {normalize_text(item) for item in output.get("improvement_areas", [])}
        expected_strengths = {normalize_text(item) for item in scenario.expected.expected_strength_tags}
        expected_gaps = {normalize_text(item) for item in scenario.expected.expected_gap_tags}
        priority = [normalize_text(item) for item in output.get("improvement_areas", [])]
        expected_priority = [normalize_text(item) for item in scenario.expected.expected_priority_dimensions]
        priority_score = Decimal(100) if priority[: len(expected_priority)] == expected_priority else Decimal(50) if set(priority) >= set(expected_priority) else Decimal(0)
        parts = [item for item in (precision_recall_score(strengths, expected_strengths), precision_recall_score(gaps, expected_gaps), priority_score) if item is not None]
        prioritisation = sum(parts) / len(parts) if parts else None
        actions = [str(item) for item in output.get("coaching_points", [])] + [str(item.get("activity", "")) for item in output.get("practice_plan", []) if isinstance(item, dict)]
        actionability = sum(actionability_score(item, [[name] for name in expected_priority]) for item in actions) / len(actions) if actions else Decimal(0)
        specificity = term_group_coverage(" ".join(str(value) for value in output.values()), scenario.expected.required_term_groups)
        readable_items = [str(output.get("executive_summary", ""))] + [str(item) for key in ("strengths", "improvement_areas", "coaching_points") for item in output.get(key, [])]
        readability = sum(readability_score(item, banned_phrases=scenario.scoring.banned_generic_phrases) for item in readable_items) / len(readable_items) if readable_items else None
        return {"strength_gap_prioritisation": prioritisation, "actionability": actionability, "session_specificity": specificity, "conciseness_readability": readability}
    if scenario.stage == "technical_drill":
        drills = output.get("drills", [])
        drill = drills[0] if drills else {}
        walkthrough = str(drill.get("walkthrough", ""))
        prompt = str(drill.get("drill_prompt", ""))
        return {"question_alignment": term_group_coverage(walkthrough, scenario.expected.required_term_groups), "worked_example_usefulness": term_group_coverage(walkthrough, scenario.scoring.role_relevance_term_groups), "tradeoff_coverage": term_group_coverage(walkthrough, scenario.scoring.expected_tradeoff_term_groups), "drill_instruction_clarity": (actionability_score(prompt, scenario.expected.required_term_groups) + readability_score(prompt)) / Decimal(2)}
    return {}


_WEIGHTS: dict[str, dict[str, Decimal]] = {
    "company_research": {"source_factual_grounding": Decimal(".40"), "verification_uncertainty": Decimal(".25"), "role_company_relevance": Decimal(".20"), "conciseness_schema_usability": Decimal(".15")},
    "question_generation": {"requirement_coverage": Decimal(".30"), "category_distribution": Decimal(".20"), "role_jd_specificity": Decimal(".20"), "question_diversity": Decimal(".15"), "clarity_usability": Decimal(".15")},
    "model_answer": {"evidence_grounding": Decimal(".30"), "star_completeness": Decimal(".25"), "relevance": Decimal(".20"), "specificity": Decimal(".15"), "conciseness_readability": Decimal(".10")},
    "answer_evaluation": {"dimension_band_agreement": Decimal(".35"), "overall_score_calibration": Decimal(".20"), "grounded_feedback_evidence": Decimal(".20"), "strengths_gaps": Decimal(".15"), "follow_up_judgement": Decimal(".10")},
    "rubric_synthesis": {"evidence_grounding": Decimal(".50"), "drill_specificity": Decimal(".30"), "focus_alignment": Decimal(".20")},
    "session_report": {"strength_gap_prioritisation": Decimal(".35"), "actionability": Decimal(".30"), "session_specificity": Decimal(".20"), "conciseness_readability": Decimal(".15")},
    "technical_drill": {"question_alignment": Decimal(".35"), "worked_example_usefulness": Decimal(".30"), "tradeoff_coverage": Decimal(".20"), "drill_instruction_clarity": Decimal(".15")},
}


def score_execution(
    scenario: CoachScenario,
    execution: StageExecution,
    validation: ValidationResult,
) -> ScenarioScore:
    if not validation.eligible:
        return ScenarioScore({}, None)
    if scenario.stage == "model_answer" and scenario.expected.outcome == "withheld_insufficient_evidence":
        return ScenarioScore(
            {name: None for name in _WEIGHTS["model_answer"]}, "100.0"
        )
    if scenario.stage == "question_generation":
        values = _question_score(scenario, execution.output)
    elif scenario.stage == "model_answer":
        values = _model_answer_score(scenario, execution.output)
    elif scenario.stage == "answer_evaluation":
        values = _evaluation_score(scenario, execution.output)
    else:
        values = _simple_stage_score(scenario, execution.output)
    weights = _WEIGHTS.get(scenario.stage, {})
    quality = weighted_stage_score(
        {name: (value, weights[name]) for name, value in values.items() if name in weights}
    )
    return ScenarioScore(
        dimensions={name: _display(value) for name, value in values.items()},
        quality_score=_display(quality),
    )
