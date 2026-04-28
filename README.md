<div align="center">

# 🛡️ CodeGate

**The governance layer for AI coding agents.**
**AI 编码代理的治理层。**

[![Alpha v0.2](https://img.shields.io/badge/status-alpha%20v0.2-blue)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)]()

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
│   Gemini CLI)    │
└────────┬────────┘
         ▼
┌─────────────────┐
│  Reviewer        │ ← Baseline-aware drift detection
│  (3-layer filter)│   Structural pre-check → LLM review → Ghost pattern suppression
└────────┬────────┘
         ▼
┌─────────────────┐
│  Gatekeeper      │ ← approve / revise_code / escalate_to_human
│  (Policy Engine) │   8 deterministic rules with risk-aware thresholds
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

# Run governance pipeline (non-interactive, pre-provided answers)
codegate run --input "add filename validation" \
  --answers "support pdf,jpg,png|max 50MB" --executor opencode

# Run A/B evaluation (governed vs ungoverned)
codegate ab --project /path/to/project --input "your requirement" \
  --model kimi-for-coding/k2p6 --case-name "case_name"

# Run batch evaluation
codegate ab-batch --cases eval_cases/image2pdf_cases.yaml
```

## Evidence: Real Benchmark Results (V2.2)

> All numbers from actual benchmark runs — not estimates.

| Metric | Value | What It Means |
|--------|-------|---------------|
| Governance overhead | **19.6s avg** | ~20s extra per AI task for behavioral safety |
| False positives | **0 / 5 cases** | Zero noise — only real issues flagged |
| Approval rate | **4/5 approve, 1 blocked** | Blocks only when contract conflict detected |
| 5-case total cost | **$0.03 (¥0.22)** | Governance cost is negligible |
| V1 → V2.2 speed | **↓ 84%** | Continuous self-improvement |

### What Got Caught

In our 4-case real-project evaluation (image2pdf Java project):

- ✅ **3 cases approved** — AI output matched the contract
- 🔄 **1 case blocked** — AI silently removed `@Min(72)` annotation while adding validation; CodeGate caught the contract conflict and requested revision

## Key Capabilities

| Capability | Status |
|------------|--------|
| Contract-first governance (goals + criteria + constraints) | ✅ |
| Interactive requirement clarification (CLI) | ✅ |
| Baseline-aware drift detection (3-layer) | ✅ |
| Ghost pattern suppression (zero false positives) | ✅ |
| Policy engine with 8 deterministic rules | ✅ |
| Risk-aware thresholds (low/medium/high) | ✅ |
| Automated A/B evaluation (governed vs raw) | ✅ |
| Batch evaluation with aggregate reporting | ✅ |
| Auditor-ready evidence reports (7-section) | ✅ |
| Full audit evidence persistence | ✅ |

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
├── adapters/        # Executor adapters (OpenCode)
├── analysis/        # Structural pre-check (baseline diff)
├── eval/            # A/B runner + batch runner
├── policies/        # Policy engine (8 deterministic rules)
├── prompts/         # LLM prompt templates
├── schemas/         # Pydantic models (contract, review, gate, execution)
├── store/           # Artifact persistence
├── workflow/        # LangGraph state machine
├── cli.py           # CLI entry point
└── config.py        # Configuration

docs/                # Team-facing documentation
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

- **Alpha stage** — not production-ready, API may change
- **Executor support** — currently OpenCode and Gemini CLI (Cursor/Windsurf adapters planned)
- **LLM non-determinism** — each run may produce slightly different results
- **Governance overhead** — ~20s per task (the price of behavioral safety)

## License

Apache-2.0
