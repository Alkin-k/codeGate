"""Sandbox Report — evidence from an isolated executor run."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SandboxReport(BaseModel):
    """Evidence produced by running an executor inside an isolated sandbox.

    The sandbox ensures the original project directory is never modified
    by the executor. All changes are captured as diffs and patches for
    audit trail.

    diff_content and patch_content store the actual text content so that
    evidence survives sandbox cleanup.
    """

    enabled: bool = True
    strategy: str = "disabled"  # "git_worktree" | "temp_copy" | "disabled"
    project_dir: str = ""
    sandbox_dir: str = ""
    base_ref: str = "none"  # git commit hash or "none" for copy strategy
    changed_files: List[str] = Field(default_factory=list)
    diff_path: Optional[str] = None
    patch_path: Optional[str] = None
    diff_content: Optional[str] = None  # Actual diff text, survives cleanup
    patch_content: Optional[str] = None  # Actual patch text, survives cleanup
    created_at: str = ""
    cleanup_status: str = "pending"  # "cleaned" | "preserved" | "failed" | "pending"
