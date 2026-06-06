"""Tests for resume_store service."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch



# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_profile(
    title: str = "AI Project Manager",
    summary: str = "Experienced delivery leader with 20 years in technology programmes.",
    skills_primary: list[str] | None = None,
    skills_secondary: list[str] | None = None,
    certifications: list[str] | None = None,
    target_roles: list[str] | None = None,
    proof_points: list | None = None,
) -> MagicMock:
    p = MagicMock()
    p.candidate.title = title
    p.candidate.summary = summary
    p.skills.primary = skills_primary or ["agile delivery", "project management", "stakeholder management"]
    p.skills.secondary = skills_secondary or ["python", "cloud"]
    p.skills.certifications = certifications or ["PMP", "PSM-1"]
    p.search.target_roles = target_roles or ["AI Project Manager", "IT Project Manager"]
    pp = MagicMock()
    pp.summary = "Delivered £5M digital transformation at Northern Powergrid."
    p.proof_points = proof_points or [pp]
    return p


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestResumeStore:

    def test_save_and_load_resume_text(self, tmp_path):
        """save_resume_text writes text to disk; get_resume_text reads it back."""
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_path)}):
            # Re-import to pick up env var
            import importlib
            import app.services.resume_store as rs_module
            importlib.reload(rs_module)

            sample_text = "Jane Doe\nSenior PM with 15 years experience in Agile delivery."
            rs_module.save_resume_text(sample_text)
            loaded = rs_module.get_resume_text()

        assert loaded == sample_text

    def test_resume_text_falls_back_to_profile_when_absent(self, tmp_path):
        """get_resume_text returns synthesised text from profile when file missing."""
        profile = _make_profile()

        with patch.dict(os.environ, {"DATA_DIR": str(tmp_path)}):
            import importlib
            import app.services.resume_store as rs_module
            importlib.reload(rs_module)

            with patch("app.services.resume_store.load_profile", return_value=profile):
                text = rs_module.get_resume_text()

        assert text is not None
        assert len(text) > 20
        # Should contain key profile fields
        assert "AI Project Manager" in text or "project management" in text.lower()

    def test_synthesise_from_profile_includes_key_fields(self, tmp_path):
        """synthesise_from_profile concatenates title, summary, skills, certs, target_roles."""
        profile = _make_profile(
            title="Technical Delivery Lead",
            summary="20 years delivering enterprise transformation.",
            skills_primary=["agile", "cloud"],
            certifications=["PMP"],
            target_roles=["Delivery Lead", "Programme Manager"],
        )

        with patch.dict(os.environ, {"DATA_DIR": str(tmp_path)}):
            import importlib
            import app.services.resume_store as rs_module
            importlib.reload(rs_module)

            with patch("app.services.resume_store.load_profile", return_value=profile):
                text = rs_module.synthesise_from_profile()

        assert "Technical Delivery Lead" in text
        assert "agile" in text.lower() or "PMP" in text
        assert "Delivery Lead" in text or "Programme Manager" in text

    def test_resume_embedding_is_cached(self, tmp_path):
        """get_resume_embedding calls embedder.embed() once; second call returns cached value."""
        sample_text = "Senior PM with Agile and PMP certification."
        fake_embedding = [0.1] * 384

        with patch.dict(os.environ, {"DATA_DIR": str(tmp_path)}):
            import importlib
            import app.services.resume_store as rs_module
            importlib.reload(rs_module)

            # Clear any cached embedding state
            rs_module._embedding_cache.clear()

            rs_module.save_resume_text(sample_text)

            call_count = 0

            def fake_embed(text: str) -> list[float]:
                nonlocal call_count
                call_count += 1
                return fake_embedding

            with patch("app.services.resume_store.embed", side_effect=fake_embed):
                emb1 = rs_module.get_resume_embedding()
                emb2 = rs_module.get_resume_embedding()

        # embedder called only once despite two get_resume_embedding() calls
        assert call_count == 1
        assert emb1 == fake_embedding
        assert emb2 == fake_embedding

    def test_get_resume_embedding_returns_list_of_floats(self, tmp_path):
        """get_resume_embedding returns a non-empty list of floats."""
        sample_text = "Experienced project manager."
        fake_emb = [0.5] * 384

        with patch.dict(os.environ, {"DATA_DIR": str(tmp_path)}):
            import importlib
            import app.services.resume_store as rs_module
            importlib.reload(rs_module)
            rs_module._embedding_cache.clear()
            rs_module.save_resume_text(sample_text)

            with patch("app.services.resume_store.embed", return_value=fake_emb):
                result = rs_module.get_resume_embedding()

        assert isinstance(result, list)
        assert len(result) == 384
        assert all(isinstance(x, float) for x in result)
