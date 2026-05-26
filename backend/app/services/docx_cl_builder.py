"""DOCX Cover Letter Builder — calls generate_cl_docx.js to produce .docx files."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..schemas.tailor import CoverLetterResult, JDAnalysisResult

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_CL_SCRIPT = _TEMPLATES_DIR / "generate_cl_docx.js"
_OUTPUT_BASE = Path("data/generated")


class DocxCLBuilder:
    """Builds ATS-safe cover letter .docx files via Node.js docx library."""

    def build(
        self,
        cover_letter: CoverLetterResult,
        jd_analysis: JDAnalysisResult,
        personal: dict[str, Any],
        application_id: str,
        version: int,
        variant_label: str = "A",
    ) -> tuple[str, int]:
        """Generate a cover letter .docx and return (file_path, file_size_bytes).

        Args:
            cover_letter: CoverLetterResult from CoverLetterGenerator.
            jd_analysis: JD analysis for role context.
            personal: Personal details dict (name, email, phone, etc.).
            application_id: UUID of the application.
            version: Document version number.
            variant_label: "A" or "B" label.

        Returns:
            Tuple of (absolute file path, file size in bytes).

        Raises:
            RuntimeError: If the Node.js script fails.
        """
        out_dir = _OUTPUT_BASE / application_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = (out_dir / f"cl_v{version}_{variant_label}.docx").resolve()
        expected_parent = _OUTPUT_BASE.resolve()
        if not str(out_path).startswith(str(expected_parent)):
            raise ValueError(f"Output path traversal detected: {out_path}")

        spec = _build_cl_spec(cover_letter, jd_analysis, personal)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            json.dump(spec, tf, indent=2)
            spec_path = tf.name

        try:
            result = subprocess.run(
                ["node", str(_CL_SCRIPT), spec_path, str(out_path)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(_TEMPLATES_DIR),
            )
            if result.returncode != 0:
                logger.error("CL docx generation failed: %s", result.stderr)
                raise RuntimeError(f"generate_cl_docx.js failed: {result.stderr[:500]}")

            file_size = out_path.stat().st_size
            logger.info("CL docx generated: %s (%d bytes)", out_path, file_size)
            return str(out_path), file_size

        finally:
            os.unlink(spec_path)


def _build_cl_spec(
    cover_letter: CoverLetterResult,
    jd_analysis: JDAnalysisResult,
    personal: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the JSON spec that generate_cl_docx.js consumes."""
    return {
        "personal": personal,
        "subject_line": cover_letter.subject_line,
        "greeting": cover_letter.greeting,
        "body_paragraphs": cover_letter.body_paragraphs,
        "sign_off": cover_letter.sign_off,
        "role_applied_for": jd_analysis.role_title,
        "company_name": jd_analysis.company_context.company_name or "the Company",
        "word_count": cover_letter.word_count,
    }
