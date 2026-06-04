# Benchmark / Verification Report — v0.7.0 Governance Contract Runtime

**Scope:** v0.7 is a runtime / artifact / CLI base layer. This report records the
acceptance verification run for the Governance Contract Runtime. It is **not** a
model-quality benchmark — the demos below are deterministic governance fixtures.

## Environment

- CodeGate version: `0.7.0` (`src/codegate/__init__.py`, `pyproject.toml`)
- Python: 3.9 (`.venv`)
- Date of run: 2026-06-04

## 1. Full test suite

```
./.venv/bin/python -m pytest -q
→ 304 passed in ~6.9s
```

New v0.7 tests included:
- `tests/test_run_metadata.py` — RunMetadata defaults / JSON roundtrip / missing optionals / `generate_run_id` format, `!= work_item_id`, and same-second uniqueness
- `tests/test_governance_verdict.py` — verdict defaults / roundtrip / nested evidence pointers
- `tests/test_artifact_store_runtime.py` — new `runs/{run_id}` layout, no-overwrite with explicit and auto-generated run ids, verdict fields/evidence, manifest pointers, run_index update & resave, index-failure isolation, load/diff/completeness
- `tests/test_cli_runs.py` — list/diff/completeness helpers, replay-does-no-LLM guard, Typer CliRunner smoke for `runs list/show/replay`

v0.6 regression suites all green (sandbox, review history, run manifest, audit evidence, security gates).

## 2. Governance demos (deterministic fixtures)

### security_gate_demo
```
✅ Demo passed: T5 approved, T6 caught by security gate.
  T5 (safe / per-route guest mode)  → SEC violations: 0 → approve
  T6 (unsafe / global public)       → SEC violations: 3 → revise_code
```

### backend_security_demo
```
✅ All 10 scenarios passed!
  Blocking drift (T7–T12) and safe-refactor false-positive checks (T13–T16) all matched expected decisions.
```

### real_executor_smoke --dry-run (offline, no API key)
```
  Passed: 2 / Failed: 0
  [PASS] smoke_01_hello — git_worktree, 1 file changed, no pollution, 7 artifacts indexed
  [PASS] smoke_02_add   — git_worktree, 1 file changed, no pollution, 7 artifacts indexed
```

The smoke harness saves through `ArtifactStore.save_run()` and reads the returned
run directory — confirming the relocation to `runs/{run_id}` is transparent to
existing callers.

## 3. `codegate runs` CLI (end-to-end, real artifacts)

Two real runs were persisted to `./artifacts/runs/` and exercised through the CLI.

### runs list
```
Run ID                       Status     Executor     Sandbox        Started
run_20260604_120000_verif1   completed  codex        git_worktree   2026-06-04…
run_20260604_120100_verif2   completed  builtin_llm  —              2026-06-04…
```

### runs replay <run_id> (no LLM/executor)
```
Replay status: ✅ complete
Evidence completeness score: 100% (8/8)
No LLM/executor invoked — artifact-level replay only.
Final Verdict: REVISE_CODE | Approved: False | Changed files: 2
```

### runs diff <a> <b>
```
≠ final_decision      approve        revise_code
≠ approved            True           False
≠ executor_name       codex          builtin_llm
≠ sandbox_strategy    git_worktree   None
≠ changed_files_count 1              2
  completeness_score  1.0            1.0
```

### run_index.json
```
runs indexed: 2
  run_20260604_120000_verif1  approve      runs/run_20260604_120000_verif1
  run_20260604_120100_verif2  revise_code  runs/run_20260604_120100_verif2
```

### Legacy compatibility
`codegate history` is unchanged and continues to render the pre-v0.7
`artifacts/{work_item_id}/` runs, correctly ignoring the new `runs/` directory.

## Acceptance matrix

| Item | Standard | Result |
|---|---|---|
| run_id | unique per run; same work_item never overwrites | ✅ |
| run_metadata.json / verdict.json | written every run, fields complete | ✅ |
| run_index.json | auto-updated, listable; index failure can't break artifact | ✅ |
| runs show / diff | render verdict; compare two runs | ✅ |
| replay-lite | no LLM/executor; validates completeness score | ✅ |
| manifest | remains all-relative incl. new run_metadata/verdict pointers | ✅ |
| v0.6 regression | full pytest + sandbox/review_history/smoke green | ✅ |

## Promise boundary

> CodeGate now produces durable, queryable, replayable governance run records.

Explicitly **not** promised in v0.7: GitHub Action, dashboard, SARIF, full policy
YAML, multi-agent orchestration, web UI, enterprise audit integrations.
`diff`/`replay` are artifact-level, not semantic re-review.
