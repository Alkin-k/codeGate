"""Artifact Store — persists governance artifacts as JSON files."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import codegate
from codegate.config import get_config
from codegate.schemas.run import (
    RunArtifactBundle,
    RunMetadata,
    generate_run_id,
)
from codegate.schemas.verdict import GovernanceVerdict, VerdictEvidence
from codegate.workflow.state import GovernanceState

logger = logging.getLogger(__name__)

# Artifacts whose presence defines a "complete" run for replay-lite.
# Used as a baseline; the actual required set is unioned with the manifest's
# non-null pointers so deleting a referenced file surfaces as missing.
_CORE_REQUIRED_ARTIFACTS = (
    "run_metadata.json",
    "verdict.json",
    "run_manifest.json",
    "summary.json",
    "work_item.json",
)


class ArtifactStore:
    """Persists all governance artifacts for audit trail."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or get_config().store_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_run(self, state: GovernanceState, run_id: str | None = None) -> Path:
        """Save a complete governance run to disk under a stable run_id.

        v0.7: runs are keyed by a stable ``run_id`` (not the work_item id),
        so re-running the same work item no longer overwrites prior evidence.

        Creates a directory structure:
          artifacts/
            runs/
              {run_id}/
                run_metadata.json
                work_item.json
                contract.json
                execution_report.json
                review_findings.json
                gate_decision.json
                summary.json
                verdict.json
                run_manifest.json
        """
        work_item = state.work_item
        run_id = run_id or generate_run_id(work_item.id)
        run_dir = self.base_dir / "runs" / run_id
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

        # === v0.7 Governance Contract Runtime ===

        # Run metadata (stable identity of this run)
        metadata = self._build_run_metadata(run_id, state)
        self._save_json(run_dir / "run_metadata.json", metadata.model_dump(mode="json"))

        # Governance verdict (single machine-readable final decision)
        verdict = self.generate_verdict(state, run_dir, metadata)
        self._save_json(run_dir / "verdict.json", verdict.model_dump(mode="json"))

        # Generate and save run manifest (index of all artifacts) — written
        # last so it indexes run_metadata.json and verdict.json too.
        manifest = self._generate_manifest(run_dir, state)
        self._save_json(run_dir / "run_manifest.json", manifest)

        # Update the global run index. Failure here must NEVER corrupt or
        # discard the run artifact, so it is best-effort.
        self._update_run_index(metadata, state)

        logger.info(f"Artifacts saved to: {run_dir}")
        return run_dir

    def _build_run_metadata(self, run_id: str, state: GovernanceState) -> RunMetadata:
        """Derive immutable run identity from the governance state."""
        executor_name = None
        if state.execution_report:
            executor_name = state.execution_report.executor_name

        sandbox_strategy = None
        git_base_ref = None
        project_dir = None
        if state.sandbox_report:
            sandbox_strategy = state.sandbox_report.strategy
            git_base_ref = state.sandbox_report.base_ref
            project_dir = state.sandbox_report.project_dir or None

        started_at = state.work_item.created_at
        started_iso = (
            started_at.isoformat()
            if hasattr(started_at, "isoformat")
            else str(started_at)
        )

        return RunMetadata(
            run_id=run_id,
            work_item_id=state.work_item.id,
            codegate_version=codegate.__version__,
            started_at=started_iso,
            completed_at=datetime.now(timezone.utc).isoformat(),
            project_dir=project_dir,
            executor_name=executor_name,
            sandbox_strategy=sandbox_strategy,
            git_base_ref=git_base_ref,
            git_head_ref=None,
            status="failed" if state.error else "completed",
        )

    def generate_verdict(
        self,
        state: GovernanceState,
        run_dir: Path,
        metadata: RunMetadata | None = None,
    ) -> GovernanceVerdict:
        """Build the single machine-readable final verdict for a run.

        Evidence pointers use the same relative-existence discipline as the
        run manifest so the verdict stays valid after the run dir is moved.
        """

        def _rel_or_none(filename: str) -> str | None:
            return filename if (run_dir / filename).exists() else None

        gate = state.gate_decision
        decision = gate.decision if gate else None
        requires_human = bool(gate.requires_human) if gate else False
        if decision == "escalate_to_human":
            requires_human = True

        # Changed files: prefer sandbox evidence, fall back to execution report.
        if state.sandbox_report and state.sandbox_report.changed_files:
            changed_files_count = len(state.sandbox_report.changed_files)
        elif state.execution_report:
            changed_files_count = len(state.execution_report.file_list)
        else:
            changed_files_count = 0

        completed_iterations = (
            len(state.review_history)
            if state.review_history
            else len(state.iteration_history)
        )

        # Reasons: gate summary + any blocking finding messages.
        reasons: list[str] = []
        if gate and gate.summary:
            reasons.append(gate.summary)
        for f in state.review_findings:
            if f.blocking:
                reasons.append(f"[{f.severity}] {f.message}")

        sandbox_enabled = bool(
            state.sandbox_report and state.sandbox_report.enabled
        )

        return GovernanceVerdict(
            run_id=metadata.run_id if metadata else "",
            work_item_id=state.work_item.id,
            final_decision=decision,
            final_status=state.work_item.status.value,
            approved=decision == "approve",
            requires_human=requires_human,
            risk_level=state.work_item.risk_level,
            executor_name=(
                state.execution_report.executor_name
                if state.execution_report
                else None
            ),
            sandbox_enabled=sandbox_enabled,
            sandbox_strategy=(
                state.sandbox_report.strategy if state.sandbox_report else None
            ),
            changed_files_count=changed_files_count,
            blocking_findings_count=sum(1 for f in state.review_findings if f.blocking),
            policy_violations_count=len(state.policy_violations),
            completed_iterations=completed_iterations,
            evidence=VerdictEvidence(
                # The manifest is always written by save_run immediately after
                # the verdict, so it is a guaranteed forward reference.
                manifest="run_manifest.json",
                contract=_rel_or_none("contract.json"),
                sandbox_report=_rel_or_none("sandbox_report.json"),
                candidate_diff=_rel_or_none("candidate.diff"),
                review_history=_rel_or_none("review_history.json"),
                gate_decision=_rel_or_none("gate_decision.json"),
                policy_result=_rel_or_none("policy_result.json"),
            ),
            reasons=reasons,
            next_action=gate.next_action if gate and gate.next_action else None,
        )

    def _update_run_index(self, metadata: RunMetadata, state: GovernanceState) -> None:
        """Append/replace this run in the global run index (best-effort).

        Entries are keyed by run_id so multiple runs of the same work item
        never overwrite each other. Any failure is logged and swallowed so it
        cannot damage the already-persisted run artifact.
        """
        index_path = self.base_dir / "run_index.json"
        try:
            index: dict = {"runs": []}
            if index_path.exists():
                loaded = json.loads(index_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("runs"), list):
                    index = loaded

            entry = {
                "run_id": metadata.run_id,
                "work_item_id": metadata.work_item_id,
                "raw_request": state.work_item.raw_request,
                "decision": state.gate_decision.decision if state.gate_decision else None,
                "status": metadata.status,
                "executor_name": metadata.executor_name,
                "created_at": metadata.completed_at or metadata.started_at,
                "artifact_dir": f"runs/{metadata.run_id}",
                "verdict": f"runs/{metadata.run_id}/verdict.json",
            }

            runs = [r for r in index["runs"] if r.get("run_id") != metadata.run_id]
            runs.append(entry)
            index["runs"] = runs
            self._save_json(index_path, index)
        except Exception as exc:  # noqa: BLE001 — index must never break artifacts
            logger.warning(f"Failed to update run_index.json: {exc}")

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

        # The manifest is written to run_manifest.json immediately after this
        # returns, so index it explicitly — the scan above ran before it existed.
        manifest["artifacts"]["run_manifest.json"] = "run_manifest.json"

        # Add explicit pointers to key artifacts (all relative)
        manifest["run_metadata"] = _rel_or_none("run_metadata.json")
        manifest["verdict"] = _rel_or_none("verdict.json")
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
        """List all saved runs with their summaries (legacy work_item layout).

        Kept byte-for-byte for the existing ``codegate history`` command. The
        v0.7 ``runs/`` subdirectory holds no top-level summary.json, so it is
        harmlessly skipped here. Use ``list_run_metadata`` for v0.7 runs.
        """
        runs = []
        for run_dir in sorted(self.base_dir.iterdir()):
            if run_dir.is_dir():
                summary = self.load_summary(run_dir.name)
                if summary:
                    runs.append(summary)
        return runs

    # === v0.7 Governance Contract Runtime: run queries ===

    @property
    def runs_dir(self) -> Path:
        return self.base_dir / "runs"

    def _resolve_run_dir(self, run_id: str) -> Path | None:
        """Locate a run directory: new ``runs/{run_id}`` or legacy ``{run_id}``."""
        candidate = self.runs_dir / run_id
        if candidate.is_dir():
            return candidate
        legacy = self.base_dir / run_id
        if legacy.is_dir():
            return legacy
        return None

    def _load_json(self, path: Path):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def list_run_metadata(self) -> list[RunMetadata]:
        """List v0.7 runs by parsing each run_metadata.json, newest last."""
        metas: list[RunMetadata] = []
        if not self.runs_dir.exists():
            return metas
        for run_dir in sorted(self.runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            data = self._load_json(run_dir / "run_metadata.json")
            if data:
                try:
                    metas.append(RunMetadata.model_validate(data))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Skipping malformed run_metadata in {run_dir}: {exc}")
        metas.sort(key=lambda m: m.started_at)
        return metas

    def compute_completeness(self, run_dir: Path) -> dict:
        """Replay-lite artifact completeness check (pure file reads).

        The required set is the union of a core baseline and every non-null
        pointer recorded in run_manifest.json, so deleting a referenced file
        (e.g. candidate.diff) surfaces as ``missing`` and lowers the score.
        """
        required: list[str] = list(_CORE_REQUIRED_ARTIFACTS)

        manifest = self._load_json(run_dir / "run_manifest.json")
        if isinstance(manifest, dict):
            pointer_keys = (
                "run_metadata", "verdict", "work_item", "contract",
                "execution_report", "sandbox_report", "review_history",
                "policy_result", "gate_decision", "summary",
                "candidate_diff", "candidate_patch",
            )
            for key in pointer_keys:
                val = manifest.get(key)
                if isinstance(val, str) and val:
                    required.append(val)

        # De-duplicate while preserving order.
        seen: set[str] = set()
        required = [r for r in required if not (r in seen or seen.add(r))]

        present = [r for r in required if (run_dir / r).exists()]
        missing = [r for r in required if not (run_dir / r).exists()]
        score = round(len(present) / len(required), 4) if required else 0.0
        return {
            "required": required,
            "present": present,
            "missing": missing,
            "score": score,
        }

    def load_run(self, run_id: str) -> RunArtifactBundle:
        """Load a run back from disk for inspection/replay (no LLM/executor)."""
        run_dir = self._resolve_run_dir(run_id)
        if run_dir is None:
            raise FileNotFoundError(f"Run not found: {run_id}")

        meta_data = self._load_json(run_dir / "run_metadata.json")
        verdict_data = self._load_json(run_dir / "verdict.json")
        manifest = self._load_json(run_dir / "run_manifest.json")
        summary = self._load_json(run_dir / "summary.json")
        review_history = self._load_json(run_dir / "review_history.json") or []
        policy_result = self._load_json(run_dir / "policy_result.json")

        completeness = self.compute_completeness(run_dir)

        return RunArtifactBundle(
            run_id=run_id,
            run_dir=str(run_dir),
            metadata=RunMetadata.model_validate(meta_data) if meta_data else None,
            verdict=GovernanceVerdict.model_validate(verdict_data) if verdict_data else None,
            manifest=manifest,
            summary=summary,
            review_history=review_history if isinstance(review_history, list) else [],
            policy_result=policy_result,
            present=completeness["present"],
            missing=completeness["missing"],
            completeness_score=completeness["score"],
        )

    def diff_runs(self, run_a: str, run_b: str) -> dict:
        """Compare two governance runs at the artifact/verdict level."""
        bundle_a = self.load_run(run_a)
        bundle_b = self.load_run(run_b)

        def _fields(bundle: RunArtifactBundle) -> dict:
            v = bundle.verdict
            return {
                "run_id": bundle.run_id,
                "final_decision": v.final_decision if v else None,
                "approved": v.approved if v else None,
                "requires_human": v.requires_human if v else None,
                "risk_level": v.risk_level if v else None,
                "executor_name": v.executor_name if v else None,
                "sandbox_strategy": v.sandbox_strategy if v else None,
                "changed_files_count": v.changed_files_count if v else None,
                "blocking_findings_count": v.blocking_findings_count if v else None,
                "policy_violations_count": v.policy_violations_count if v else None,
                "completed_iterations": v.completed_iterations if v else None,
                "reasons": v.reasons if v else [],
                "completeness_score": bundle.completeness_score,
            }

        fields_a = _fields(bundle_a)
        fields_b = _fields(bundle_b)
        differing = sorted(
            k for k in fields_a
            if k not in ("run_id", "reasons") and fields_a[k] != fields_b[k]
        )
        return {"a": fields_a, "b": fields_b, "differing_fields": differing}
