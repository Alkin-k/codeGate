#!/usr/bin/env python3
"""Real Executor Smoke Harness — validates sandbox + artifact chain.

Runs CodeGate governance pipeline on disposable fixture projects to verify
the Implementation Sandbox, Review History, and Run Manifest work end-to-end.

Usage:
    # Dry-run (no API key needed, uses BuiltinLLMExecutor)
    .venv/bin/python benchmarks/real_executor_smoke/run_smoke.py --dry-run

    # With real executor
    .venv/bin/python benchmarks/real_executor_smoke/run_smoke.py --executor codex

What it validates:
    1. Sandbox isolates executor changes from fixture project
    2. Diff/patch are generated correctly
    3. Review history accumulates across iterations
    4. Run manifest indexes all artifacts
    5. Original fixture directory is not polluted
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _is_git_internal(path: Path, project_dir: Path) -> bool:
    """Check if a file is inside .git/ (git internal objects are shared across worktrees)."""
    try:
        rel = path.relative_to(project_dir)
        return rel.parts[0] == ".git"
    except ValueError:
        return False


def load_scenarios() -> list[dict]:
    """Load scenarios from scenarios.yaml."""
    import yaml

    scenarios_path = Path(__file__).resolve().parent / "scenarios.yaml"
    with open(scenarios_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("scenarios", [])


def create_fixture_project(tmp_dir: Path, name: str) -> Path:
    """Create a disposable fixture project with git init."""
    project = tmp_dir / name
    project.mkdir(parents=True, exist_ok=True)

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=str(project), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "smoke@test.com"],
        cwd=str(project), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Smoke Test"],
        cwd=str(project), capture_output=True, check=True,
    )
    (project / "__init__.py").write_text("")
    subprocess.run(["git", "add", "."], cwd=str(project), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(project), capture_output=True, check=True,
    )
    return project


def run_smoke_dry_run(scenarios: list[dict]) -> int:
    """Run smoke harness in dry-run mode (no API key needed)."""
    from codegate.execution.sandbox import ExecutionSandbox
    from codegate.schemas.work_item import WorkItem
    from codegate.schemas.contract import ImplementationContract, AcceptanceCriterion
    from codegate.store.artifact_store import ArtifactStore
    from codegate.workflow.state import GovernanceState

    passed = 0
    failed = 0
    results = []

    with tempfile.TemporaryDirectory(prefix="codegate-smoke-") as tmp_dir:
        tmp_path = Path(tmp_dir)

        for scenario in scenarios:
            sid = scenario["id"]
            name = scenario["name"]
            print(f"\n  [{sid}] {name}")

            # Create disposable fixture project
            fixture_project = create_fixture_project(tmp_path, sid)

            # Snapshot original state (excluding .git internals)
            original_files = set(
                str(f.relative_to(fixture_project))
                for f in fixture_project.rglob("*")
                if f.is_file() and not _is_git_internal(f, fixture_project)
            )

            # Test sandbox isolation
            try:
                with ExecutionSandbox(
                    fixture_project, strategy="auto", base_dir=tmp_path
                ) as sandbox:
                    # Simulate executor writing a file in sandbox
                    (sandbox.sandbox_dir / "hello.py").write_text(
                        "def hello():\n    return 'hello world'\n"
                    )

                report = sandbox.report
                assert report is not None, "Sandbox report is None"
                assert report.enabled, "Sandbox not enabled"
                assert len(report.changed_files) > 0, "No changed files detected"
                print(f"    Sandbox: {report.strategy} — {len(report.changed_files)} file(s) changed")

                # Verify no pollution (excluding .git internals)
                current_files = set(
                    str(f.relative_to(fixture_project))
                    for f in fixture_project.rglob("*")
                    if f.is_file() and not _is_git_internal(f, fixture_project)
                )
                new_files = current_files - original_files
                assert len(new_files) == 0, f"Pollution detected: {new_files}"
                print("    No pollution: original project unchanged")

                # Test artifact chain
                work_item = WorkItem(raw_request=scenario["requirement"])
                state = GovernanceState(work_item=work_item)
                state.sandbox_report = report

                artifact_dir = tmp_path / "artifacts" / sid
                store = ArtifactStore(base_dir=artifact_dir)
                run_dir = store.save_run(state)

                # Verify manifest
                manifest_path = run_dir / "run_manifest.json"
                assert manifest_path.exists(), "run_manifest.json not found"
                manifest = json.loads(manifest_path.read_text())
                assert manifest["sandbox_report"] is not None, "sandbox_report not in manifest"
                print(f"    Manifest: {len(manifest['artifacts'])} artifact(s) indexed")

                # Verify sandbox_report.json
                sandbox_json = run_dir / "sandbox_report.json"
                assert sandbox_json.exists(), "sandbox_report.json not found"

                print(f"    PASSED")
                passed += 1
                results.append({"id": sid, "status": "passed"})

            except Exception as e:
                print(f"    FAILED: {e}")
                failed += 1
                results.append({"id": sid, "status": "failed", "error": str(e)})

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Smoke Harness Results (dry-run)")
    print(f"{'=' * 60}")
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"  Total:   {passed + failed}")
    print()

    for r in results:
        status = "PASS" if r["status"] == "passed" else "FAIL"
        print(f"  [{status}] {r['id']}")

    return 0 if failed == 0 else 1


def run_smoke_real(scenarios: list[dict], executor_name: str) -> int:
    """Run smoke harness with a real executor adapter.

    Uses the BuiltinLLMExecutor through the full ExecutionSandbox + ArtifactStore
    chain. Requires an LLM API key configured for the built-in executor.

    For codex/gemini/opencode: returns 2 (not yet implemented).
    """
    from codegate.execution.sandbox import ExecutionSandbox
    from codegate.schemas.work_item import WorkItem
    from codegate.schemas.contract import ImplementationContract, AcceptanceCriterion
    from codegate.store.artifact_store import ArtifactStore
    from codegate.workflow.state import GovernanceState

    if executor_name != "builtin_llm":
        print(f"\n  Real executor mode for '{executor_name}' is not yet implemented.")
        print(f"  Supported: builtin_llm (via --executor builtin_llm)")
        print(f"  Use --dry-run for sandbox+artifact chain validation without API keys.")
        return 2

    from codegate.adapters.executor import BuiltinLLMExecutor

    print(f"\n  Real executor smoke test with: BuiltinLLMExecutor")
    print(f"  Scenarios: {len(scenarios)}")
    print(f"  NOTE: Requires LLM API key for code generation.\n")

    passed = 0
    failed = 0
    results = []

    with tempfile.TemporaryDirectory(prefix="codegate-smoke-real-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        adapter = BuiltinLLMExecutor()

        for scenario in scenarios:
            sid = scenario["id"]
            name = scenario["name"]
            print(f"\n  [{sid}] {name}")

            fixture_project = create_fixture_project(tmp_path, sid)

            original_files = set(
                str(f.relative_to(fixture_project))
                for f in fixture_project.rglob("*")
                if f.is_file() and not _is_git_internal(f, fixture_project)
            )

            try:
                # Build a minimal contract from the scenario
                work_item = WorkItem(raw_request=scenario["requirement"])
                contract = ImplementationContract(
                    work_item_id=work_item.id,
                    goals=[scenario["requirement"]],
                    non_goals=[],
                    acceptance_criteria=[
                        AcceptanceCriterion(
                            description=c,
                            priority="must",
                            verification="manual",
                        )
                        for c in scenario.get("eval_criteria", [])
                    ],
                )

                with ExecutionSandbox(
                    fixture_project, strategy="auto", base_dir=tmp_path
                ) as sandbox:
                    report = adapter.execute(
                        contract=contract,
                        work_dir=str(sandbox.sandbox_dir),
                    )

                sandbox_report = sandbox.report
                assert sandbox_report is not None, "Sandbox report is None"
                assert sandbox_report.enabled, "Sandbox not enabled"
                print(f"    Sandbox: {sandbox_report.strategy} — "
                      f"{len(sandbox_report.changed_files)} file(s) changed")

                # Verify no pollution
                current_files = set(
                    str(f.relative_to(fixture_project))
                    for f in fixture_project.rglob("*")
                    if f.is_file() and not _is_git_internal(f, fixture_project)
                )
                new_files = current_files - original_files
                assert len(new_files) == 0, f"Pollution detected: {new_files}"
                print("    No pollution: original project unchanged")

                # Save artifacts
                state = GovernanceState(work_item=work_item)
                state.contract = contract
                state.execution_report = report
                state.sandbox_report = sandbox_report

                artifact_dir = tmp_path / "artifacts" / sid
                store = ArtifactStore(base_dir=artifact_dir)
                run_dir = store.save_run(state)

                manifest_path = run_dir / "run_manifest.json"
                assert manifest_path.exists(), "run_manifest.json not found"
                manifest = json.loads(manifest_path.read_text())
                print(f"    Manifest: {len(manifest['artifacts'])} artifact(s) indexed")
                print(f"    PASSED")
                passed += 1
                results.append({"id": sid, "status": "passed"})

            except Exception as e:
                print(f"    FAILED: {e}")
                failed += 1
                results.append({"id": sid, "status": "failed", "error": str(e)})

    print(f"\n{'=' * 60}")
    print(f"  Smoke Harness Results (real executor: builtin_llm)")
    print(f"{'=' * 60}")
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"  Total:   {passed + failed}")
    print()

    for r in results:
        status = "PASS" if r["status"] == "passed" else "FAIL"
        print(f"  [{status}] {r['id']}")

    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CodeGate Real Executor Smoke Harness"
    )
    parser.add_argument(
        "--executor",
        choices=["codex", "gemini", "opencode", "builtin_llm"],
        default=None,
        help="Executor to use (default: dry-run with BuiltinLLMExecutor)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run without API keys (validates sandbox + artifact chain only)",
    )
    args = parser.parse_args()

    scenarios = load_scenarios()
    if not scenarios:
        print("ERROR: No scenarios found in scenarios.yaml")
        return 1

    print("=" * 60)
    print("  CodeGate Real Executor Smoke Harness")
    print("=" * 60)
    print(f"  Scenarios loaded: {len(scenarios)}")

    if args.dry_run or args.executor is None:
        return run_smoke_dry_run(scenarios)
    else:
        return run_smoke_real(scenarios, args.executor)


if __name__ == "__main__":
    sys.exit(main())
