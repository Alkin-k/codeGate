"""Artifact Store — persists governance artifacts as JSON files."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from codegate.config import get_config
from codegate.workflow.state import GovernanceState

logger = logging.getLogger(__name__)


class ArtifactStore:
    """Persists all governance artifacts for audit trail."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or get_config().store_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_run(self, state: GovernanceState) -> Path:
        """Save a complete governance run to disk.

        Creates a directory structure:
          artifacts/
            {work_item_id}/
              work_item.json
              contract.json
              execution_report.json
              review_findings.json
              gate_decision.json
              summary.json
        """
        work_item = state.work_item
        run_dir = self.base_dir / work_item.id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Save work item
        self._save_json(run_dir / "work_item.json", work_item.model_dump(mode="json"))

        # Save contract
        if state.contract:
            self._save_json(run_dir / "contract.json", state.contract.model_dump(mode="json"))

        # Save clarification Q&A
        if state.clarification_questions or state.clarification_answers:
            self._save_json(run_dir / "clarification_qa.json", {
                "round": state.clarification_round,
                "questions": state.clarification_questions,
                "answers": state.clarification_answers,
                "mode": state.clarification_mode,
            })

        # Save execution report
        if state.execution_report:
            self._save_json(
                run_dir / "execution_report.json",
                state.execution_report.model_dump(mode="json"),
            )

        # Save sandbox report (if executor ran in sandbox)
        if state.sandbox_report:
            self._save_json(
                run_dir / "sandbox_report.json",
                state.sandbox_report.model_dump(mode="json"),
            )
            # Save diff/patch content directly (survives sandbox cleanup)
            if state.sandbox_report.diff_content:
                (run_dir / "candidate.diff").write_text(
                    state.sandbox_report.diff_content, encoding="utf-8"
                )
            if state.sandbox_report.patch_content:
                (run_dir / "candidate.patch").write_text(
                    state.sandbox_report.patch_content, encoding="utf-8"
                )

        # Save review findings — always persist, even when empty ([])
        # This ensures CLI evidence is machine-comparable with benchmark evidence.
        self._save_json(
            run_dir / "review_findings.json",
            [f.model_dump(mode="json") for f in state.review_findings],
        )

        # === Audit evidence: structural pre-check pipeline ===

        # Save structural diff (deterministic pre-check output)
        if state.structural_diff:
            self._save_json(run_dir / "structural_diff.json", state.structural_diff)

        # Save raw review findings (LLM output BEFORE post-filter)
        if state.raw_review_findings:
            self._save_json(
                run_dir / "raw_review_findings.json",
                [f.model_dump(mode="json") for f in state.raw_review_findings],
            )

        # Save suppressed findings (with suppression reasons)
        if state.suppressed_findings:
            self._save_json(
                run_dir / "suppressed_findings.json",
                state.suppressed_findings,
            )

        # Save gate decision
        if state.gate_decision:
            self._save_json(
                run_dir / "gate_decision.json",
                state.gate_decision.model_dump(mode="json"),
            )

        # Save policy result (if available)
        if state.policy_result:
            self._save_json(run_dir / "policy_result.json", state.policy_result)

        # Save phase timings (if available)
        if state.phase_timings:
            self._save_json(run_dir / "phase_timings.json", state.phase_timings)

        # Save iteration history (per-iteration evidence for multi-round governance)
        if state.iteration_history:
            self._save_json(run_dir / "iteration_history.json", state.iteration_history)

            # Also save per-iteration structured directories for detailed audit
            iterations_dir = run_dir / "iterations"
            iterations_dir.mkdir(exist_ok=True)
            for entry in state.iteration_history:
                iter_num = entry.get("iteration", 0)
                iter_dir = iterations_dir / str(iter_num)
                iter_dir.mkdir(exist_ok=True)
                self._save_json(iter_dir / "gate_snapshot.json", entry)

        # Save review history (structured multi-round evidence)
        if state.review_history:
            self._save_json(run_dir / "review_history.json", state.review_history)
            # Also save per-iteration review/policy/gate files
            iterations_dir = run_dir / "iterations"
            for entry in state.review_history:
                iter_num = entry.get("iteration", 0)
                iter_dir = iterations_dir / str(iter_num)
                iter_dir.mkdir(parents=True, exist_ok=True)
                if "review_findings" in entry:
                    self._save_json(iter_dir / "review_findings.json", entry["review_findings"])
                if "policy_result" in entry:
                    self._save_json(iter_dir / "policy_result.json", entry["policy_result"])
                if "gate_decision" in entry:
                    self._save_json(iter_dir / "gate_decision.json", entry["gate_decision"])

        # Save run summary
        # Derive gatekeeper's original decision from policy_result if available
        gatekeeper_original = None
        if state.policy_result and state.policy_result.get("gatekeeper_original_decision"):
            gatekeeper_original = state.policy_result["gatekeeper_original_decision"]

        summary = {
            "work_item_id": work_item.id,
            "raw_request": work_item.raw_request,
            "final_status": work_item.status.value,
            "decision": state.gate_decision.decision if state.gate_decision else None,
            "gatekeeper_original_decision": gatekeeper_original,
            "drift_score": state.gate_decision.drift_score if state.gate_decision else None,
            "coverage_score": state.gate_decision.coverage_score if state.gate_decision else None,
            "timed_out": (
                state.execution_report.timed_out
                if state.execution_report and hasattr(state.execution_report, "timed_out")
                else False
            ),
            "completed_iterations": (
                len(state.review_history) if state.review_history
                else len(state.iteration_history)
            ),
            "max_iterations": state.max_iterations,
            "total_tokens": state.total_tokens,
            "phase_tokens": state.phase_tokens,
            "phase_timings": state.phase_timings,
            "findings_count": len(state.review_findings),
            "blocking_findings": sum(1 for f in state.review_findings if f.blocking),
            "advisory_findings": sum(
                1 for f in state.review_findings
                if getattr(f, "disposition", "advisory") == "advisory" and not f.blocking
            ),
            "info_findings": sum(
                1 for f in state.review_findings
                if getattr(f, "disposition", None) == "info"
            ),
            "raw_findings_count": len(state.raw_review_findings),
            "suppressed_findings_count": len(state.suppressed_findings),
            "validation_passed": (
                state.execution_report.validation_result.passed
                if state.execution_report
                and state.execution_report.validation_result
                else None
            ),
            "validation_tests_run": (
                state.execution_report.validation_result.tests_run
                if state.execution_report
                and state.execution_report.validation_result
                else 0
            ),
            "validation_command": (
                state.execution_report.validation_result.command
                if state.execution_report
                and state.execution_report.validation_result
                else None
            ),
            "policy_violations": state.policy_violations,
            "clarification_rounds": state.clarification_round,
            "clarification_questions": state.clarification_questions,
            "clarification_answers": state.clarification_answers,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_json(run_dir / "summary.json", summary)

        # Generate and save run manifest (index of all artifacts)
        manifest = self._generate_manifest(run_dir, state)
        self._save_json(run_dir / "run_manifest.json", manifest)

        logger.info(f"Artifacts saved to: {run_dir}")
        return run_dir

    def _save_json(self, path: Path, data: dict | list) -> None:
        """Save data as formatted JSON."""
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def _generate_manifest(self, run_dir: Path, state: GovernanceState) -> dict:
        """Generate a run manifest that indexes all artifacts produced by this run.

        All paths are relative to run_dir. No absolute filesystem paths
        appear in the manifest so it remains valid after the run directory
        is moved or archived.
        """

        def _rel_or_none(filename: str) -> str | None:
            """Return relative path if file exists in run_dir, else None."""
            return filename if (run_dir / filename).exists() else None

        manifest = {
            "work_item_id": state.work_item.id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": {},
        }

        # Scan run_dir for all .json files and index them (relative paths)
        for json_file in sorted(run_dir.rglob("*.json")):
            rel = str(json_file.relative_to(run_dir))
            manifest["artifacts"][rel] = rel

        # Add explicit pointers to key artifacts (all relative)
        manifest["work_item"] = _rel_or_none("work_item.json")
        manifest["contract"] = _rel_or_none("contract.json")
        manifest["execution_report"] = _rel_or_none("execution_report.json")
        manifest["sandbox_report"] = _rel_or_none("sandbox_report.json")
        manifest["review_history"] = _rel_or_none("review_history.json")
        manifest["policy_result"] = _rel_or_none("policy_result.json")
        manifest["gate_decision"] = _rel_or_none("gate_decision.json")
        manifest["summary"] = _rel_or_none("summary.json")

        # Candidate diff/patch — only present when content was persisted
        manifest["candidate_diff"] = _rel_or_none("candidate.diff")
        manifest["candidate_patch"] = _rel_or_none("candidate.patch")

        return manifest

    def load_summary(self, work_item_id: str) -> dict | None:
        """Load a run summary by work item ID."""
        summary_path = self.base_dir / work_item_id / "summary.json"
        if summary_path.exists():
            return json.loads(summary_path.read_text(encoding="utf-8"))
        return None

    def list_runs(self) -> list[dict]:
        """List all saved runs with their summaries."""
        runs = []
        for run_dir in sorted(self.base_dir.iterdir()):
            if run_dir.is_dir():
                summary = self.load_summary(run_dir.name)
                if summary:
                    runs.append(summary)
        return runs
