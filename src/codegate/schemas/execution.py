"""ExecutionReport — the result returned by the executor after implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Result of post-execution validation (e.g., mvn test, npm test)."""

    type: str = Field(description="Project type: 'maven', 'gradle', 'npm', etc.")
    command: str = Field(description="The command that was run.")
    exit_code: int = Field(description="Process exit code (0 = success).")
    passed: bool = Field(description="Whether validation passed.")
    error_summary: Optional[str] = Field(
        default=None,
        description="Brief error description if validation failed.",
    )
    tests_run: int = Field(default=0, description="Number of tests executed.")
    tests_failed: int = Field(default=0, description="Number of tests that failed.")
    stdout_tail: Optional[str] = Field(
        default=None,
        description="Last N lines of stdout for diagnostics.",
    )


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

    # === File content (for real executors that produce actual file changes) ===
    files_content: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of relative filepath → current file content after execution.",
    )
    baseline_content: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of relative filepath → content at HEAD (before execution). "
        "Only populated for modified files (not new files).",
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
        "Example: 'builtin_llm', 'opencode', 'gemini', 'claude_code'",
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

    # === Execution state ===
    timed_out: bool = Field(
        default=False,
        description="Whether the executor timed out before completion.",
    )
    validation_result: Optional[ValidationResult] = Field(
        default=None,
        description="Result of post-execution validation (tests, build).",
    )
