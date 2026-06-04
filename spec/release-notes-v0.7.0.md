# CodeGate v0.7.0 — Release Notes

**Theme:** Governance Contract Runtime

> v0.6 put the executor inside a governance boundary.
> v0.7 turns the evidence that boundary produces into **durable, queryable, replayable runtime assets.**

## What changed in one line

CodeGate now produces **durable, queryable, replayable governance run records** — each run has a stable `run_id`, an immutable artifact bundle, a single machine-readable verdict, and CLI commands to list/show/diff/replay them.

## New Features

### Stable Run Identity (`src/codegate/schemas/run.py`)

Every governance run now has a stable `run_id` (format `run_YYYYMMDD_HHMMSS_<shortid>_<rand>`) that is **distinct from the work_item id**. The trailing random suffix guarantees uniqueness even for two saves of the same work item within the same second, so re-running the same work item never overwrites prior evidence.

- `RunMetadata` — immutable identity & context: `run_id`, `work_item_id`, `codegate_version`, `started_at`/`completed_at`, `project_dir`, `executor_name`, `sandbox_strategy`, `git_base_ref`/`git_head_ref`, `status`.
- `generate_run_id(work_item_id)` — sortable, collision-resistant id; never equal to the work_item id.
- Artifacts now live under `artifacts/runs/{run_id}/...`. Legacy `artifacts/{work_item_id}/...` runs remain readable.

### Governance Verdict (`src/codegate/schemas/verdict.py`)

A single `verdict.json` per run captures the final decision so consumers no longer stitch together `gate_decision.json` + `summary.json` + `policy_result.json`.

- `GovernanceVerdict` — `final_decision`, `approved`, `requires_human`, `risk_level`, executor/sandbox context, `changed_files_count`, `blocking_findings_count`, `policy_violations_count`, `completed_iterations`, `reasons`, `next_action`.
- `VerdictEvidence` — relative-path-or-None pointers to the manifest, contract, sandbox report, candidate diff, review history, gate decision, and policy result.

### Run Index (`artifacts/run_index.json`)

`save_run()` updates a global, queryable index after every run.

- Entries are keyed by `run_id`, so multiple runs of the same work item are **separate records** (no overwrite).
- All pointers are relative (`runs/{run_id}` / `runs/{run_id}/verdict.json`).
- Index updates are **best-effort**: a corrupt or unwritable index can never damage the run artifact it describes.

### `codegate runs` CLI group (`src/codegate/cli.py`)

```bash
codegate runs list            # list all runs with status/executor/sandbox
codegate runs show <run_id>   # render the verdict + metadata + evidence completeness
codegate runs diff <a> <b>    # compare two runs field-by-field
codegate runs replay <run_id> # reload artifacts & validate completeness (no LLM)
```

The `run` command now also prints the governance verdict summary and the `run_id` at the end.

### Replay-lite

`codegate runs replay` reloads a run **purely from artifacts** — it never re-invokes any LLM, executor, reviewer, or policy engine. It reports replay status, missing artifacts, the final verdict, and an **evidence completeness score** derived from the run manifest's referenced files (a full bundle scores `1.0`; deleting a referenced file such as `candidate.diff` surfaces as `missing` and lowers the score).

## New `ArtifactStore` API

- `save_run(state, run_id: str | None = None) -> Path`
- `generate_verdict(state, run_dir, metadata=None) -> GovernanceVerdict`
- `load_run(run_id) -> RunArtifactBundle`
- `list_run_metadata() -> list[RunMetadata]`
- `diff_runs(run_a, run_b) -> dict`
- `compute_completeness(run_dir) -> dict`

## Artifact Changes

New files in each run directory (`artifacts/runs/{run_id}/`):
- `run_metadata.json` — stable run identity
- `verdict.json` — single machine-readable final verdict

New file at the store root:
- `run_index.json` — queryable index of all v0.7 runs

`run_manifest.json` now also indexes `run_metadata` and `verdict` (relative paths preserved).

## Breaking Changes

None for documented APIs. Artifacts for **new** runs move from `artifacts/{work_item_id}/` to `artifacts/runs/{run_id}/`; `save_run()` returns the new path, and every existing caller uses that returned path. Legacy artifact directories remain readable, and the `codegate history` command is unchanged.

## Migration

No migration needed. Old artifact directories are still loadable via `load_run()` (legacy fallback). New runtime fields default safely.

## Scope Clarification

v0.7 is a **runtime / artifact / CLI base layer**, not a product shell.

- **CodeGate v0.7 owns**: run identity, verdict schema, run index, artifact-level diff/replay, evidence completeness.
- **Explicit non-goals**: GitHub Action, dashboard, SARIF, full policy YAML, multi-agent orchestration, web UI, auto PR comments, new executor adapters. `diff`/`replay` are **artifact-level**, not semantic re-review.
