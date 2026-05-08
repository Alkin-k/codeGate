"""Executor Adapter — abstract interface for code execution backends.

The executor is EXTERNAL to the governance system. This adapter pattern
allows plugging in different execution backends:

  - BuiltinLLMExecutor: simulated executor using LLM (for testing only)
  - Future: OpenCodeAdapter, OMOAdapter, ClaudeCodeAdapter, CodexAdapter, GeminiCLIAdapter

The governance layer (spec_council → reviewer → gatekeeper) is
executor-agnostic. It only cares about the ImplementationContract
going in and the ExecutionReport coming back.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from codegate.schemas.contract import ImplementationContract
from codegate.schemas.execution import ExecutionReport

logger = logging.getLogger(__name__)


class ExecutorAdapter(ABC):
    """Abstract base class for executor adapters.

    All executors receive an approved ImplementationContract and return
    an ExecutionReport. The governance layer does not care HOW the code
    is produced — only WHAT comes back.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this executor (e.g., 'claude_code', 'omo')."""
        ...

    @property
    def project_dir(self) -> str:
        """The project directory this adapter operates on.

        Returns the configured project_dir, or empty string if not set.
        Used by ExecutionSandbox to determine the directory to protect.
        """
        return getattr(self, "_project_dir", "") or ""

    @abstractmethod
    def execute(
        self,
        contract: ImplementationContract,
        context: str = "",
        feedback: str = "",
        work_dir: str = "",
    ) -> ExecutionReport:
        """Execute the contract and return a report.

        Args:
            contract: The approved ImplementationContract.
            context: Project context (tech stack, existing code info).
            feedback: Optional feedback from a previous review round
                      (for revision cycles).
            work_dir: If set, the executor MUST run in this directory
                      (sandbox isolation). If empty, use adapter default.

        Returns:
            ExecutionReport with code_output, file_list, summary, etc.
        """
        ...


class BuiltinLLMExecutor(ExecutorAdapter):
    """Simulated executor that uses an LLM to generate code.

    WARNING: This is for testing/benchmarking only. It produces text
    output, not real patches. A real executor (Claude Code, Codex, etc.)
    would produce actual file changes.
    """

    @property
    def name(self) -> str:
        return "builtin_llm"

    def execute(
        self,
        contract: ImplementationContract,
        context: str = "",
        feedback: str = "",
        work_dir: str = "",
    ) -> ExecutionReport:
        from codegate.config import get_config
        from codegate.llm import call_llm_json, load_prompt

        config = get_config()
        model = config.models.exec_model
        system_prompt = load_prompt("executor")
        user_message = self._build_prompt(contract, context, feedback)

        start = time.time()
        result, tokens = call_llm_json(
            model=model,
            system_prompt=system_prompt,
            user_message=user_message,
        )
        elapsed = time.time() - start

        return self._parse_report(
            data=result,
            work_item_id="",  # filled by caller
            model=model,
            tokens=tokens,
            elapsed=elapsed,
        )

    def _build_prompt(
        self,
        contract: ImplementationContract,
        context: str,
        feedback: str,
    ) -> str:
        parts = [
            "## Implementation Contract (APPROVED)\n",
            "### Goals",
        ]
        for i, g in enumerate(contract.goals):
            parts.append(f"{i + 1}. {g}")

        parts.append("\n### Non-Goals (DO NOT implement these)")
        for ng in contract.non_goals:
            parts.append(f"- ❌ {ng}")

        parts.append("\n### Acceptance Criteria")
        for i, ac in enumerate(contract.acceptance_criteria):
            parts.append(f"{i + 1}. [{ac.priority.upper()}] {ac.description}")
            parts.append(f"   Verification: {ac.verification}")

        if contract.constraints:
            parts.append("\n### Constraints")
            for c in contract.constraints:
                parts.append(f"- {c}")

        if contract.required_tests:
            parts.append("\n### Required Tests")
            for t in contract.required_tests:
                parts.append(f"- {t}")

        if context:
            parts.append(f"\n### Project Context\n\n{context}")

        if feedback:
            parts.append(
                f"\n### Previous Review Feedback\n\n"
                f"Your previous implementation was rejected. "
                f"Fix these issues:\n{feedback}"
            )

        parts.append(
            "\n## Your Task\n\n"
            "Implement the above contract. Follow it exactly.\n"
            "Output a JSON with:\n"
            "- code_output: the complete implementation code\n"
            "- file_list: list of file paths created/modified\n"
            "- summary: what you did\n"
            "- goals_addressed: which goal indices you addressed (e.g., [0, 1, 2])\n"
            "- unresolved_items: anything you couldn't complete\n"
            "- self_reported_risks: any concerns\n"
        )

        return "\n".join(parts)

    @staticmethod
    def _parse_report(
        data: dict, work_item_id: str, model: str, tokens: int, elapsed: float,
    ) -> ExecutionReport:
        def _to_str_list(val) -> list:
            if val is None or val == "None" or val == "null":
                return []
            if isinstance(val, str):
                return [val] if val.strip() else []
            if isinstance(val, list):
                return [str(x) for x in val]
            return [str(val)]

        return ExecutionReport(
            work_item_id=work_item_id,
            code_output=str(data.get("code_output", "")),
            file_list=_to_str_list(data.get("file_list")),
            summary=str(data.get("summary", "")),
            goals_addressed=_to_str_list(data.get("goals_addressed")),
            unresolved_items=_to_str_list(data.get("unresolved_items")),
            self_reported_risks=_to_str_list(data.get("self_reported_risks")),
            executor_name="builtin_llm",
            model_used=model,
            token_usage=tokens,
            execution_time_seconds=elapsed,
        )
