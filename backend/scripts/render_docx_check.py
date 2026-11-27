"""In-image check: the Node-backed DOCX renderers work for CV and cover letter."""
from __future__ import annotations

import os
import tempfile
import zipfile

from app.schemas.tailor import CoverLetterResult, JDAnalysisResult, TailoredCVResult
from app.services.docx_cl_builder import DocxCLBuilder
from app.services.docx_cv_builder import DocxCVBuilder


def main() -> None:
    os.chdir(tempfile.mkdtemp())
    jd = JDAnalysisResult.model_validate(
        {"role_title": "Delivery Lead", "company_context": {"company_name": "Synthetic Co"}}
    )
    cv = TailoredCVResult.model_validate(
        {
            "summary": "Synthetic delivery summary.",
            "skills": [{"category": "Delivery", "items": ["Planning"]}],
            "experience": [
                {
                    "role": "Delivery Lead",
                    "company": "Synthetic Co",
                    "period": "2020-2024",
                    "achievements": ["Delivered a synthetic programme."],
                }
            ],
        }
    )
    personal = {
        "name": "Synthetic Candidate",
        "email": "candidate@example.test",
        "phone": "000000000",
        "location": "London",
    }
    cover_letter = CoverLetterResult.model_validate(
        {
            "subject_line": "Application for Delivery Lead",
            "greeting": "Dear team,",
            "body_paragraphs": ["Synthetic cover letter paragraph."],
            "sign_off": "Regards",
            "word_count": 4,
        }
    )

    cv_path, _ = DocxCVBuilder().build(cv, jd, personal, "synthetic-app", 1)
    cl_path, _ = DocxCLBuilder().build(cover_letter, jd, personal, "synthetic-app", 1)
    for path in (cv_path, cl_path):
        with zipfile.ZipFile(path) as archive:
            assert "word/document.xml" in archive.namelist(), path
    print("render-ok")


if __name__ == "__main__":
    main()
