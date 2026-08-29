"""Provider-generic structured generation capability registration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..models import CapabilityDescriptor, IdempotencyClass, SideEffectClass
from ..registry import CapabilityRegistry
from .native import CapabilityHandler, NativeCapabilityAdapter


class StructuredGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_ref: str
    schema_ref: str
    model_id: str | None = None


class StructuredGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_ref: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMCapabilityAdapter(NativeCapabilityAdapter):
    """Names the provider boundary without coupling runtime to one SDK."""

    def __init__(self, handler: CapabilityHandler) -> None:
        super().__init__(handler)


def register_llm_generate_structured(
    registry: CapabilityRegistry,
    *,
    handler: CapabilityHandler,
) -> None:
    registry.register(
        CapabilityDescriptor(
            capability_id="llm.generate_structured",
            version=1,
            input_model=StructuredGenerationInput,
            output_model=StructuredGenerationOutput,
            side_effect_class=SideEffectClass.READ_ONLY_EXTERNAL,
            idempotency_class=IdempotencyClass.IDEMPOTENT,
            required_permissions=(),
            default_timeout_seconds=60.0,
        ),
        LLMCapabilityAdapter(handler),
    )
