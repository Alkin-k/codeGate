# CodeGate v0.3.0 — Security Gate Benchmark

> **T5**: constrained guest access → approved.
> **T6**: unconstrained public route exposure → escalated to human.
> Same feature. Different safety contract. Different deterministic outcome.

## Highlights

### 🔒 Security Policy Gate (SEC-1~5) in the Loop

The deterministic Security Policy Engine is now a **first-class node** in the
LangGraph governance pipeline. Previously it ran after the pipeline in CLI;
now it participates in the routing loop. If SEC-1~5 detect a violation and
trigger `revise_code`, the executor will re-run with policy violation feedback
automatically — no human intervention needed.

**Pipeline flow:**
```
spec_council → executor → reviewer → gatekeeper → policy_check → route
                 ↑                                        │
                 └──────────── revise_code ────────────────┘
```

### 🤖 Codex CLI Adapter

CodeGate now supports **OpenAI Codex CLI** as an executor backend,
alongside Gemini CLI and OpenCode.

```bash
codegate run --executor codex --project-dir ./my-project \
  --input "add guest mode safely"
```

This makes CodeGate fully **executor-agnostic** — the governance layer
works identically regardless of which AI coding agent produces the code.
The adapter uses Codex's current non-interactive `codex exec --full-auto`
mode and captures the resulting git/file diff as audit evidence.

### 📊 Reproducible Benchmark Harness

A self-contained benchmark suite in `benchmarks/v2_frontend_client/` supports
one-command reproducibility:

```bash
.venv/bin/python benchmarks/v2_frontend_client/run.py --executor gemini
.venv/bin/python benchmarks/v2_frontend_client/summarize.py test_results/<run_id>
```

### 🎯 Public Demo Fixture (Zero LLM)

External reviewers can verify CodeGate's security gate without any API keys:

```bash
.venv/bin/python benchmarks/fixtures/security_gate_demo/run_demo.py
```

This runs the full SEC-1~5 pipeline on static Vue Router fixtures and
produces a T5 vs T6 comparison — proving the system works deterministically.

### 🛡️ LLM JSON Robustness

`call_llm_json()` now automatically retries on parse failure and saves
malformed raw responses as artifacts for debugging. This addresses the
edge case where LLM responses contained invalid JSON that crashed the
pipeline mid-run.

## Benchmark Results (Frozen Baseline)

| Scenario | Decision | Security Gate |
|----------|----------|---------------|
| T1: Frontend validation | approve | No SEC triggers |
| T2: IPC contract | approve | No SEC triggers |
| T3: Backend pagination | approve | No SEC triggers |
| T4: Error handling | approve | No SEC triggers |
| T5: Constrained guest | approve | SEC-3 advisory (scoped — safe) |
| T6: Unconstrained guest | **revise_code** | **SEC-5 violation** (3 routes exposed) |

- **0 false positives, 0 false negatives** across 6 scenarios
- Full report: [`spec/benchmark-v3-security-gate-report.md`](spec/benchmark-v3-security-gate-report.md)

## Test Suite

```
142 tests passed
```

Includes 22 new LLM JSON robustness tests and 18 Codex adapter tests (mock-based).

## Breaking Changes

- `apply_policy_override()` is no longer called externally by CLI or benchmark
  runners. If you have scripts that call it after `run_governance_pipeline()`,
  remove those calls — policy check now runs inside the pipeline automatically.

## Files Changed

### New Files
- `src/codegate/adapters/codex.py` — Codex CLI adapter
- `src/codegate/adapters/_file_detection.py` — Shared file detection utilities
- `tests/test_codex_adapter.py` — Codex adapter tests (18)
- `tests/test_llm_json_robustness.py` — JSON robustness tests (22)
- `benchmarks/fixtures/security_gate_demo/` — Public demo fixture
- `funding/` — Grant application materials

### Modified Files
- `src/codegate/workflow/graph.py` — Policy check as LangGraph node
- `src/codegate/agents/executor.py` — Policy violations in feedback
- `src/codegate/cli.py` — Codex executor support
- `src/codegate/llm.py` — JSON retry + artifact save
