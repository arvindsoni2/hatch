"""Video Analyser — backend validation of browser-side TF.js face metrics."""
from __future__ import annotations

import logging

from ..schemas.coach import VideoMetrics

logger = logging.getLogger(__name__)


class VideoAnalyserService:
    """Validates and clamps video metrics computed browser-side by TensorFlow.js face-mesh.

    TF.js analysis runs in the browser for latency and privacy.
    This service validates the submitted metrics are within expected ranges.
    """

    def validate_metrics(self, raw_metrics: dict) -> VideoMetrics:
        """Validate and clamp browser-submitted video metrics.

        Args:
            raw_metrics: Raw dict from browser-side TF.js analysis.

        Returns:
            Validated VideoMetrics with values clamped to valid ranges.
        """
        eye_contact = float(raw_metrics.get("eye_contact_pct", 0.0))
        head_stability = float(raw_metrics.get("head_stability", 0.5))
        expression = str(raw_metrics.get("expression", "neutral"))
        gesture_freq = float(raw_metrics.get("gesture_freq", 0.0))

        # Clamp to valid ranges
        eye_contact = max(0.0, min(100.0, eye_contact))
        head_stability = max(0.0, min(1.0, head_stability))
        gesture_freq = max(0.0, gesture_freq)

        valid_expressions = {"neutral", "happy", "focused", "confused", "tense", "confident"}
        if expression not in valid_expressions:
            logger.debug("Unknown expression '%s', defaulting to 'neutral'", expression)
            expression = "neutral"

        return VideoMetrics(
            eye_contact_pct=round(eye_contact, 1),
            head_stability=round(head_stability, 3),
            expression=expression,
            gesture_freq=round(gesture_freq, 1),
        )
