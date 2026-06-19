"""DOCX CV Builder — calls the Node.js generate_cv_docx.js script to produce .docx files."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..schemas.tailor import JDAnalysisResult, TailoredCVResult

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_CV_SCRIPT = _TEMPLATES_DIR / "generate_cv_docx.js"
_OUTPUT_BASE = Path("data/generated")


class DocxCVBuilder:
    """Builds ATS-safe CV .docx files via Node.js docx library."""

    def build(
        self,
        tailored_cv: TailoredCVResult,
        jd_analysis: JDAnalysisResult,
        personal: dict[str, Any],
        application_id: str,
        version: int,
        variant_label: str = "A",
    ) -> tuple[str, int]:
        """Generate a CV .docx and return (file_path, file_size_bytes).

        Args:
            tailored_cv: Tailored CV result from CVTailor.
            jd_analysis: JD analysis for context / keywords.
            personal: Personal details dict (name, email, phone, etc.).
            application_id: UUID of the application (used for output dir).
            version: Document version number.
            variant_label: "A" or "B" label.

        Returns:
            Tuple of (absolute file path, file size in bytes).

        Raises:
            RuntimeError: If the Node.js script fails.
        """
        out_dir = _OUTPUT_BASE / application_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = (out_dir / f"cv_v{version}_{variant_label}.docx").resolve()
        expected_parent = _OUTPUT_BASE.resolve()
        if not str(out_path).startswith(str(expected_parent)):
            raise ValueError(f"Output path traversal detected: {out_path}")

        spec = _build_cv_spec(tailored_cv, jd_analysis, personal)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            json.dump(spec, tf, indent=2)
            spec_path = tf.name

        try:
            result = subprocess.run(
                ["node", str(_CV_SCRIPT), spec_path, str(out_path)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(_TEMPLATES_DIR),
            )
            if result.returncode != 0:
                logger.error("CV docx generation failed: %s", result.stderr)
                raise RuntimeError(f"generate_cv_docx.js failed: {result.stderr[:500]}")

            file_size = out_path.stat().st_size
            logger.info("CV docx generated: %s (%d bytes)", out_path, file_size)
            return str(out_path), file_size

        finally:
            os.unlink(spec_path)


def _build_cv_spec(
    tailored_cv: TailoredCVResult,
    jd_analysis: JDAnalysisResult,
    personal: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the JSON spec that generate_cv_docx.js consumes."""
    return {
        "personal": personal,
        "summary": tailored_cv.summary,
        "skills": [
            {
                "display_name": (
                    s.get("category") or s.get("display_name") or s.get("name") or ""
                ),
                "items": s.get("items", []),
            }
            for s in tailored_cv.skills
        ],
        "experience": [
            {
                "role": exp.role,
                "company": exp.company,
                "period": exp.period,
                "achievements": exp.achievements,
            }
            for exp in tailored_cv.experience
        ],
        "education": [
            {
                "qualification": edu.qualification,
                "institution": edu.institution,
                "year": edu.year,
                "field": edu.field,
                "location": edu.location,
                "details": edu.details,
            }
            for edu in tailored_cv.education
        ],
        "certifications": tailored_cv.certifications,
        "role_applied_for": jd_analysis.role_title,
        "ats_keywords": tailored_cv.ats_keywords_embedded,
        "validation_status": tailored_cv.validation_status,
        "structural_warnings": tailored_cv.structural_warnings,
    }
