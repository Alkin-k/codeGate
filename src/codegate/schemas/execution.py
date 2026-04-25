"""ExecutionReport — the result returned by the executor after implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Result of post-execution validation (e.g., mvn test, npm test)."""

    type: str = Field(description="Project type: 'maven', 'npm', 'gradle', etc.")
    command: str = Field(description="Validation command run.")
    exit_code: int = Field(description="Process exit code.")
    passed: bool = Field(description="Whether validation passed.")
    error_summary: Optional[str] = Field(
        default=None,
        description="First compilation/test error message (truncated).",
    )
    tests_run: int = Field(default=0)
    tests_failed: int = Field(default=0)
    stdout_tail: str = Field(
        default="",
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
    files_content: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of filepath → file content for created/modified files. "
        "Populated by real executor adapters (e.g., opencode).",
    )
    baseline_content: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of filepath → original content from clean baseline (git HEAD). "
        "Only populated for MODIFIED files (not new). "
        "Enables reviewer to distinguish 'removed baseline code' from 'removed previous iteration code'.",
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

    # === Timeout & Partial Evidence ===
    timed_out: bool = Field(
        default=False,
        description="True if executor was killed due to timeout. "
        "When True, files_content may contain partial changes found on disk.",
    )
    partial_output: Optional[str] = Field(
        default=None,
        description="Truncated stdout from executor before timeout. "
        "Only populated when timed_out=True.",
    )

    # === Post-run Validation ===
    validation_result: Optional[ValidationResult] = Field(
        default=None,
        description="Result of automatic post-run validation "
        "(e.g., mvn test, npm test). Populated when project type is detected.",
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

