"""Structured reasoning outputs and durable cross-stage context."""

from typing import Literal, TypedDict

from pydantic import Field, model_validator

from ..models import NonEmptyText, OutputModel


class Impact(OutputModel):
    summary: NonEmptyText
    affected_files: list[NonEmptyText]
    risks: list[NonEmptyText]
    decisions: list[NonEmptyText]


class FileChange(OutputModel):
    path: NonEmptyText
    content: str  # Full replacement text; deletion is deliberately unsupported.


class ChangeSet(OutputModel):
    rationale: NonEmptyText
    changes: list[FileChange] = Field(min_length=1, max_length=12)
    addressed_tasks: list[NonEmptyText] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_paths(self):
        paths = [change.path for change in self.changes]
        if len(paths) != len(set(paths)):
            raise ValueError("Change paths must be unique")
        return self


class TestReview(OutputModel):
    coverage_notes: list[NonEmptyText]
    missing_cases: list[NonEmptyText]


class SecurityReview(OutputModel):
    findings: list[NonEmptyText]
    blocking_findings: list[NonEmptyText]


class Documentation(OutputModel):
    summary: NonEmptyText
    usage: list[NonEmptyText]
    limitations: list[NonEmptyText]


class HumanDecision(OutputModel):
    action: Literal["approve", "reject", "revise", "clarify", "stop"]
    actor: NonEmptyText
    note: NonEmptyText
    requirement: str = ""
    execute_tests: bool = False
    expected_digest: str = ""


class LifecycleState(TypedDict, total=False):
    # Plain serializable values keep checkpoints independent of provider clients.
    run_id: str
    requirement: str
    revision: int
    mode: str
    status: str
    analysis: dict | None
    plan: dict | None
    impact: dict | None
    proposal: dict | None
    policy: dict | None
    snapshot: dict[str, str]
    snapshot_hash: str
    test_python: str
    test_result: dict | None
    security_result: dict | None
    documentation: dict | None
    failure: str | None
    repair_count: int
    execute_tests: bool
    approved_digest: str | None
    decision: dict | None
    route: str
    feedback: list[str]
