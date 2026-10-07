"""Shared state and validated LLM output contracts."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequirementAnalysis(OutputModel):
    normalized_requirement: NonEmptyText
    ambiguities: list[NonEmptyText]
    assumptions: list[NonEmptyText]
    acceptance_criteria: list[NonEmptyText] = Field(min_length=1)


class Task(OutputModel):
    id: NonEmptyText
    description: NonEmptyText
    depends_on: list[NonEmptyText]


class EngineeringPlan(OutputModel):
    tasks: list[Task] = Field(min_length=1)
    execution_order: list[NonEmptyText] = Field(min_length=1)
    risks: list[NonEmptyText]

    @model_validator(mode="after")
    def validate_dependencies(self) -> Self:
        # The LLM proposes a graph; deterministic code rejects invalid graphs.
        ids = [task.id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("Task IDs must be unique")
        if len(self.execution_order) != len(ids) or set(self.execution_order) != set(ids):
            raise ValueError("Execution order must contain every task exactly once")
        positions = {task_id: index for index, task_id in enumerate(self.execution_order)}
        for task in self.tasks:
            if len(task.depends_on) != len(set(task.depends_on)):
                raise ValueError("Dependencies must be unique")
            for dependency in task.depends_on:
                if dependency not in positions:
                    raise ValueError("Dependency refers to an unknown task")
                # Also rules out self-dependencies and cycles.
                if positions[dependency] >= positions[task.id]:
                    raise ValueError("Dependencies must precede their dependent task")
        return self


class EngineeringState(OutputModel):
    # Each field is a LangGraph state channel. Nodes return only changed fields.
    requirement: NonEmptyText
    analysis: RequirementAnalysis | None = None
    plan: EngineeringPlan | None = None
