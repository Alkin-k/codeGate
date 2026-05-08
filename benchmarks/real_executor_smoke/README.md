# Real Executor Smoke Harness

Validates the CodeGate **Governed Execution Boundary** — sandbox isolation, artifact chain, and run manifest — using disposable fixture projects.

## Quick Start

```bash
# Dry-run (no API key needed, validates sandbox + artifacts)
.venv/bin/python benchmarks/real_executor_smoke/run_smoke.py --dry-run

# Full sandbox + artifact chain with BuiltinLLMExecutor (requires LLM API key)
.venv/bin/python benchmarks/real_executor_smoke/run_smoke.py --executor builtin_llm
```

## Executor Mode Status (v0.6.0)

| Mode | Flag | Status | Notes |
|------|------|--------|-------|
| Fixture smoke | `--dry-run` | Working | No API key needed; validates sandbox isolation + artifact chain |
| Built-in LLM | `--executor builtin_llm` | Working | Requires LLM API key; runs full sandbox + artifact chain |
| Codex CLI | `--executor codex` | Exit 2 | Not yet implemented in v0.6.0 |
| Gemini CLI | `--executor gemini` | Exit 2 | Not yet implemented in v0.6.0 |
| OpenCode CLI | `--executor opencode` | Exit 2 | Not yet implemented in v0.6.0 |

Real CLI executor smoke (codex/gemini/opencode) is deferred to v0.6.1 or when CI infra supports external CLI tools.

## What It Validates

1. **Sandbox Isolation** — executor changes are confined to the sandbox; original fixture project is not modified
2. **Change Detection** — diff/patch files are generated correctly for changed files
3. **Artifact Chain** — `sandbox_report.json` and `run_manifest.json` are produced with relative paths
4. **No Pollution** — original fixture directory remains unchanged after sandbox cleanup

## Scenarios

Scenarios are defined in `scenarios.yaml`. Each scenario specifies:
- A requirement (what to build)
- Context (project setup)
- Evaluation criteria (what to check)

## Architecture

```
benchmarks/real_executor_smoke/
├── run_smoke.py        # Main harness runner
├── scenarios.yaml      # Test scenarios
└── README.md           # This file
```

The harness creates disposable git-initialized projects in a temp directory, runs the executor inside an `ExecutionSandbox`, and verifies the artifact chain end-to-end.
