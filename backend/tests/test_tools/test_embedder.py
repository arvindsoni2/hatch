"""Tests for the local sentence-transformer embedder."""
from __future__ import annotations

import pytest


class TestEmbedder:

    def test_embed_returns_fixed_dimension_vector(self):
        """embed() returns a list of 384 floats (all-MiniLM-L6-v2 output dim)."""
        from app.agents.tools.embedder import embed

        result = embed("Senior Project Manager with 20 years experience")
        assert isinstance(result, list)
        assert len(result) == 384
        assert all(isinstance(x, float) for x in result)

    def test_cosine_identical_text_near_one(self):
        """cosine(embed(x), embed(x)) should be > 0.99."""
        from app.agents.tools.embedder import embed, cosine

        text = "IT Project Manager with PMP certification and 15 years experience"
        emb1 = embed(text)
        emb2 = embed(text)
        similarity = cosine(emb1, emb2)
        assert similarity > 0.99, f"Identical text cosine should be > 0.99, got {similarity}"

    def test_cosine_related_roles_high(self):
        """THE CORE REGRESSION TEST: AI PM and IT PM are semantically equivalent.

        This is the original bug: AI Project Manager / Technical Delivery Lead
        scored 0% against IT Project Manager.  Semantic similarity must be > 0.5.
        """
        from app.agents.tools.embedder import embed, cosine

        candidate = "AI Project Manager and Technical Delivery Lead"
        job_role = "Information Technology Project Manager"

        emb_candidate = embed(candidate)
        emb_job = embed(job_role)
        similarity = cosine(emb_candidate, emb_job)

        assert similarity > 0.5, (
            f"'AI Project Manager / Technical Delivery Lead' vs "
            f"'Information Technology Project Manager' cosine should be > 0.5, got {similarity:.4f}. "
            f"This is the core regression — keyword scoring gave 0%, semantic should recognise equivalence."
        )

    def test_cosine_unrelated_low(self):
        """cosine(embed('project manager'), embed('pastry chef')) should be < 0.3."""
        from app.agents.tools.embedder import embed, cosine

        emb_pm = embed("project manager")
        emb_chef = embed("pastry chef")
        similarity = cosine(emb_pm, emb_chef)
        assert similarity < 0.3, (
            f"'project manager' vs 'pastry chef' cosine should be < 0.3, got {similarity:.4f}"
        )

    def test_model_loads_once(self):
        """SentenceTransformer constructor called at most once (singleton pattern)."""
        import importlib
        from unittest.mock import patch, MagicMock

        # Reset the singleton so we can observe the constructor call
        import app.agents.tools.embedder as emb_module
        original_model = emb_module._model
        emb_module._model = None  # reset singleton

        constructor_call_count = 0
        real_class = None

        try:
            from sentence_transformers import SentenceTransformer as _Real
            real_class = _Real

            class TrackingTransformer(_Real):
                def __init__(self, *args, **kwargs):
                    nonlocal constructor_call_count
                    constructor_call_count += 1
                    super().__init__(*args, **kwargs)

            with patch("app.agents.tools.embedder.SentenceTransformer", TrackingTransformer):
                # Reset again under the patch
                emb_module._model = None
                from app.agents.tools.embedder import embed
                embed("test one")
                embed("test two")
                embed("test three")

        finally:
            # Restore original model state
            emb_module._model = original_model

        assert constructor_call_count <= 1, (
            f"SentenceTransformer should be constructed at most once (singleton), "
            f"but was constructed {constructor_call_count} times."
        )

    def test_embed_batch_returns_multiple_embeddings(self):
        """embed_batch returns one embedding per input text."""
        from app.agents.tools.embedder import embed_batch

        texts = [
            "Project Manager",
            "Data Scientist",
            "Software Engineer",
        ]
        results = embed_batch(texts)
        assert len(results) == 3
        for emb in results:
            assert len(emb) == 384

    def test_cosine_symmetry(self):
        """cosine(a, b) == cosine(b, a) within floating-point tolerance."""
        from app.agents.tools.embedder import embed, cosine

        emb_a = embed("Senior Delivery Manager")
        emb_b = embed("Programme Director")
        assert abs(cosine(emb_a, emb_b) - cosine(emb_b, emb_a)) < 1e-6
