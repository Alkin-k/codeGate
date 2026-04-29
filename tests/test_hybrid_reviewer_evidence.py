"""End-to-end reviewer audit evidence test with git-backed baseline content."""

from __future__ import annotations

import subprocess

import codegate.agents.reviewer as reviewer
from codegate.adapters.gemini import GeminiCLIAdapter
from codegate.schemas.contract import AcceptanceCriterion, ImplementationContract
from codegate.schemas.execution import ExecutionReport
from codegate.schemas.work_item import WorkItem
from codegate.store.artifact_store import ArtifactStore
from codegate.workflow.state import GovernanceState


def test_reviewer_persists_hybrid_evidence_from_git_baseline(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    project_dir = repo / "frontend"
    project_dir.mkdir(parents=True)
    source = project_dir / "ConvertController.java"
    source.write_text(
        "public class ConvertController {\n"
        "    public void convert(@Min(72) Integer dpi) {}\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "codegate@example.test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CodeGate Test"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=repo, check=True)

    source.write_text(
        "public class ConvertController {\n"
        "    public void convert(Integer dpi) {}\n"
        "}\n",
        encoding="utf-8",
    )

    changed, baseline = GeminiCLIAdapter()._detect_git_changes(str(project_dir))
    assert changed
    assert baseline

    def fake_review(*args, **kwargs):
        return (
            {
                "findings": [
                    {
                        "category": "drift",
                        "severity": "P1",
                        "message": "Removed @Min(72) annotation from dpi parameter.",
                        "contract_clause_ref": "constraints[0]",
                        "code_location": "ConvertController.java",
                        "blocking": True,
                        "suggestion": "Restore @Min(72).",
                    },
                    {
                        "category": "drift",
                        "severity": "P1",
                        "message": (
                            "Removed HandlerMethodValidationException handler from "
                            "GlobalExceptionHandler."
                        ),
                        "contract_clause_ref": "constraints[0]",
                        "code_location": "GlobalExceptionHandler.java",
                        "blocking": True,
                        "suggestion": "Restore the handler.",
                    },
                    {
                        "category": "completeness",
                        "severity": "P1",
                        "message": "No boundary test was added.",
                        "contract_clause_ref": "acceptance_criteria[0]",
                        "code_location": "(missing)",
                        "blocking": True,
                        "suggestion": "Add a boundary test.",
                    },
                ],
                "drift_score": 20,
                "coverage_score": 80,
            },
            123,
        )

    monkeypatch.setattr(reviewer, "call_llm_json", fake_review)

    work_item = WorkItem(raw_request="Preserve dpi validation")
    contract = ImplementationContract(
        work_item_id=work_item.id,
        goals=["Preserve existing dpi validation while refactoring."],
        non_goals=["Do not remove validation annotations."],
        acceptance_criteria=[
            AcceptanceCriterion(
                description="DPI lower bound remains enforced.",
                verification="Inspect ConvertController.java",
            )
        ],
        constraints=["Preserve baseline validation annotations."],
    )
    report = ExecutionReport(
        work_item_id=work_item.id,
        code_output=changed["ConvertController.java"],
        file_list=["ConvertController.java"],
        files_content=changed,
        baseline_content=baseline,
        summary="Removed annotation during refactor.",
    )
    state = GovernanceState(work_item=work_item, contract=contract, execution_report=report)

    state = reviewer.run_reviewer(state)

    assert state.structural_diff
    assert len(state.raw_review_findings) == 3
    assert len(state.suppressed_findings) == 1
    assert len(state.review_findings) == 2
    assert "HandlerMethodValidationException" in state.suppressed_findings[0]["message"]

    run_dir = ArtifactStore(base_dir=tmp_path / "artifacts").save_run(state)
    assert (run_dir / "structural_diff.json").exists()
    assert (run_dir / "raw_review_findings.json").exists()
    assert (run_dir / "suppressed_findings.json").exists()
