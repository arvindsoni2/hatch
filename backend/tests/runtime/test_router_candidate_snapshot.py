"""Durable candidate-snapshot contracts for routing decisions."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select

from app.runtime.evaluation import RoutingDecisionRecord
from app.runtime.intelligence import (
    ModelDescriptor,
    ModelRegistry,
    ModelRouter,
    RoutingPreference,
    RoutingRequirements,
)

from workflow_test_support import start_and_claim


async def test_router_persists_a_metadata_only_candidate_snapshot(
    workflow_runtime,
) -> None:
    """Dropping exclusion/rank snapshot data must make this test fail."""
    kernel, factory = workflow_runtime
    _run, claim = await start_and_claim(kernel, now=datetime(2030, 1, 1))
    router = ModelRouter(
        ModelRegistry(
            (
                ModelDescriptor(
                    model_id="router-model",
                    version="2026.09",
                    provider="llamacpp",
                    model_name="provider/native:model",
                    capabilities=frozenset({"structured_output"}),
                    quality_score=0.8,
                    base_rank=10,
                    local_or_cloud="local",
                ),
            )
        )
    )
    decision = router.route(
        RoutingRequirements(
            task_id="router.snapshot",
            task_version=1,
            required_capabilities=frozenset({"structured_output"}),
        ),
        None,
        RoutingPreference.auto(),
    )

    async with factory.transaction() as uow:
        await router.persist_decision(
            uow.evaluations,
            task_attempt_id=claim.task_attempt_id,
            capability_id="llm.generate_structured",
            decision=decision,
        )
        await uow.commit()

    async with factory.session_factory() as session:
        record = (await session.scalars(select(RoutingDecisionRecord))).one()
    assert record.task_id == "router.snapshot"
    assert record.task_version == 1
    assert record.model_version == "2026.09"
    assert record.evidence_snapshot_id == decision.evidence_snapshot_id
    assert json.loads(json.dumps(record.candidate_snapshot_json)) == [
        {
            "model_id": "router-model",
            "model_version": "2026.09",
            "provider": "llamacpp",
            "eligible": True,
            "excluded_reason_codes": [],
            "rank_components": {"base": 10.0, "evidence": 0.0, "preference": 0.0},
            "final_rank": 10.0,
        }
    ]
