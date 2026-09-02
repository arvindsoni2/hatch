"""Deterministic resolution of only a task's declared context."""

from __future__ import annotations

from uuid import uuid4

from ..storage.contracts import RuntimeUnitOfWorkFactory
from .models import (
    INITIAL_CONTEXT_CAPABILITIES,
    ContextItem,
    ContextOmission,
    ContextPackage,
    ContextRequirement,
    context_package_hash,
    validate_context_item_metadata,
)
from .registry import ContextRegistry, RegisteredContextProvider


class ContextResolutionError(ValueError):
    """A stable, caller-safe context resolution failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ContextResolver:
    """Resolve declared providers and bind one immutable package to an attempt."""

    def __init__(
        self, uow_factory: RuntimeUnitOfWorkFactory, registry: ContextRegistry
    ) -> None:
        self._uow_factory = uow_factory
        self._registry = registry

    async def resolve(
        self,
        task_attempt_id: str,
        requirements: tuple[ContextRequirement, ...],
        budget: int,
    ) -> ContextPackage:
        if (
            isinstance(budget, bool)
            or not isinstance(budget, int)
            or not 1 <= budget <= 32768
        ):
            raise ContextResolutionError("context_budget_invalid")
        items: list[ContextItem] = []
        omissions: list[ContextOmission] = []
        seen_capabilities: set[str] = set()
        for requirement in requirements:
            if requirement.capability in seen_capabilities:
                raise ContextResolutionError("context_requirement_duplicate")
            seen_capabilities.add(requirement.capability)
            provider = self._registry.provider_for(requirement.capability)
            if (
                requirement.capability not in INITIAL_CONTEXT_CAPABILITIES
                or provider is None
            ):
                if requirement.required:
                    raise ContextResolutionError("context_required_missing")
                omissions.append(
                    ContextOmission(
                        capability=requirement.capability,
                        reason=(
                            "context_capability_unknown"
                            if requirement.capability
                            not in INITIAL_CONTEXT_CAPABILITIES
                            else "context_provider_missing"
                        ),
                    )
                )
                continue
            item = await self._resolve_item(provider, task_attempt_id, requirement)
            if item is None:
                if requirement.required:
                    raise ContextResolutionError("context_required_missing")
                omissions.append(
                    ContextOmission(
                        capability=requirement.capability,
                        reason="context_source_missing",
                    )
                )
                continue
            try:
                validate_context_item_metadata(item)
            except ValueError:
                raise ContextResolutionError(
                    "context_package_metadata_unsafe"
                ) from None
            if item.token_estimate > (requirement.max_tokens or budget):
                if requirement.required:
                    raise ContextResolutionError("context_budget_exceeded")
                omissions.append(
                    ContextOmission(
                        capability=requirement.capability,
                        reason="context_budget_exceeded",
                    )
                )
                continue
            if (
                sum(entry.token_estimate for entry in items) + item.token_estimate
                > budget
            ):
                if requirement.required:
                    raise ContextResolutionError("context_budget_exceeded")
                omissions.append(
                    ContextOmission(
                        capability=requirement.capability,
                        reason="context_budget_exceeded",
                    )
                )
                continue
            items.append(item)
        package = self._package(task_attempt_id, tuple(items), tuple(omissions))
        try:
            async with self._uow_factory.transaction() as uow:
                await uow.context_packages.persist_and_bind(package)
                await uow.commit()
        except ValueError as error:
            if str(error) in {
                "context_package_already_bound",
                "context_package_metadata_unsafe",
                "context_task_attempt_missing",
            }:
                raise ContextResolutionError(str(error)) from None
            raise ContextResolutionError("context_package_persistence_failed") from None
        return package

    async def load(self, package_id: str) -> ContextPackage | None:
        try:
            async with self._uow_factory.transaction() as uow:
                return await uow.context_packages.load(package_id)
        except ValueError:
            raise ContextResolutionError("context_package_corrupt") from None

    @staticmethod
    async def _resolve_item(
        provider: RegisteredContextProvider,
        task_attempt_id: str,
        requirement: ContextRequirement,
    ) -> ContextItem | None:
        try:
            resolve = getattr(provider, "resolve", None)
            if resolve is None:
                raise TypeError("provider does not expose resolve")
            item = await resolve(task_attempt_id, requirement)
        except Exception:
            raise ContextResolutionError("context_provider_invalid")
        if item is not None and (
            not isinstance(item, ContextItem)
            or item.capability != requirement.capability
            or item.provider_id != provider.provider_id
        ):
            raise ContextResolutionError("context_provider_invalid")
        return item

    @staticmethod
    def _package(
        task_attempt_id: str,
        items: tuple[ContextItem, ...],
        omissions: tuple[ContextOmission, ...],
    ) -> ContextPackage:
        content_hash = context_package_hash(task_attempt_id, items, omissions)
        return ContextPackage(
            id=uuid4().hex,
            task_attempt_id=task_attempt_id,
            items=items,
            omissions=omissions,
            total_token_estimate=sum(item.token_estimate for item in items),
            content_hash=content_hash,
        )
