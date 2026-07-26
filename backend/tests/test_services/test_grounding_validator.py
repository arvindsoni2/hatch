"""G-5 tests — entity-level grounding validator catches fabricated content."""
from __future__ import annotations


from app.schemas.tailor import TailoredCVResult, TailoredExperience
from app.services.grounding_validator import validate


REAL_MASTER_CV = {
    "personal": {"full_name": "Jane Smith"},
    "summary_variants": {"default": "Experienced delivery lead with 15 years in energy sector."},
    "experience": [
        {
            "role": "Programme Manager",
            "company": "Utility Corp",
            "period": "2018 – Present",
            "achievements": [
                {"text": "Delivered £500K cost savings via mobile platform serving 2,000 engineers."},
                {"text": "Led SAFe transformation across 3 business units, 80 engineers."},
            ],
        },
        {
            "role": "Project Manager",
            "company": "DataFlow Ltd",
            "period": "2015 – 2018",
            "achievements": [
                {"text": "Managed £1.2M AWS migration with 99.5% uptime."},
            ],
        },
    ],
    "skills": {
        "delivery": {"items": ["Agile", "SAFe", "PRINCE2", "Stakeholder Management"]},
    },
    "certifications": ["PMP", "PSM-1", "PRINCE2 Practitioner"],
    "education": [
        {
            "qualification": "MBA",
            "institution": "Example Business School",
            "year": "2010",
        }
    ],
}


def _build_tailored(**kwargs) -> TailoredCVResult:
    defaults = dict(
        summary="Experienced delivery professional.",
        skills=[{"category": "Delivery", "items": ["Agile", "SAFe"]}],
        experience=[
            TailoredExperience(
                role="Programme Manager",
                company="Utility Corp",
                period="2018 – Present",
                achievements=["Delivered £500K cost savings via mobile platform serving 2,000 engineers."],
            )
        ],
        certifications=["PMP"],
        education=[
            {
                "qualification": "MBA",
                "institution": "Example Business School",
                "year": "2010",
            }
        ],
        ats_keywords_embedded=[],
        tailoring_notes="notes",
        blocking_issues=[],
        fabrication_warnings=[],
    )
    defaults.update(kwargs)
    return TailoredCVResult(**defaults)


class TestGroundingValidator:
    def test_clean_result_has_no_blocking_issues(self):
        """A properly grounded tailored CV produces zero blocking issues."""
        tailored = _build_tailored()
        blocking, advisory = validate(tailored, REAL_MASTER_CV)
        assert blocking == [], f"Unexpected blocking: {blocking}"

    def test_placeholder_company_is_blocking(self):
        """PLACEHOLDER — Company A in company name is a blocking issue."""
        tailored = _build_tailored(
            experience=[
                TailoredExperience(
                    role="Programme Manager",
                    company="PLACEHOLDER — Company A (Energy Sector)",
                    period="2018 – Present",
                    achievements=["Delivered cost savings via platform."],
                )
            ]
        )
        blocking, _ = validate(tailored, REAL_MASTER_CV)
        assert any("placeholder" in b.lower() for b in blocking), blocking

    def test_invented_company_is_blocking(self):
        """Company name not in master CV is a blocking issue."""
        tailored = _build_tailored(
            experience=[
                TailoredExperience(
                    role="Programme Manager",
                    company="Company B (Aviation Sector)",
                    period="2018 – Present",
                    achievements=["Led delivery programme."],
                )
            ]
        )
        blocking, _ = validate(tailored, REAL_MASTER_CV)
        assert any("company" in b.lower() for b in blocking), blocking

    def test_fabricated_number_in_achievement_is_blocking(self):
        """A numeric token in an achievement not in the master CV is blocking."""
        tailored = _build_tailored(
            experience=[
                TailoredExperience(
                    role="Programme Manager",
                    company="Utility Corp",
                    period="2018 – Present",
                    achievements=["Delivered £3M programme saving 40% costs."],  # £3M and 40% not in master
                )
            ]
        )
        blocking, _ = validate(tailored, REAL_MASTER_CV)
        assert any("numeric" in b.lower() or "fabricated" in b.lower() for b in blocking), blocking

    def test_real_metric_from_master_passes(self):
        """A metric that exists verbatim in the master CV is not flagged."""
        tailored = _build_tailored(
            experience=[
                TailoredExperience(
                    role="Programme Manager",
                    company="Utility Corp",
                    period="2018 – Present",
                    achievements=["Delivered £500K cost savings via mobile platform."],
                )
            ]
        )
        blocking, _ = validate(tailored, REAL_MASTER_CV)
        metric_blocks = [b for b in blocking if "£500K" in b]
        assert metric_blocks == [], f"Real metric incorrectly flagged: {metric_blocks}"

    def test_invented_education_is_blocking(self):
        """Education values not in master CV are blocking."""
        tailored = _build_tailored(
            education=[
                {
                    "qualification": "PhD Artificial Intelligence",
                    "institution": "Invented University",
                    "year": "2024",
                }
            ]
        )
        blocking, _ = validate(tailored, REAL_MASTER_CV)
        assert any("education" in b.lower() for b in blocking), blocking

    def test_sc_cleared_claim_without_master_evidence_is_blocking(self):
        """SC Cleared claim not in master CV is blocking."""
        tailored = _build_tailored(
            summary="SC Cleared Technical Architect with 15 years experience.",
        )
        blocking, _ = validate(tailored, REAL_MASTER_CV)
        assert any("clearance" in b.lower() for b in blocking), blocking

    def test_invented_certification_is_blocking(self):
        """A certification not in master CV certifications is blocking."""
        tailored = _build_tailored(
            certifications=["PMP", "ITIL v4 Expert"],  # ITIL not in master
        )
        blocking, _ = validate(tailored, REAL_MASTER_CV)
        assert any("ITIL" in b for b in blocking), blocking

    def test_real_certification_passes(self):
        """A certification present in the master CV is not flagged."""
        tailored = _build_tailored(certifications=["PMP"])
        blocking, _ = validate(tailored, REAL_MASTER_CV)
        cert_blocks = [b for b in blocking if "PMP" in b]
        assert cert_blocks == [], f"Real cert incorrectly flagged: {cert_blocks}"

    def test_the_real_failure_scenario(self):
        """Regression: the exact failure case from the spec produces 3+ blocking issues."""
        bad_tailored = TailoredCVResult(
            summary="SC Cleared Technical Architect with 20+ years leading £3M programmes.",
            skills=[{"category": "Architecture & Design", "items": ["SC Cleared", "AWS"]}],
            experience=[
                TailoredExperience(
                    role="SC Cleared Technical Architect",
                    company="Company B (Aviation Sector)",
                    period="2019 – 2022",
                    achievements=["Delivered £3M programme with 99.9% uptime."],
                )
            ],
            certifications=["PMP"],
            ats_keywords_embedded=[],
            tailoring_notes="",
            blocking_issues=[],
            fabrication_warnings=[],
        )
        blocking, _ = validate(bad_tailored, REAL_MASTER_CV)
        assert len(blocking) >= 3, f"Expected ≥3 blocking issues, got {len(blocking)}: {blocking}"
