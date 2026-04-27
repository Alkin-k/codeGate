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

        # Save review findings
        if state.review_findings:
            self._save_json(
                run_dir / "review_findings.json",
                [f.model_dump(mode="json") for f in state.review_findings],
            )

        # Save gate decision
        if state.gate_decision:
            self._save_json(
                run_dir / "gate_decision.json",
                state.gate_decision.model_dump(mode="json"),
            )

        # Save run summary
        summary = {
            "work_item_id": work_item.id,
            "raw_request": work_item.raw_request,
            "final_status": work_item.status.value,
            "decision": state.gate_decision.decision if state.gate_decision else None,
            "drift_score": state.gate_decision.drift_score if state.gate_decision else None,
            "coverage_score": state.gate_decision.coverage_score if state.gate_decision else None,
            "iterations": state.iteration,
            "total_tokens": state.total_tokens,
            "phase_tokens": state.phase_tokens,
            "findings_count": len(state.review_findings),
            "blocking_findings": sum(1 for f in state.review_findings if f.blocking),
            "clarification_rounds": state.clarification_round,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_json(run_dir / "summary.json", summary)

        logger.info(f"Artifacts saved to: {run_dir}")
        return run_dir

    def _save_json(self, path: Path, data: dict | list) -> None:
        """Save data as formatted JSON."""
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

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
