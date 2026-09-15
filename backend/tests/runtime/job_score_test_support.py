"""Synthetic product inputs; database and scoring implementations remain real."""

import uuid

from app.models.job import JobPosting
from app.schemas.profile import Profile


def profile(method="local"):
    return Profile.model_validate(
        {
            "candidate": {"title": "Senior Cloud Architect", "years_experience": 15},
            "skills": {"primary": ["AWS", "Python"], "secondary": ["Terraform"]},
            "search": {
                "target_roles": ["Cloud Architect"],
                "locations": [
                    {"city": "London", "country": "UK", "remote_preference": "remote"}
                ],
            },
            "compensation": {"min_rate": 500, "max_rate": 750, "currency": "GBP"},
            "scoring": {"method": method},
            "llm": {
                "provider": "anthropic",
                "primary_model": "claude-sonnet-4-6",
                "triage_model": "claude-haiku-4-5-20251001",
            },
        }
    )


def job(**values):
    job_id = values.pop("id", str(uuid.uuid4()))
    defaults = dict(
        id=job_id,
        title="Senior Cloud Architect",
        company="Synthetic Lab",
        description="AWS Python Terraform. Lead remote infrastructure design. SYNTHETIC_PRIVATE_CANARY",
        location="London remote",
        rate_text="£650/day",
        rate_min=650,
        rate_max=650,
        currency="GBP",
        url=f"https://example.test/jobs/{job_id}",
        source="synthetic",
    )
    defaults.update(values)
    return JobPosting(**defaults)


def install_profile(monkeypatch, candidate):
    for name in (
        "app.agents.scorer_agent.load_profile",
        "app.agents.tools.profile_loader.load_profile",
        "app.agents.tools.llm_factory.load_profile",
    ):
        monkeypatch.setattr(name, lambda: candidate)
    monkeypatch.setattr(
        "app.services.resume_store.get_resume_text",
        lambda: "Synthetic AWS Python Terraform candidate",
    )


def install_provider(monkeypatch, outcomes, *, on_primary=None):
    """Replace only provider transport; routing, schemas and scoring stay real."""
    remaining = iter(outcomes)

    class Model:
        def with_structured_output(self, schema, **kwargs):
            class Endpoint:
                async def ainvoke(self, prompt):
                    if "relevant" in schema.model_fields:
                        return schema(relevant=True, reason="synthetic_relevant")
                    value = next(remaining)
                    if on_primary is not None:
                        await on_primary()
                    if isinstance(value, Exception):
                        raise value
                    if isinstance(value, dict):
                        return schema.model_validate(value)
                    return schema(
                        skill_match=value,
                        experience_match=value,
                        rate_match=value,
                        location_match=value,
                        overall_score=123,
                        reasoning="SYNTHETIC_PRIVATE_CANARY",
                        keyword_matches=["AWS", "fabricated-skill"],
                        keyword_misses=[],
                    )

            return Endpoint()

    monkeypatch.setattr(
        "app.agents.tools.llm_factory._build_model", lambda *args, **kwargs: Model()
    )

    class Limiter:
        async def acquire(self):
            pass

        def record_429(self):
            pass

    for name in (
        "app.agents.scorer_agent.get_limiter",
        "app.agents.tools.rate_limiter.get_limiter",
    ):
        monkeypatch.setattr(name, Limiter)
