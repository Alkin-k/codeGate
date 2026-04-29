#!/usr/bin/env python3
"""Benchmark runner for V2 Frontend Client scenarios.

Reads scenarios.yaml, runs each scenario through the CodeGate governance
pipeline, and saves artifacts to test_results/<run_id>/.

Usage:
    .venv/bin/python benchmarks/v2_frontend_client/run.py --executor gemini
    .venv/bin/python benchmarks/v2_frontend_client/run.py --scenarios t5,t6
    .venv/bin/python benchmarks/v2_frontend_client/run.py --dry-run

Environment:
    Requires a configured .env file at the project root.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logger = logging.getLogger(__name__)

SCENARIOS_FILE = Path(__file__).parent / "scenarios.yaml"
DEFAULT_OUTPUT = PROJECT_ROOT / "test_results"


def load_scenarios(
    scenarios_file: Path = SCENARIOS_FILE,
    filter_ids: list[str] | None = None,
) -> list[dict]:
    """Load and optionally filter scenarios from YAML."""
    with open(scenarios_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    scenarios = data.get("scenarios", [])
    project_meta = {
        "project_name": data.get("project", {}).get("name", "unknown"),
        "repo": data.get("project", {}).get("repo", ""),
        "frontend_dir": data.get("project", {}).get("frontend_dir", ""),
    }

    if filter_ids:
        scenarios = [s for s in scenarios if s["id"] in filter_ids]

    return scenarios, project_meta


def run_scenario(
    scenario: dict,
    executor_name: str,
    executor_model: str,
    project_dir: str,
    timeout: int,
    output_dir: Path,
) -> dict:
    """Run a single scenario through the governance pipeline."""
    from codegate.store.artifact_store import ArtifactStore
    from codegate.workflow.graph import run_governance_pipeline

    scenario_id = scenario["id"]
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Running: {scenario['name']}")
    logger.info(f"{'=' * 60}")

    start_time = time.time()

    try:
        # Run governance pipeline
        state = run_governance_pipeline(
            raw_request=scenario["request"],
            context=scenario.get("context", ""),
            clarification_answers=scenario.get("answers"),
            risk_level=scenario.get("risk_level", "medium"),
        )

        # Policy check runs inside the pipeline graph (policy_check node)

        elapsed = time.time() - start_time

        # Save artifacts
        store = ArtifactStore(output_dir)
        run_dir = store.save_run(state, subdirectory=scenario_id)

        # Extract result summary
        result = {
            "scenario_id": scenario_id,
            "name": scenario["name"],
            "status": "completed",
            "elapsed_seconds": round(elapsed, 1),
            "decision": state.gate_decision.decision if state.gate_decision else None,
            "gatekeeper_original": (
                state.policy_result.get("gatekeeper_original_decision")
                if state.policy_result
                else None
            ),
            "drift_score": (
                state.gate_decision.drift_score if state.gate_decision else None
            ),
            "coverage_score": (
                state.gate_decision.coverage_score if state.gate_decision else None
            ),
            "findings_count": len(state.review_findings),
            "blocking_findings": sum(
                1 for f in state.review_findings if f.blocking
            ),
            "policy_violations": state.policy_violations,
            "security_violations": (
                state.policy_result.get("security", {}).get("security_violations", [])
                if state.policy_result
                else []
            ),
            "security_warnings": (
                state.policy_result.get("security", {}).get("security_warnings", [])
                if state.policy_result
                else []
            ),
            "security_triggers": (
                [
                    t.get("rule", "?")
                    for t in state.policy_result.get("security", {}).get(
                        "rule_triggers", []
                    )
                ]
                if state.policy_result
                else []
            ),
            "total_tokens": state.total_tokens,
            "artifact_dir": str(run_dir),
        }

        logger.info(
            f"[{scenario_id}] {result['decision']} "
            f"(drift={result['drift_score']}, "
            f"findings={result['findings_count']}) "
            f"in {elapsed:.1f}s"
        )

        return result

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[{scenario_id}] FAILED: {e}")
        return {
            "scenario_id": scenario_id,
            "name": scenario["name"],
            "status": "failed",
            "error": str(e),
            "elapsed_seconds": round(elapsed, 1),
        }


def configure_executor(
    executor_name: str,
    executor_model: str,
    project_dir: str,
    timeout: int,
):
    """Configure the executor adapter."""
    if executor_name == "gemini":
        from codegate.adapters.gemini import GeminiCLIAdapter
        from codegate.agents.executor import set_executor_adapter

        adapter = GeminiCLIAdapter(
            model=executor_model or None,
            timeout=timeout,
            project_dir=project_dir or None,
        )
        set_executor_adapter(adapter)
        logger.info(
            "Using gemini executor "
            f"(model={executor_model or 'default'}, timeout={timeout}s)"
        )

    elif executor_name == "opencode":
        from codegate.adapters.opencode import OpenCodeAdapter
        from codegate.agents.executor import set_executor_adapter

        adapter = OpenCodeAdapter(
            model=executor_model or None,
            timeout=timeout,
            project_dir=project_dir or None,
        )
        set_executor_adapter(adapter)
        logger.info(
            "Using opencode executor "
            f"(model={executor_model or 'default'}, timeout={timeout}s)"
        )

    elif executor_name == "builtin_llm":
        logger.info("Using builtin_llm executor (simulated)")

    else:
        raise ValueError(f"Unknown executor: {executor_name}")


def main():
    parser = argparse.ArgumentParser(
        description="Run CodeGate V2 Frontend Client Benchmark"
    )
    parser.add_argument(
        "--executor",
        default="builtin_llm",
        choices=["builtin_llm", "gemini", "opencode"],
        help="Executor adapter to use",
    )
    parser.add_argument(
        "--executor-model",
        default="",
        help="Model for executor (e.g., gemini-2.5-pro)",
    )
    parser.add_argument(
        "--project-dir",
        default="",
        help="Project directory for real executors",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Executor timeout in seconds",
    )
    parser.add_argument(
        "--scenarios",
        default="",
        help="Comma-separated scenario IDs to run (default: all)",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output directory (default: test_results/<run_id>)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show scenarios without running",
    )
    parser.add_argument(
        "--env",
        default=".env",
        help="Path to .env file",
    )
    args = parser.parse_args()

    # Initialize config
    from codegate.config import get_config, init_config

    init_config(args.env)
    config = get_config()

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load scenarios
    filter_ids = (
        [s.strip() for s in args.scenarios.split(",")]
        if args.scenarios
        else None
    )
    scenarios, project_meta = load_scenarios(filter_ids=filter_ids)

    if not scenarios:
        print("No scenarios matched the filter.")
        sys.exit(1)

    # Dry run
    if args.dry_run:
        print(f"\n{'=' * 60}")
        print(f"DRY RUN — {len(scenarios)} scenario(s)")
        print(f"{'=' * 60}")
        for s in scenarios:
            print(f"  {s['id']:40s} {s['name']}")
            print(f"    request: {s['request'][:60].strip()}...")
            print(f"    risk: {s.get('risk_level', 'medium')}")
            print()
        sys.exit(0)

    # Create run directory
    run_id = datetime.now().strftime("v2_benchmark_%Y%m%d_%H%M%S")
    output_base = Path(args.output) if args.output else DEFAULT_OUTPUT
    run_dir = output_base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Configure executor
    configure_executor(args.executor, args.executor_model, args.project_dir, args.timeout)

    # Run scenarios
    results = []
    total_start = time.time()

    for scenario in scenarios:
        result = run_scenario(
            scenario=scenario,
            executor_name=args.executor,
            executor_model=args.executor_model,
            project_dir=args.project_dir,
            timeout=args.timeout,
            output_dir=run_dir,
        )
        results.append(result)

    total_elapsed = time.time() - total_start

    # Save manifest
    manifest = {
        "run_id": run_id,
        "benchmark": "v2_frontend_client",
        "executor": args.executor,
        "executor_model": args.executor_model or "default",
        "project": project_meta,
        "started_at": datetime.now().isoformat(),
        "total_elapsed_seconds": round(total_elapsed, 1),
        "total_scenarios": len(results),
        "completed": sum(1 for r in results if r["status"] == "completed"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
    }

    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Print summary
    print(f"\n{'=' * 70}")
    print(f"BENCHMARK COMPLETE — {run_id}")
    print(f"{'=' * 70}")
    print(f"{'Scenario':<40} {'Decision':<18} {'Findings':<10} {'Time'}")
    print("-" * 80)
    for r in results:
        if r["status"] == "failed":
            print(
                f"{r['scenario_id']:<40} {'FAILED':<18} "
                f"{'-':<10} {r['elapsed_seconds']}s"
            )
        else:
            print(
                f"{r['scenario_id']:<40} {r['decision']:<18} "
                f"{r['findings_count']:<10} {r['elapsed_seconds']}s"
            )

    completed = sum(1 for r in results if r["status"] == "completed")
    print(f"\nTotal: {completed}/{len(results)} completed, {total_elapsed:.0f}s elapsed")
    print(f"Results saved to: {run_dir}")
    print("\nTo summarize and validate against expected outcomes:")
    print(f"  .venv/bin/python benchmarks/v2_frontend_client/summarize.py {run_dir}")


if __name__ == "__main__":
    main()
