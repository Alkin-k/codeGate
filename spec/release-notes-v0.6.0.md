# CodeGate v0.6.0 — Release Notes

**Theme:** Governed Execution Boundary

## New Features

### Implementation Sandbox (`src/codegate/execution/sandbox.py`)

External coding executors now run inside an isolated sandbox that prevents modification of the original project directory.

- **Git worktree strategy**: Preferred for git repositories. Creates a detached worktree and captures changes via `git diff` and `git format-patch`. Detects both tracked and untracked file changes.
- **Temp copy fallback**: For non-git projects. Copies the project to a temp directory and detects added, modified, and deleted files.
- **Auto strategy**: Tries git worktree first, falls back to copy.
- **Evidence preservation**: On timeout or failure, the sandbox is preserved for audit. On success, it is cleaned up automatically.
- **Context manager**: `ExecutionSandbox` supports `with` statement for clean lifecycle management.

### Review History (`GovernanceState.review_history`)

Each governance iteration now appends a structured entry to `review_history`, preserving all rounds of evidence:

- Review findings per iteration
- Raw review findings (LLM output before post-filter)
- Suppressed findings (false positives filtered by structural pre-check)
- Policy results per iteration
- Gate decisions per iteration

Previous iteration evidence is never overwritten. Entries are auto-appended by `apply_policy_override()`.

### Run Manifest (`run_manifest.json`)

`ArtifactStore.save_run()` now generates a `run_manifest.json` that indexes all artifacts produced by a run:

- Work item, contract, execution report
- Sandbox report (with diff/patch pointers)
- Review history
- Policy result, gate decision, summary
- `candidate_diff` and `candidate_patch` use relative paths within the run directory (not absolute sandbox paths)

`completed_iterations` in the summary now correctly reflects `review_history` length.

### Real Executor Smoke Harness (`benchmarks/real_executor_smoke/`)

A benchmark harness validates the sandbox + artifact chain end-to-end:

- `--dry-run` mode: No API key needed, uses disposable fixture projects to validate sandbox isolation and artifact chain
- `--executor builtin_llm`: Real executor mode using BuiltinLLMExecutor through the full sandbox + artifact chain (requires LLM API key)
- `--executor codex|gemini|opencode`: **Not yet implemented** — returns exit code 2

## Artifact Changes

New files in each run's artifact directory:
- `sandbox_report.json` — sandbox strategy, changed files, diff/patch content
- `review_history.json` — structured multi-round evidence
- `run_manifest.json` — index of all artifacts (relative paths)
- `candidate.diff` — unified diff of sandbox changes
- `candidate.patch` — git format-patch (worktree strategy only)

## Breaking Changes

None. All existing fields and behaviors are preserved.

## Migration

No migration needed. The new fields (`sandbox_report`, `review_history`) default to `None`/`[]` and are backward-compatible.

## Scope Clarification

CodeGate is a **governance layer**, not an execution orchestrator:

- **CodeGate owns**: sandbox isolation, review history, audit trail, policy enforcement, quality gate
- **CodeGate does NOT own**: multi-agent orchestration (OMO/OMC), code generation (Codex/Claude/Gemini/OpenCode), agent-to-agent communication, dashboard/UI
