"""ExecutionReport — the result returned by the executor after implementation."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ExecutionReport(BaseModel):
    """Report from the executor (coding agent) after completing implementation.

    Contains the generated code, a self-assessment, and metadata.
    The Review Gate will compare this against the ImplementationContract.
    """

    work_item_id: str

    # === Output ===
    code_output: str = Field(
        ...,
        description="The generated code / patch / implementation.",
    )
    file_list: list[str] = Field(
        default_factory=list,
        description="List of files created or modified.",
    )

    # === Self-report ===
    summary: str = Field(
        default="",
        description="Executor's own summary of what was implemented.",
    )
    goals_addressed: list[str] = Field(
        default_factory=list,
        description="Which contract goals the executor believes it addressed.",
    )
    unresolved_items: list[str] = Field(
        default_factory=list,
        description="Items the executor could not complete or is unsure about.",
    )
    self_reported_risks: list[str] = Field(
        default_factory=list,
        description="Risks the executor identified during implementation.",
    )

    # === Metadata ===
    executor_name: str = Field(
        default="builtin_llm",
        description="Which executor produced this report. "
        "Example: 'builtin_llm', 'opencode', 'omo', 'claude_code'",
    )
    model_used: str = Field(
        default="",
        description="The actual LLM model used for code generation.",
    )
    token_usage: int = Field(
        default=0,
        description="Total tokens consumed during execution.",
    )
    execution_time_seconds: float = Field(
        default=0.0,
        description="Wall-clock time for execution.",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
