<div align="center">

# 🛡️ CodeGate

**The governance layer for AI coding agents.**
**AI 编码代理的治理层。**

[![CI](https://github.com/Alkin-k/codeGate/actions/workflows/ci.yml/badge.svg)](https://github.com/Alkin-k/codeGate/actions/workflows/ci.yml)
[![Alpha v0.5.0](https://img.shields.io/badge/status-alpha%20v0.5.0-blue)]()
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

## Evidence: Real Benchmark Results (V5 Evidence Quality)

> All numbers from actual benchmark runs — not estimates.

| Metric | Value | What It Means |
|--------|-------|---------------|
| Governance overhead | **~16-22s** | Extra governance time for contract/security review |
| Blocking false positives | **0 / 4 scenarios** | Common extractor-visible refactors remain non-blocking |
| Backend demo decisions | **6 / 6 matched** | Blocking and preserved backend scenarios (T7-T12) matched expected policy decisions |
| Benchmark harness | **10 scenarios** | Reproducible T7-T16 backend security suite |
| Evidence Quality | **SEC-1~10 Coverage** | SEC-1~10 rule triggers emit structured evidence; tests cover representative triggers. |


### What Got Caught (and What Didn't)

In the V5 backend security demo against realistic FastAPI/Java/Node code:

- ✅ **T13-T16 Common Refactors approved** — renaming `get_current_user` to `get_authenticated_user` or moving hardcoded CORS to `os.getenv` is recognized as non-blocking (advisory).
- ⚠️ **T8 Auth Removal escalated** — removing `Depends(get_current_user)` without replacement is blocked with SEC-6 evidence.
- ⚠️ **T11 User Role Trust revised** — trusting `role` from request body is blocked with SEC-9 evidence.

## Evidence: Backend/API Security Gate (V5)

v0.5 adds structured evidence and safe refactor support. The public fixture is zero-LLM, so it can be reproduced without API keys or executor setup.

```bash
.venv/bin/python benchmarks/fixtures/backend_security_demo/run_demo.py
```

| Scenario | Risk | Expected |
|----------|------|----------|
| T7-T9 | Auth/Tenant scope preserved | approve |
| T8 | Auth boundary removed | block via SEC-6 (escalate_to_human) |
| T10 | Tenant scope removed | block via SEC-8 (escalate_to_human) |
| T11 | User-provided role trusted | block via SEC-9 (revise_code) |
| T12 | Security config relaxed | block via SEC-10 (revise_code) |
| T13-T16 | Safe refactoring | approve (advisory warning) |

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

- **Alpha v0.5.0** — not production-ready, API may change
- **Executor support** — OpenCode, Gemini CLI, and Codex CLI (Cursor/Windsurf adapters planned)
- **LLM non-determinism** — each run may produce slightly different results
- **Governance overhead** — ~20s per task (the price of behavioral safety)
- **Security rules** — SEC-1~10 cover common frontend routing and backend API drift patterns, not a full SAST replacement

## License

Apache-2.0
