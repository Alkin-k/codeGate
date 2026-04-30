<div align="center">

# 🛡️ CodeGate

**The governance layer for AI coding agents.**
**AI 编码代理的治理层。**

[![Alpha v0.4](https://img.shields.io/badge/status-alpha%20v0.4-blue)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)]()

*AI agents write code fast — but they silently break things.*
*CodeGate catches the changes that tests miss.*

</div>

---

## The Problem

You ask an AI agent to "add filename validation." It does — correctly. But it also **silently removes** the existing `@Min(72)` annotation on another parameter. Tests pass. PR looks clean. The behavioral change is invisible until a user hits the removed boundary.

We call these **Silent Behavioral Drifts** — changes that pass all tests but violate system invariants. They are the hidden cost of "vibe coding."

## How CodeGate Helps

CodeGate sits **between your requirements and your coding agents**, enforcing contract-first governance:

```
Requirement
    │
    ▼
┌─────────────────┐
│  Spec Council    │ ← Clarifies ambiguous requirements into a contract
│  (goals/criteria/│   (interactive CLI or pre-provided answers)
│   constraints)   │
└────────┬────────┘
         ▼
┌─────────────────┐
│  Executor        │ ← Passes contract to any AI coding agent
│  (OpenCode /     │
│   Gemini/Codex)  │
└────────┬────────┘
         ▼
┌─────────────────┐
│  Reviewer        │ ← Baseline-aware drift detection
│  (3-layer filter)│   Structural pre-check → LLM review → Ghost pattern suppression
└────────┬────────┘
         ▼
┌─────────────────┐
│  Gatekeeper      │ ← LLM decision
└────────┬────────┘
         ▼
┌─────────────────┐
│  Policy Check    │ ← final approve / revise_code / escalate_to_human
│  (Rule 1-11)     │   deterministic rules + SEC-1~10 security gate
└─────────────────┘
```

## Quick Start

```bash
# Install
pip install git+https://github.com/Alkin-k/codeGate.git

# Initialize config
codegate init
# Edit .env with your API key

# Run governance pipeline — OpenCode executor (interactive)
codegate run --input "add filename validation to /api/convert" \
  --executor opencode --executor-model kimi-for-coding/k2p6

# Run governance pipeline — Gemini CLI executor
codegate run --input "add filename validation" \
  --executor gemini --project-dir /path/to/project

# Run governance pipeline — Codex CLI executor
codegate run --input "add filename validation" \
  --executor codex --project-dir /path/to/project

# Run governance pipeline (non-interactive, pre-provided answers)
codegate run --input "add filename validation" \
  --answers "support pdf,jpg,png|max 50MB" --executor opencode

# Run A/B evaluation (governed vs ungoverned)
codegate ab --project /path/to/project --input "your requirement" \
  --model kimi-for-coding/k2p6 --case-name "case_name"

# Run batch evaluation
codegate ab-batch --cases eval_cases/image2pdf_cases.yaml
```

## Evidence: Real Benchmark Results (V3 Security Gate)

> All numbers from actual benchmark runs — not estimates.

| Metric | Value | What It Means |
|--------|-------|---------------|
| Governance overhead | **~16-22s** | Extra governance time for contract/security review |
| False positives | **0 / 6 scenarios** | Safe scoped guest access is approved |
| False negatives | **0 / 6 scenarios** | Unsafe guest/public route exposure is blocked |
| Benchmark harness | **6 scenarios** | Reproducible T1-T6 frontend/client suite |
| Test suite | **201 tests passing** | Unit, integration, policy, extractor, Codex adapter, and LLM JSON robustness |

### What Got Caught

In the V3 frontend/client benchmark against a real Vue 3 + TypeScript + Tauri project:

- ✅ **T5 constrained guest mode approved** — route-scoped `meta.guest` access with preserved token checks
- ⚠️ **T6 unconstrained guest mode escalated** — protected workspace routes were exposed via `public: true`, caught by deterministic SEC-5 policy evidence
- 🔄 **Rule 7 contract drift blocks** — assumed-default boundary issues are revised even when the LLM gatekeeper says approve

## Evidence: Backend/API Security Gate (V4)

v0.4 adds deterministic backend security drift checks for Python/FastAPI, Java/Spring, and backend TypeScript APIs. The public fixture is zero-LLM, so it can be reproduced without API keys or executor setup.

```bash
.venv/bin/python benchmarks/fixtures/backend_security_demo/run_demo.py
```

| Scenario | Risk | Expected |
|----------|------|----------|
| T7 | Auth boundary preserved | approve |
| T8 | Auth boundary removed | block via SEC-6 |
| T9 | Tenant scope preserved | approve |
| T10 | Tenant scope removed | block via SEC-8 |
| T11 | User-provided role trusted | block via SEC-9 where implemented |
| T12 | CORS/cookie/security config relaxed | block via SEC-10 where implemented |

The demo validates both the final decision and the expected SEC rule trigger. This prevents a scenario from passing only because an unrelated rule happened to block it.

## Key Capabilities

| Capability | Status |
|------------|--------|
| Contract-first governance (goals + criteria + constraints) | ✅ |
| Interactive requirement clarification (CLI) | ✅ |
| Baseline-aware drift detection (3-layer) | ✅ |
| Ghost pattern suppression (zero false positives) | ✅ |
| Policy engine with 11 deterministic rules | ✅ |
| Security gate for frontend auth/routing risks (SEC-1~5) | ✅ |
| Backend/API security gate (SEC-6~10) | ✅ |
| TypeScript/Vue + Rust structural extractors | ✅ |
| Reproducible V2 frontend/client benchmark harness | ✅ |
| Risk-aware thresholds (low/medium/high) | ✅ |
| Automated A/B evaluation (governed vs raw) | ✅ |
| Batch evaluation with aggregate reporting | ✅ |
| Auditor-ready evidence reports (7-section) | ✅ |
| Full audit evidence persistence | ✅ |
| LLM JSON retry + malformed response artifacts | ✅ |

## Reproduce the V3 Benchmark

```bash
# Run all scenarios with Gemini CLI
.venv/bin/python benchmarks/v2_frontend_client/run.py --executor gemini

# Validate historical or freshly generated results
.venv/bin/python benchmarks/v2_frontend_client/summarize.py \
  test_results/v2_security_gate_sec5_verify_20260429
```

Read the frozen report:

- [`spec/benchmark-v3-security-gate-report.md`](spec/benchmark-v3-security-gate-report.md)
- [`spec/release-notes-v3-security-benchmark.md`](spec/release-notes-v3-security-benchmark.md)

## Reproduce the V4 Backend Demo

```bash
.venv/bin/python benchmarks/fixtures/backend_security_demo/run_demo.py
```

Read the v0.4 docs:

- [`spec/benchmark-v4-backend-security-gate-report.md`](spec/benchmark-v4-backend-security-gate-report.md)
- [`spec/release-notes-v0.4.0.md`](spec/release-notes-v0.4.0.md)
- [`docs/backend-security-gate-design.md`](docs/backend-security-gate-design.md)

## Evidence Reports

Each governance run produces a complete audit trail:

**Single run** (`codegate ab`):
- `audit_report.md` — 7-section report (Clearance → Risk → Findings → A/B → Evidence → Reproducibility → Verdict)
- `codegate_artifacts/` — Full evidence chain (contract, findings, structural diff, gate decision)

**Batch run** (`codegate ab-batch`):
- `batch_report.md` — Aggregate summary with blocked case analysis
- Per-case subdirectories with individual reports

## Project Structure

```
src/codegate/
├── agents/          # LLM agents: spec_council, executor, reviewer, gatekeeper
├── adapters/        # Executor adapters (OpenCode, Gemini CLI, Codex CLI)
├── analysis/        # Baseline diff + TS/Vue/Rust/Python structural extractors
├── eval/            # A/B runner + batch runner
├── policies/        # Policy engine + Security gate (SEC-1~10)
├── prompts/         # LLM prompt templates
├── schemas/         # Pydantic models (contract, review, gate, execution)
├── store/           # Artifact persistence
├── workflow/        # LangGraph state machine
├── cli.py           # CLI entry point
└── config.py        # Configuration

docs/                # Team-facing documentation
benchmarks/          # Reproducible benchmark harness
funding/             # Grant/resource application materials
eval_cases/          # A/B evaluation case definitions (YAML)
spec/                # Technical reports and benchmark results
ADR/                 # Architecture Decision Records
tests/               # Fixture-based regression tests
```

## Team Alpha Trial

See [`TEAM_ALPHA_TRIAL_GUIDE.md`](docs/TEAM_ALPHA_TRIAL_GUIDE.md) for the complete onboarding guide.

Quick path:
1. Install CodeGate and configure `.env`
2. Run the built-in batch: `codegate ab-batch --cases eval_cases/image2pdf_cases.yaml`
3. Review `batch_report.md` — expect 3 approve + 1 revise_code
4. Write your own cases for your project

## Honest Limitations

- **Alpha v0.4** — not production-ready, API may change
- **Executor support** — OpenCode, Gemini CLI, and Codex CLI (Cursor/Windsurf adapters planned)
- **LLM non-determinism** — each run may produce slightly different results
- **Governance overhead** — ~20s per task (the price of behavioral safety)
- **Security rules** — SEC-1~10 cover common frontend routing and backend API drift patterns, not a full SAST replacement

## License

Apache-2.0
