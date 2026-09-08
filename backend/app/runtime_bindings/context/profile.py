"""Read-only profile.yaml context binding."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from hashlib import sha256
import json

from app.agents.tools.profile_loader import get_profile_dict
from app.runtime.context import ContextItem, ContextRequirement


_CAPABILITIES = (
    "candidate.profile_summary",
    "candidate.verified_experience",
    "candidate.achievements",
    "candidate.skills",
)


class ProfileYamlContextProvider:
    """References the existing profile source without retaining profile contents."""

    provider_id = "profile.yaml"
    capabilities = _CAPABILITIES

    def __init__(
        self, loader: Callable[[], Mapping[str, object]] = get_profile_dict
    ) -> None:
        self._loader = loader

    async def resolve(
        self, task_attempt_id: str, requirement: ContextRequirement
    ) -> ContextItem | None:
        try:
            profile = self._loader()
        except Exception:
            return None
        content_hash = sha256(
            json.dumps(
                profile, sort_keys=True, default=str, separators=(",", ":")
            ).encode()
        ).hexdigest()
        return ContextItem(
            capability=requirement.capability,
            provider_id=self.provider_id,
            source_ref="candidate:profile",
            descriptor=requirement.capability.replace(".", "-"),
            summary=None,
            provenance={"source_version": content_hash},
            freshness=None,
            sensitivity="confidential",
            token_estimate=256,
            confidence=1.0,
            content_hash=content_hash,
        )
