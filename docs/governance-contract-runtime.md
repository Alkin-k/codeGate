# Governance Contract Runtime (v0.7)

## What this is

The Governance Contract Runtime turns a CodeGate run from a one-shot review into a **durable, queryable, replayable record**. Each run produces an immutable artifact bundle that can be listed, inspected, compared, and replayed long after the run finished — without re-invoking any LLM or executor.

> v0.6 put the executor inside a governance boundary.
> v0.7 makes the evidence that boundary produces an **auditable asset**.

This is a **runtime**, not a dashboard. There is no web UI, no server, no database — just JSON artifacts on disk and a CLI to query them.

## Run identity

Every run gets a stable `run_id` of the form:

```
run_YYYYMMDD_HHMMSS_<shortid>_<rand>
```

The leading timestamp keeps ids sortable, the work-item-derived `shortid` aids traceability, and the trailing random suffix guarantees uniqueness — two saves of the same work item within the same second still produce distinct ids.

The `run_id` is **deliberately not** the `work_item_id`. This is the whole point: re-running the same requirement produces a *new* record rather than overwriting the previous one, so you keep a history you can diff.

## On-disk layout

```
artifacts/
  run_index.json                      # queryable index of all runs
  runs/
    run_20260604_120000_ab12cd/
      run_metadata.json               # stable identity (run_id, executor, sandbox, git ref…)
      verdict.json                    # single machine-readable final verdict
      run_manifest.json               # relative-path index of every artifact
      work_item.json
      contract.json
      execution_report.json
      sandbox_report.json             # (if executor ran in a sandbox)
      candidate.diff                  # (if changes were captured)
      review_findings.json
      review_history.json             # (multi-round runs)
      gate_decision.json
      policy_result.json
      summary.json
```

Legacy `artifacts/{work_item_id}/...` runs from v0.6 and earlier remain readable.

## The verdict

`verdict.json` is the one file you read to know what happened:

| Field | Meaning |
|---|---|
| `final_decision` | `approve` / `revise_spec` / `revise_code` / `escalate_to_human` |
| `approved` | `true` iff decision is `approve` |
| `requires_human` | gate asked for human review (or escalated) |
| `risk_level` | work item risk |
| `executor_name`, `sandbox_strategy`, `sandbox_enabled` | execution context |
| `changed_files_count` | from sandbox evidence, else execution report |
| `blocking_findings_count`, `policy_violations_count`, `completed_iterations` | quantitative summary |
| `evidence` | relative pointers to manifest / contract / sandbox / diff / review history / gate / policy |
| `reasons`, `next_action` | human-readable rationale |

All `evidence` pointers are **relative** to the run directory, so a bundle stays valid after it is moved or archived.

## CLI

```bash
# List every run
codegate runs list

# Show one run's verdict, metadata, and evidence completeness
codegate runs show run_20260604_120000_ab12cd

# Compare two runs field-by-field (artifact-level, not semantic)
codegate runs diff run_20260604_120000_ab12cd run_20260605_090000_ef34gh

# Replay-lite: reload from artifacts and validate completeness (NO LLM/executor)
codegate runs replay run_20260604_120000_ab12cd
```

The legacy `codegate history` command is unchanged and continues to scan the old layout.

## Replay-lite & completeness

`runs replay` (and `ArtifactStore.load_run`) reload a run **purely from disk**. No model is called, no executor runs. The completeness score is:

```
score = present_required_artifacts / total_required_artifacts
```

where the required set is the union of a core baseline (`run_metadata.json`, `verdict.json`, `run_manifest.json`, `summary.json`, `work_item.json`) and **every non-null pointer recorded in `run_manifest.json`**. So if a referenced artifact (e.g. `candidate.diff`) is deleted, replay reports it as `missing` and the score drops below `1.0`. This makes the artifact bundle a genuinely auditable asset: you can prove, offline, that the evidence is intact.

## What this is NOT

- **Not** a semantic re-review. `diff` and `replay` compare and validate *artifacts*, they do not re-run the reviewer.
- **Not** a dashboard, GitHub Action, SARIF emitter, or web UI.
- **Not** a database — the index is a single JSON file, updated best-effort so it can never corrupt a run.

## Programmatic API

```python
from codegate.store.artifact_store import ArtifactStore

store = ArtifactStore()
run_dir = store.save_run(state)                 # returns artifacts/runs/{run_id}
metas   = store.list_run_metadata()             # list[RunMetadata]
bundle  = store.load_run("run_2026...")         # RunArtifactBundle (+ completeness)
diff    = store.diff_runs("run_a", "run_b")     # dict
```
