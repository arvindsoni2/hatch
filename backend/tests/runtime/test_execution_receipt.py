"""A staged side effect may continue only after a fenced durable receipt."""

from datetime import timedelta
from sqlalchemy import select
from app.runtime.workflow.models import TaskAttemptRecord
from workflow_test_support import start_and_claim


async def test_completed_artifact_receipt_allows_next_gateway_intent(workflow_runtime):
    kernel, factory = workflow_runtime
    now = kernel.clock.now()
    _, claim = await start_and_claim(kernel, now=now)
    values = dict(
        capability_id="artifact.render_cv",
        capability_version=1,
        side_effect_class="artifact_generation",
        idempotency_class="idempotent_with_key",
        reconciliation_reference="synthetic.receipt",
    )
    assert await kernel.begin_execution_intent(claim, now=now, **values)
    assert await kernel.persist_execution_result(
        claim,
        execution_role="artifact",
        result_class="success",
        started_at=now,
        finished_at=now,
        latency_ms=0,
        metadata={},
        **values,
    )

    async def absent(uow):
        return False

    assert not await kernel.acknowledge_execution_receipt(
        claim, receipt_ref="artifact:one", verify_receipt=absent
    )
    assert not await kernel.begin_execution_intent(claim, now=now, **values)

    async def verified(uow):
        return True

    assert await kernel.acknowledge_execution_receipt(
        claim, receipt_ref="artifact:one", verify_receipt=verified
    )
    async with factory.session_factory() as db:
        attempt = await db.scalar(select(TaskAttemptRecord))
        assert attempt.result_ref_json == {"execution_receipt_ref": "artifact:one"}
    assert await kernel.begin_execution_intent(claim, now=now, **values)
    assert not await kernel.acknowledge_execution_receipt(
        claim,
        receipt_ref="artifact:one",
        verify_receipt=verified,
        now=now + timedelta(seconds=31),
    )
