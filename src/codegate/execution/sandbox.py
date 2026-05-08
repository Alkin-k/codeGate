"""Implementation Sandbox — isolates executor changes from the original project.

The sandbox ensures that external coding executors (Codex, Gemini, OpenCode, etc.)
never modify the original project directory. All changes are captured as diffs
and patches for the governance audit trail.

Strategies:
  - git_worktree: Creates a git worktree (preferred, preserves git history)
  - temp_copy: Copies project to a temp directory (fallback for non-git projects)
"""

from __future__ import annotations

import difflib
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from codegate.schemas.sandbox import SandboxReport

logger = logging.getLogger(__name__)


class ExecutionSandbox:
    """Isolates executor changes from the original project directory.

    Usage:
        with ExecutionSandbox(project_dir) as sandbox:
            # executor runs in sandbox.sandbox_dir
            adapter.execute(contract, context, feedback)
        # sandbox.report contains changed_files, diff, patch
    """

    def __init__(
        self,
        project_dir: Path | str,
        strategy: str = "auto",
        base_dir: Optional[Path] = None,
    ):
        """
        Args:
            project_dir: The original project directory to protect.
            strategy: "auto" (try worktree, fallback to copy),
                      "git_worktree" (force worktree),
                      "temp_copy" (force copy).
            base_dir: Parent directory for sandbox worktrees/temp dirs.
                      Defaults to system temp directory.
        """
        self.project_dir = Path(project_dir).resolve()
        self.strategy = strategy
        self.base_dir = base_dir or Path(tempfile.gettempdir())
        self.sandbox_dir: Optional[Path] = None
        self._base_ref: str = "none"
        self._is_worktree: bool = False
        self._created_at: str = ""
        self.report: Optional[SandboxReport] = None

    def __enter__(self) -> ExecutionSandbox:
        self.create()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            self.collect_changes()
        except Exception as e:
            logger.error(f"Failed to collect sandbox changes: {e}")
            if self.report:
                self.report.cleanup_status = "failed"
        if exc_type is None:
            self.cleanup()
        else:
            # Exception path — keep sandbox for evidence, mark as preserved
            if self.report and self.report.cleanup_status == "pending":
                self.report.cleanup_status = "preserved"

    def create(self) -> SandboxReport:
        """Create the sandbox and return an initial report."""
        self._created_at = datetime.now(timezone.utc).isoformat()

        if self.strategy == "auto":
            if self._is_git_repo():
                return self._create_worktree()
            else:
                return self._create_copy()
        elif self.strategy == "git_worktree":
            return self._create_worktree()
        elif self.strategy == "temp_copy":
            return self._create_copy()
        else:
            raise ValueError(f"Unknown sandbox strategy: {self.strategy}")

    def collect_changes(self) -> SandboxReport:
        """After executor runs, detect changes and generate diff/patch.

        If called multiple times, returns the existing report without
        re-scanning (to avoid overwriting a previously collected report).
        """
        if self.report is not None and self.report.changed_files:
            return self.report
        if not self.sandbox_dir or not self.sandbox_dir.exists():
            self.report = SandboxReport(
                enabled=True,
                strategy=self.strategy,
                project_dir=str(self.project_dir),
                sandbox_dir="",
                created_at=self._created_at,
                cleanup_status="failed",
            )
            return self.report

        changed_files = []
        diff_path = None
        patch_path = None
        diff_content = None
        patch_content = None

        if self._is_worktree:
            changed_files = self._detect_git_changes()
        else:
            changed_files = self._detect_copy_changes()

        if changed_files:
            diff_path, diff_content = self._generate_diff(changed_files)
            if self._is_worktree:
                patch_path, patch_content = self._generate_patch()

        self.report = SandboxReport(
            enabled=True,
            strategy="git_worktree" if self._is_worktree else "temp_copy",
            project_dir=str(self.project_dir),
            sandbox_dir=str(self.sandbox_dir),
            base_ref=self._base_ref,
            changed_files=changed_files,
            diff_path=str(diff_path) if diff_path else None,
            patch_path=str(patch_path) if patch_path else None,
            diff_content=diff_content,
            patch_content=patch_content,
            created_at=self._created_at,
            cleanup_status="pending",
        )
        return self.report

    def cleanup(self) -> None:
        """Remove the sandbox directory."""
        if not self.sandbox_dir or not self.sandbox_dir.exists():
            if self.report:
                self.report.cleanup_status = "cleaned"
            return

        try:
            if self._is_worktree:
                self._remove_worktree()
            else:
                shutil.rmtree(self.sandbox_dir, ignore_errors=True)
            if self.report:
                self.report.cleanup_status = "cleaned"
            logger.info(f"Sandbox cleaned up: {self.sandbox_dir}")
        except Exception as e:
            logger.error(f"Sandbox cleanup failed: {e}")
            if self.report:
                self.report.cleanup_status = "failed"

    def preserve(self) -> None:
        """Keep the sandbox directory for inspection (do not clean up)."""
        if self.report:
            self.report.cleanup_status = "preserved"

    # ---- Strategy implementations -------------------------------------------

    def _is_git_repo(self) -> bool:
        """Check if project_dir is inside a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _create_worktree(self) -> SandboxReport:
        """Create a git worktree as the sandbox."""
        # Get current commit as base ref
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=5,
            )
            self._base_ref = result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            self._base_ref = "unknown"

        # Create a unique branch name for the worktree
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        branch_name = f"codegate-sandbox-{timestamp}"
        self.sandbox_dir = self.base_dir / f"codegate-sandbox-{timestamp}"
        self._is_worktree = True

        try:
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(self.sandbox_dir)],
                capture_output=True,
                text=True,
                cwd=str(self.project_dir),
                timeout=30,
                check=True,
            )
            logger.info(f"Created git worktree sandbox: {self.sandbox_dir}")
        except subprocess.CalledProcessError as e:
            logger.warning(f"git worktree failed, falling back to copy: {e}")
            return self._create_copy()

        self.report = SandboxReport(
            enabled=True,
            strategy="git_worktree",
            project_dir=str(self.project_dir),
            sandbox_dir=str(self.sandbox_dir),
            base_ref=self._base_ref,
            created_at=self._created_at,
            cleanup_status="pending",
        )
        return self.report

    def _create_copy(self) -> SandboxReport:
        """Create a temp copy of the project as the sandbox."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        self.sandbox_dir = self.base_dir / f"codegate-copy-{timestamp}"
        self._is_worktree = False

        # Copy project, excluding .git to keep it lightweight
        shutil.copytree(
            str(self.project_dir),
            str(self.sandbox_dir),
            ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules", ".venv"),
        )
        logger.info(f"Created copy sandbox: {self.sandbox_dir}")

        self.report = SandboxReport(
            enabled=True,
            strategy="temp_copy",
            project_dir=str(self.project_dir),
            sandbox_dir=str(self.sandbox_dir),
            base_ref=self._base_ref,
            created_at=self._created_at,
            cleanup_status="pending",
        )
        return self.report

    def _remove_worktree(self) -> None:
        """Remove a git worktree."""
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(self.sandbox_dir)],
            capture_output=True,
            text=True,
            cwd=str(self.project_dir),
            timeout=30,
        )

    # ---- Change detection ---------------------------------------------------

    def _detect_git_changes(self) -> list[str]:
        """Detect changed files in a worktree via git diff.

        Combines tracked changes (git diff HEAD) and untracked files
        (git ls-files --others) so that both modified and new files are
        detected in a single call.
        """
        changed: list[str] = []
        try:
            # Tracked changes (modified/deleted files)
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(self.sandbox_dir),
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                changed.extend(f for f in result.stdout.strip().split("\n") if f)

            # Untracked files (new files not in index)
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                capture_output=True,
                text=True,
                cwd=str(self.sandbox_dir),
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                untracked = [f for f in result.stdout.strip().split("\n") if f]
                # Avoid duplicates
                existing = set(changed)
                changed.extend(f for f in untracked if f not in existing)
        except Exception as e:
            logger.warning(f"Git change detection failed: {e}")
        return changed

    def _detect_copy_changes(self) -> list[str]:
        """Detect changed files by comparing copy against original.

        Detects three kinds of changes:
        - New files: exist in sandbox but not in original
        - Modified files: exist in both but content differs
        - Deleted files: exist in original but not in sandbox
        """
        changed = []
        if not self.sandbox_dir:
            return changed

        sandbox_files: set[str] = set()
        for root, _dirs, files in os.walk(str(self.sandbox_dir)):
            rel_root = Path(root).relative_to(self.sandbox_dir)
            for fname in files:
                rel_path = str(rel_root / fname)
                sandbox_files.add(rel_path)
                sandbox_file = Path(root) / fname
                original_file = self.project_dir / rel_root / fname

                if not original_file.exists():
                    changed.append(rel_path)
                    continue

                try:
                    if sandbox_file.read_bytes() != original_file.read_bytes():
                        changed.append(rel_path)
                except (OSError, PermissionError):
                    changed.append(rel_path)

        # Detect deleted files (in original but not in sandbox)
        for root, _dirs, files in os.walk(str(self.project_dir)):
            rel_root = Path(root).relative_to(self.project_dir)
            for fname in files:
                rel_path = str(rel_root / fname)
                if rel_path not in sandbox_files:
                    changed.append(rel_path)

        return sorted(changed)

    # ---- Diff/Patch generation ----------------------------------------------

    def _generate_diff(self, changed_files: list[str]) -> tuple[Optional[Path], Optional[str]]:
        """Generate a unified diff file for all changed files.

        Returns (path, content) tuple. Content is preserved even after
        sandbox cleanup for artifact persistence.
        """
        if not self.sandbox_dir:
            return None, None

        diff_lines = []
        for rel_path in changed_files:
            sandbox_file = self.sandbox_dir / rel_path
            original_file = self.project_dir / rel_path

            try:
                original_content = original_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            except (OSError, FileNotFoundError):
                original_content = []

            try:
                sandbox_content = sandbox_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            except (OSError, FileNotFoundError):
                sandbox_content = []

            diff = difflib.unified_diff(
                original_content,
                sandbox_content,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
            )
            diff_lines.extend(diff)

        if not diff_lines:
            return None, None

        content = "".join(diff_lines)
        diff_path = self.sandbox_dir / "candidate.diff"
        diff_path.write_text(content, encoding="utf-8")
        return diff_path, content

    def _generate_patch(self) -> tuple[Optional[Path], Optional[str]]:
        """Generate a git format-patch for worktree changes.

        Returns (path, content) tuple. Content is preserved even after
        sandbox cleanup for artifact persistence.
        """
        if not self.sandbox_dir:
            return None, None

        try:
            # Stage all changes
            subprocess.run(
                ["git", "add", "-A"],
                capture_output=True,
                text=True,
                cwd=str(self.sandbox_dir),
                timeout=10,
            )
            # Create a temporary commit for the patch
            subprocess.run(
                ["git", "commit", "-m", "sandbox changes", "--allow-empty"],
                capture_output=True,
                text=True,
                cwd=str(self.sandbox_dir),
                timeout=10,
            )
            # Generate format-patch
            result = subprocess.run(
                ["git", "format-patch", "-1", "--stdout"],
                capture_output=True,
                text=True,
                cwd=str(self.sandbox_dir),
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                content = result.stdout
                patch_path = self.sandbox_dir / "candidate.patch"
                patch_path.write_text(content, encoding="utf-8")
                return patch_path, content
        except Exception as e:
            logger.warning(f"Patch generation failed: {e}")
        return None, None
