# Governed Execution Boundary

## Overview

CodeGate v0.6.0 introduces the **Governed Execution Boundary** — the ability to run external coding executors inside an auditable, isolated sandbox. This ensures that executor changes are confined, review evidence is preserved across iterations, and every run produces a machine-readable manifest.

## CodeGate's Role

**CodeGate is a governance layer, not an execution orchestrator.**

| Concern | Owner |
|---------|-------|
| Multi-agent orchestration | OMO, OMC, LangGraph workflows |
| Code generation | Codex, Claude Code, Gemini CLI, OpenCode |
| Governance & quality gate | **CodeGate** |
| Sandbox isolation | **CodeGate** |
| Review history & audit trail | **CodeGate** |
| Policy enforcement | **CodeGate** |

CodeGate does NOT:
- Replace or compete with OMO/OMC for multi-agent orchestration
- Directly generate code (it delegates to executor adapters)
- Manage agent-to-agent communication
- Provide a dashboard or UI

## Implementation Sandbox

The sandbox isolates executor changes from the original project directory.

### Strategies

| Strategy | When | How |
|----------|------|-----|
| `git_worktree` | Git repository (default) | Creates a detached worktree; changes captured via `git diff` |
| `temp_copy` | Non-git projects | Copies project to temp dir; changes detected by file comparison |
| `auto` | Default | Tries `git_worktree`, falls back to `temp_copy` |

### Lifecycle

```python
from codegate.execution.sandbox import ExecutionSandbox

with ExecutionSandbox(project_dir) as sandbox:
    # Executor runs in sandbox.sandbox_dir
    adapter.execute(contract, context, feedback)
# sandbox.report contains: changed_files, diff_path, patch_path
```

The original `project_dir` is never modified. On success, the sandbox is cleaned up. On failure/timeout, the sandbox is preserved for evidence.

## Review History

Each iteration of the governance loop (executor → reviewer → gatekeeper) appends a structured entry to `review_history` in `GovernanceState`. Previous entries are never overwritten.

```json
[
  {
    "iteration": 1,
    "timestamp": "2026-05-06T00:00:00Z",
    "review_findings": [...],
    "raw_review_findings": [...],
    "suppressed_findings": [...],
    "policy_result": {...},
    "gate_decision": {"decision": "revise_code", ...}
  },
  {
    "iteration": 2,
    "timestamp": "2026-05-06T00:01:00Z",
    "review_findings": [...],
    "raw_review_findings": [...],
    "suppressed_findings": [...],
    "policy_result": {...},
    "gate_decision": {"decision": "approve", ...}
  }
]
```

## Run Manifest

Every `save_run()` call produces a `run_manifest.json` that indexes all artifacts. All paths are **relative to the run directory** — no absolute filesystem paths:

```json
{
  "work_item_id": "...",
  "generated_at": "2026-05-06T00:00:00Z",
  "work_item": "work_item.json",
  "contract": "contract.json",
  "execution_report": "execution_report.json",
  "sandbox_report": "sandbox_report.json",
  "review_history": "review_history.json",
  "policy_result": "policy_result.json",
  "gate_decision": "gate_decision.json",
  "summary": "summary.json",
  "candidate_diff": "candidate.diff",
  "candidate_patch": null,
  "artifacts": {"work_item.json": "work_item.json", "contract.json": "contract.json", ...}
}
```

Missing files are `null`, not empty strings. `candidate_diff` / `candidate_patch` are only present when the sandbox produced diff/patch content.

## Executor Adapters

Executors are external tools that generate code. CodeGate wraps them in the sandbox boundary:

| Executor | Adapter | CLI |
|----------|---------|-----|
| OpenAI Codex | `CodexCLIAdapter` | `codex exec` |
| Google Gemini | `GeminiCLIAdapter` | `gemini -p` |
| OpenCode | `OpenCodeAdapter` | `opencode run` |
| Built-in LLM | `BuiltinLLMExecutor` | (testing only) |
