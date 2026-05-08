# Benchmark Report: v0.6.0 Real Executor Smoke Harness

**Date:** 2026-05-08
**CodeGate version:** v0.6.0-dev
**Baseline:** v0.5.0 (228 tests)

## Summary

| Metric | Value |
|--------|-------|
| Total tests | 271 |
| Passed | 271 |
| Failed | 0 |
| New tests added | 43 |
| Security gate demo | PASSED |
| Backend security demo | PASSED |
| Smoke harness (dry-run) | PASSED (2/2) |
| Smoke harness (codex) | Exit 2 — not yet implemented |
| Smoke harness (gemini) | Exit 2 — not yet implemented |

## New Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_execution_sandbox.py` | 15 | Sandbox isolation, worktree/copy strategies, diff/patch generation, timeout evidence, context manager lifecycle, **exception path preserves sandbox** |
| `tests/test_review_history.py` | 14 | Multi-round accumulation, non-overwrite, field structure, production-path auto-append via apply_policy_override |
| `tests/test_run_manifest.py` | 10 | Artifact indexing, sandbox/review pointers, null handling, **full relative path validation (all pointer fields)** |
| `tests/test_executor_sandbox_integration.py` | 5 | **run_executor integration**: sandbox creation, work_dir isolation, no project pollution, diff/patch in artifacts, failure evidence capture |

## Smoke Harness Results

### dry-run (no API key)

| Scenario | Status | Sandbox Strategy | Changed Files |
|----------|--------|-----------------|---------------|
| smoke_01_hello | PASSED | git_worktree | 1 |
| smoke_02_add | PASSED | git_worktree | 1 |

### Real executor mode

| Executor | Status | Notes |
|----------|--------|-------|
| `builtin_llm` | Supported | Requires LLM API key; runs full sandbox + artifact chain |
| `codex` | Exit 2 | Not yet implemented |
| `gemini` | Exit 2 | Not yet implemented |
| `opencode` | Exit 2 | Not yet implemented |

## Sandbox Pollution Check

Original fixture project files were NOT modified by sandbox operations. Git internal objects (`.git/objects/`) are shared across worktrees by design — this is expected git behavior and does not constitute pollution.

## Key Fixes in v0.6.0-dev

1. **Manifest full relative paths**: ALL manifest pointer fields (work_item, contract, execution_report, sandbox_report, review_history, policy_result, gate_decision, summary, candidate_diff, candidate_patch) use relative paths. `artifacts` dict values also equal relative keys. No absolute paths leak into manifest.
2. **Git change detection**: `_detect_git_changes` now combines tracked + untracked files in a single pass
3. **Copy change detection**: `_detect_copy_changes` now detects deleted files (in original but not in sandbox)
4. **Adapter cleanup**: GeminiCLIAdapter and OpenCodeAdapter no longer delete the work_dir when it's managed by an external ExecutionSandbox
5. **Review history entries**: Include `raw_review_findings` and `suppressed_findings` for full audit trail
6. **completed_iterations**: Uses `review_history` length when available (not just `iteration_history`)
7. **Smoke harness**: `--executor codex` returns exit code 2 (not implemented) instead of 0 (false success)
8. **Exception path**: `ExecutionSandbox.__exit__` marks `cleanup_status="preserved"` on exception (not left as "pending")
9. **Integration test**: `test_executor_sandbox_integration.py` proves run_executor creates sandbox, isolates changes, and produces artifacts

## Files Changed

### New Files (14)
- `src/codegate/execution/__init__.py`
- `src/codegate/execution/sandbox.py`
- `src/codegate/schemas/sandbox.py`
- `tests/test_execution_sandbox.py`
- `tests/test_review_history.py`
- `tests/test_run_manifest.py`
- `benchmarks/real_executor_smoke/run_smoke.py`
- `benchmarks/real_executor_smoke/scenarios.yaml`
- `benchmarks/real_executor_smoke/README.md`
- `docs/governed-execution-boundary.md`
- `spec/release-notes-v0.6.0.md`
- `spec/benchmark-v6-real-executor-smoke-report.md`

### Modified Files (7)
- `src/codegate/schemas/__init__.py` — added SandboxReport export
- `src/codegate/workflow/state.py` — added sandbox_report, review_history fields
- `src/codegate/store/artifact_store.py` — sandbox/review_history/manifest saving, relative diff/patch paths, fixed completed_iterations
- `src/codegate/execution/sandbox.py` — fixed git change detection (tracked+untracked), fixed copy change detection (deleted files)
- `src/codegate/policies/engine.py` — review_history entries include raw_review_findings and suppressed_findings
- `src/codegate/adapters/gemini.py` — fixed adapter-internal cleanup conflict with ExecutionSandbox
- `src/codegate/adapters/opencode.py` — fixed adapter-internal cleanup conflict with ExecutionSandbox
