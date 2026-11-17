"""Product-owned registrations for job scoring and document rendering."""

from app.runtime.execution import (
    CapabilityDescriptor,
    CapabilityRegistry,
    IdempotencyClass,
    SideEffectClass,
)
from app.runtime.execution.adapters import (
    ArtifactCapabilityAdapter,
    CapabilityHandler,
    NativeCapabilityAdapter,
)

from .models import (
    ArtifactRenderInput,
    ArtifactRenderOutput,
    JobLocalScoreInput,
    JobLocalScoreOutput,
)


def register_product_capabilities(
    registry: CapabilityRegistry,
    *,
    local_score_handler: CapabilityHandler,
    render_cv_handler: CapabilityHandler,
    render_cover_letter_handler: CapabilityHandler,
) -> None:
    """Register exactly the three Task 8 product capabilities."""
    registry.register(
        CapabilityDescriptor(
            capability_id="job.local_score",
            version=1,
            input_model=JobLocalScoreInput,
            output_model=JobLocalScoreOutput,
            side_effect_class=SideEffectClass.PURE,
            idempotency_class=IdempotencyClass.IDEMPOTENT,
            required_permissions=(),
            default_timeout_seconds=10.0,
        ),
        NativeCapabilityAdapter(local_score_handler),
    )
    for capability_id, handler in (
        ("artifact.render_cv", render_cv_handler),
        ("artifact.render_cover_letter", render_cover_letter_handler),
    ):
        registry.register(
            CapabilityDescriptor(
                capability_id=capability_id,
                version=1,
                input_model=ArtifactRenderInput,
                output_model=ArtifactRenderOutput,
                side_effect_class=SideEffectClass.ARTIFACT_GENERATION,
                idempotency_class=IdempotencyClass.IDEMPOTENT_WITH_KEY,
                required_permissions=(),
                default_timeout_seconds=60.0,
            ),
            ArtifactCapabilityAdapter(handler),
        )


def register_readiness_capabilities(
    registry: CapabilityRegistry,
    *,
    handlers: dict[str, CapabilityHandler],
) -> None:
    """Register the five local-capable readiness tasks (spec §10)."""
    from app.runtime_bindings.tasks.coach_readiness import (
        COACH_READINESS_BRIEF_ENHANCE_V1,
        COACH_READINESS_COMPETENCY_EXTRACT_V1,
        COACH_READINESS_DEBRIEF_EXTRACT_V1,
        COACH_READINESS_EXPLAIN_V1,
        COACH_READINESS_PLAN_WORDING_V1,
    )

    for task in (
        COACH_READINESS_EXPLAIN_V1,
        COACH_READINESS_BRIEF_ENHANCE_V1,
        COACH_READINESS_PLAN_WORDING_V1,
        COACH_READINESS_DEBRIEF_EXTRACT_V1,
        COACH_READINESS_COMPETENCY_EXTRACT_V1,
    ):
        registry.register(
            CapabilityDescriptor(
                capability_id=task.task_id,
                version=task.version,
                input_model=task.input_model,
                output_model=task.output_model,
                side_effect_class=SideEffectClass.PURE,
                idempotency_class=IdempotencyClass.IDEMPOTENT,
                required_permissions=(),
                default_timeout_seconds=30.0,
                uses_model_routing=True,
            ),
            NativeCapabilityAdapter(handlers[task.task_id]),
        )
