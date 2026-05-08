"""Executor Node — LangGraph node that delegates to an ExecutorAdapter.

This node is the handoff point between the governance layer and the
execution layer. It takes the approved contract from state, calls the
configured ExecutorAdapter, and stores the ExecutionReport back into state.

The executor runs inside an ExecutionSandbox to ensure the original
project directory is never modified by the executor.
"""

from __future__ import annotations

import logging
import os

from codegate.adapters.executor import ExecutorAdapter, BuiltinLLMExecutor
from codegate.execution.sandbox import ExecutionSandbox
from codegate.schemas.work_item import WorkflowStatus
from codegate.workflow.state import GovernanceState

logger = logging.getLogger(__name__)

# Module-level adapter instance. Can be swapped at runtime.
_adapter: ExecutorAdapter = BuiltinLLMExecutor()


def set_executor_adapter(adapter: ExecutorAdapter) -> None:
    """Set the executor adapter to use for code generation.

    Call this before running the governance pipeline to use a
    different executor backend (e.g., OMO, Claude Code).
    """
    global _adapter
    _adapter = adapter
    logger.info(f"Executor adapter set to: {adapter.name}")


def run_executor(state: GovernanceState) -> GovernanceState:
    """Run the Executor node via the configured adapter.

    Takes the approved ImplementationContract and delegates code
    generation to the executor adapter.
    """
    if state.contract is None:
        state.error = "Cannot execute: no approved contract"
        return state

    # Build feedback from previous review if this is a revision cycle
    feedback = ""
    if state.review_findings:
        blocking = [f for f in state.review_findings if f.blocking]
        non_blocking = [f for f in state.review_findings if not f.blocking and f.severity in ("P0", "P1")]

        if blocking:
            feedback = "## Blocking findings (MUST fix):\n"
            for f in blocking:
                feedback += f"- [{f.severity}/{f.category}] {f.message}\n"
                if f.suggestion:
                    feedback += f"  Fix: {f.suggestion}\n"
                if f.contract_clause_ref:
                    feedback += f"  Contract ref: {f.contract_clause_ref}\n"

        if non_blocking:
            feedback += "\n## Other significant findings:\n"
            for f in non_blocking:
                feedback += f"- [{f.severity}/{f.category}] {f.message}\n"
                if f.suggestion:
                    feedback += f"  Fix: {f.suggestion}\n"

    # Include gatekeeper's actionable guidance if available
    if state.gate_decision:
        gd = state.gate_decision
        feedback += f"\n## Gatekeeper assessment:\n"
        feedback += f"- Decision: {gd.decision}\n"
        feedback += f"- Drift score: {gd.drift_score}/100\n"
        feedback += f"- Coverage score: {gd.coverage_score}/100\n"
        if gd.next_action:
            feedback += f"- **What to do next**: {gd.next_action}\n"

    # Include deterministic policy violations if available.
    # These come from the Policy Engine (Rule 1-11 + SEC-1~5)
    # and tell the executor exactly which hard rules were violated.
    if state.policy_violations:
        feedback += "\n## Policy violations (MUST address):\n"
        feedback += (
            "The following deterministic policy rules were violated. "
            "These are NOT suggestions — they are hard requirements.\n"
        )
        for v in state.policy_violations:
            feedback += f"- ❌ {v}\n"

    # Determine project directory for sandbox isolation.
    # Prefer adapter's configured project_dir; fall back to cwd.
    project_dir = _adapter.project_dir or os.getcwd()
    sandbox = ExecutionSandbox(project_dir, strategy="auto")

    try:
        sandbox.create()
        logger.info(
            f"Executor [{_adapter.name}] running in sandbox: "
            f"{sandbox.sandbox_dir} (strategy={sandbox.strategy})"
        )

        report = _adapter.execute(
            contract=state.contract,
            context=state.work_item.context,
            feedback=feedback,
            work_dir=str(sandbox.sandbox_dir),
        )
        # Fill in work item ID
        report.work_item_id = state.work_item.id

        # Collect changes and clean up sandbox
        sandbox.collect_changes()
        sandbox.cleanup()

        # Store sandbox evidence in state
        state.sandbox_report = sandbox.report
        if sandbox.report and sandbox.report.changed_files:
            logger.info(
                f"Sandbox collected {len(sandbox.report.changed_files)} changed file(s)"
            )

        # Track tokens if the adapter reported them
        if report.token_usage:
            state.add_tokens("executor", report.token_usage)

        state.execution_report = report
        state.work_item.transition_to(WorkflowStatus.REVIEWING)
        logger.info(
            f"Execution complete via [{_adapter.name}]: "
            f"{len(report.file_list)} files, "
            f"{len(report.unresolved_items)} unresolved items"
        )
    except Exception as e:
        logger.error(f"Executor [{_adapter.name}] failed: {e}")
        state.error = f"Execution failed ({_adapter.name}): {e}"
        # Preserve sandbox evidence even on failure
        try:
            sandbox.collect_changes()
            if sandbox.report and sandbox.report.cleanup_status == "pending":
                sandbox.report.cleanup_status = "preserved"
            state.sandbox_report = sandbox.report
        except Exception:
            pass

    return state
