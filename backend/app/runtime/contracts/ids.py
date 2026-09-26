"""Semantically distinct identifiers used by runtime public contracts."""

from typing import NewType

WorkflowRunId = NewType("WorkflowRunId", str)
WorkflowStepId = NewType("WorkflowStepId", str)
TaskAttemptId = NewType("TaskAttemptId", str)
ExecutionId = NewType("ExecutionId", str)
PolicyDecisionId = NewType("PolicyDecisionId", str)
RoutingDecisionId = NewType("RoutingDecisionId", str)
ContextPackageId = NewType("ContextPackageId", str)
EventId = NewType("EventId", str)
OutboxEntryId = NewType("OutboxEntryId", str)
ApprovalId = NewType("ApprovalId", str)
