"""Typed contracts for the non-secret setup control plane."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

AiMode = Literal["not_configured", "none", "local", "cloud", "custom"]
BackendProfile = Literal["core", "browser", "local-embeddings", "full"]


class SetupIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: Literal[2] = 2
    ai_mode: AiMode = "not_configured"
    backend_profile: BackendProfile = "core"
    experience: Literal["essential", "full_ai", "custom"] = "essential"
    local_primary_model: str | None = None
    local_triage_model: str | None = None
    cloud_provider: str | None = None
    cloud_primary_model: str | None = None
    cloud_triage_model: str | None = None
    setup_deferred_at: datetime | None = None
    restart_required: bool = False
    hardware_probe_id: str | None = None

    @model_validator(mode="after")
    def keep_only_active_routing(self) -> "SetupIntent":
        if self.ai_mode != "local":
            self.local_primary_model = None
            self.local_triage_model = None
        if self.ai_mode != "cloud":
            self.cloud_provider = None
            self.cloud_primary_model = None
            self.cloud_triage_model = None
        return self


class IntentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_mode: AiMode | None = None
    backend_profile: BackendProfile | None = None
    experience: Literal["essential", "full_ai", "custom"] | None = None
    local_primary_model: str | None = None
    local_triage_model: str | None = None
    cloud_provider: str | None = None
    cloud_primary_model: str | None = None
    cloud_triage_model: str | None = None
    setup_deferred_at: datetime | None = None
    restart_required: bool | None = None
    hardware_probe_id: str | None = None

