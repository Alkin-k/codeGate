"""Contract Drift Reviewer — audits implementation against the approved contract.

This is CodeGate's core differentiator: checking not just "is the code good?"
but "does the code match what was agreed upon?"

Pipeline:
  1. Structural pre-check (Hybrid Extractor) — deterministic baseline diff
  2. LLM review — contract-aware audit
  3. Post-filter — suppress false positives using structural evidence
"""

from __future__ import annotations

import logging

from codegate.config import get_config
from codegate.llm import call_llm_json, load_prompt
from codegate.schemas.review import ReviewFinding
from codegate.workflow.state import GovernanceState

logger = logging.getLogger(__name__)


def run_reviewer(state: GovernanceState) -> GovernanceState:
    """Run the Review Gate node.

    Compares the ExecutionReport against the ImplementationContract
    to find drift, gaps, and issues.

    Three-stage pipeline:
      1. Structural pre-check: compute_baseline_diff() produces ground truth
         about what was added/removed/preserved.
      2. LLM review: prompt includes structural diff as factual evidence.
      3. Post-filter: post_filter_findings() suppresses false positive
         "removed X" claims when X never existed in baseline.
    """
    if state.contract is None or state.execution_report is None:
        state.error = "Cannot review: missing contract or execution report"
        return state

    config = get_config()
    model = config.models.review_model
    system_prompt = load_prompt("reviewer")

    # --- Stage 1: Structural pre-check (Hybrid Extractor) ---
    diff_result = None
    report = state.execution_report
    if report.baseline_content and report.files_content:
        try:
            from codegate.analysis.baseline_diff import compute_baseline_diff
            diff_result = compute_baseline_diff(
                report.baseline_content, report.files_content
            )
            # Persist for audit trail
            state.structural_diff = diff_result.to_dict()
            logger.info(
                f"Structural pre-check: {len(diff_result.removed_from_baseline)} removed, "
                f"{len(diff_result.added_not_in_baseline)} added, "
                f"{len(diff_result.unchanged_baseline)} preserved"
            )
        except Exception as e:
            logger.warning(f"Structural pre-check failed (continuing without): {e}")

    # --- Stage 2: LLM review ---
    user_message = _build_review_prompt(state, diff_result=diff_result)

    try:
        result, tokens = call_llm_json(
            model=model,
            system_prompt=system_prompt,
            user_message=user_message,
        )
    except Exception as e:
        logger.error(f"Reviewer LLM JSON parsing failed: {e}")
        state.review_findings = [
            ReviewFinding(
                category="maintainability",
                severity="P0",
                message=(
                    "Review Gate could not parse the LLM reviewer JSON output. "
                    "This run cannot be safely approved without human review."
                ),
                contract_clause_ref="reviewer_json",
                code_location="reviewer",
                blocking=True,
                suggestion=(
                    "Re-run the reviewer or inspect structural_diff and "
                    "execution_report manually."
                ),
            )
        ]
        state.review_drift_score = 100
        state.review_coverage_score = 0
        return state

    state.add_tokens("reviewer", tokens)

    try:
        findings, drift_score, coverage_score = _parse_review(result)

        # --- Stage 3: Post-filter false positives ---
        if diff_result is not None:
            from codegate.analysis.baseline_diff import post_filter_findings

            # Preserve raw LLM output for audit evidence
            state.raw_review_findings = list(findings)

            kept, suppressed = post_filter_findings(
                findings, diff_result,
                baseline_content=report.baseline_content,
            )
            state.suppressed_findings = [
                {
                    "message": getattr(f, "message", ""),
                    "category": getattr(f, "category", ""),
                    "severity": getattr(f, "severity", ""),
                    "reason": "Suppressed by structural pre-check (pattern not in baseline)",
                }
                for f in suppressed
            ]
            findings = kept

            if suppressed:
                logger.info(
                    f"Post-filter: {len(suppressed)} findings suppressed, "
                    f"{len(kept)} kept"
                )

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


def _build_review_prompt(state: GovernanceState, *, diff_result=None) -> str:
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

    # --- Structural Pre-Check Evidence (Hybrid Extractor output) ---
    if diff_result is not None:
        parts.append("\n---\n")
        parts.append("## STRUCTURAL BASELINE DIFF (ground truth — do NOT contradict)\n")
        parts.append(diff_result.summary_text())
        parts.append(
            "\n> IMPORTANT: The above structural diff is produced by deterministic "
            "code analysis. If the diff says a pattern was NOT removed, you MUST NOT "
            "claim it was removed. Use this as the factual basis for drift findings.\n"
        )

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
