"""Contract Drift Reviewer — audits implementation against the approved contract.

This is CodeGate's core differentiator: checking not just "is the code good?"
but "does the code match what was agreed upon?"
"""

from __future__ import annotations

import logging

from codegate.config import get_config
from codegate.llm import call_llm_json, load_prompt
from codegate.schemas.review import ReviewFinding
from codegate.schemas.work_item import WorkflowStatus
from codegate.workflow.state import GovernanceState

logger = logging.getLogger(__name__)


def run_reviewer(state: GovernanceState) -> GovernanceState:
    """Run the Review Gate node.

    Compares the ExecutionReport against the ImplementationContract
    to find drift, gaps, and issues.
    """
    if state.contract is None or state.execution_report is None:
        state.error = "Cannot review: missing contract or execution report"
        return state

    config = get_config()
    model = config.models.review_model
    system_prompt = load_prompt("reviewer")

    user_message = _build_review_prompt(state)

    result, tokens = call_llm_json(
        model=model,
        system_prompt=system_prompt,
        user_message=user_message,
    )
    state.add_tokens("reviewer", tokens)

    try:
        findings, drift_score, coverage_score = _parse_review(result)
        state.review_findings = findings
        # Store scores temporarily for the gatekeeper
        state.review_drift_score = drift_score
        state.review_coverage_score = coverage_score

        blocking_count = sum(1 for f in findings if f.blocking)
        logger.info(
            f"Review complete: {len(findings)} findings "
            f"({blocking_count} blocking), "
            f"drift={drift_score}, coverage={coverage_score}"
        )
    except Exception as e:
        logger.error(f"Failed to parse review findings: {e}")
        state.error = f"Review parsing failed: {e}"

    return state


def _build_review_prompt(state: GovernanceState) -> str:
    """Build the prompt for the reviewer with contract + implementation side by side."""
    contract = state.contract
    report = state.execution_report
    assert contract is not None and report is not None

    parts = [
        "## APPROVED CONTRACT\n",
        "### Goals",
    ]
    for i, g in enumerate(contract.goals):
        parts.append(f"  [{i}] {g}")

    parts.append("\n### Non-Goals")
    for i, ng in enumerate(contract.non_goals):
        parts.append(f"  [{i}] {ng}")

    parts.append("\n### Acceptance Criteria")
    for i, ac in enumerate(contract.acceptance_criteria):
        parts.append(f"  [{i}] [{ac.priority}] {ac.description}")
        parts.append(f"      Verify: {ac.verification}")

    if contract.constraints:
        parts.append("\n### Constraints")
        for i, c in enumerate(contract.constraints):
            parts.append(f"  [{i}] {c}")

    if contract.assumed_defaults:
        parts.append("\n### Assumed Defaults (watch for these)")
        for d in contract.assumed_defaults:
            parts.append(f"  - {d.topic}: {d.assumed_value} ({d.reason})")

    parts.append("\n---\n")
    parts.append("## IMPLEMENTATION\n")
    parts.append(f"### Executor Summary\n{report.summary}\n")
    parts.append(f"### Files\n{', '.join(report.file_list) if report.file_list else 'N/A'}\n")

    if report.goals_addressed:
        parts.append(f"### Goals Addressed (self-reported): {report.goals_addressed}")
    if report.unresolved_items:
        parts.append("\n### Unresolved Items (self-reported)")
        for item in report.unresolved_items:
            parts.append(f"  - {item}")

    parts.append(f"\n### Code\n```\n{report.code_output}\n```\n")

    parts.append(
        "## Your Task\n\n"
        "Audit this implementation against the contract.\n"
        "Check: goal coverage, drift, non-goal violations, constraint compliance, "
        "correctness, security.\n\n"
        "Respond with JSON:\n"
        "```json\n"
        "{\n"
        '  "findings": [\n'
        "    {\n"
        '      "category": "drift|completeness|correctness|security|maintainability",\n'
        '      "severity": "P0|P1|P2",\n'
        '      "message": "...",\n'
        '      "contract_clause_ref": "goal[0]|acceptance_criteria[1]|...",\n'
        '      "code_location": "file:line or function name",\n'
        '      "blocking": true|false,\n'
        '      "suggestion": "..."\n'
        "    }\n"
        "  ],\n"
        '  "drift_score": 0-100,\n'
        '  "coverage_score": 0-100\n'
        "}\n"
        "```"
    )

    return "\n".join(parts)


def _parse_review(data: dict) -> tuple[list[ReviewFinding], int, int]:
    """Parse LLM output into ReviewFindings + scores."""
    findings = []
    for f in data.get("findings", []):
        if isinstance(f, dict):
            findings.append(ReviewFinding(
                category=f.get("category", "correctness"),
                severity=f.get("severity", "P2"),
                message=f.get("message", ""),
                contract_clause_ref=f.get("contract_clause_ref", ""),
                code_location=f.get("code_location", ""),
                blocking=f.get("blocking", False),
                suggestion=f.get("suggestion", ""),
            ))

    drift_score = int(data.get("drift_score", 50))
    coverage_score = int(data.get("coverage_score", 50))

    return findings, drift_score, coverage_score
