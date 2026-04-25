# 🛡️ CodeGate

> An approval and quality gate layer for AI coding workflows.
> 面向 AI Coding 的方案批准、偏航审计与质量门禁层。

**Status: Alpha v0.1** — 可内测，非生产接入。

## The Problem

AI agents write code fast — but they often drift from the original intent.
They silently remove validation annotations, change method signatures, or bypass existing error handling paths.
Without governance, you get fast code that solves the wrong problem.

## How CodeGate Helps

CodeGate sits **between your requirements and your coding agents**:

```
Requirement → Spec Council → Contract → Executor → Reviewer → Gatekeeper → Decision
                  │                        │           │           │
              Clarify &              AI coding     Drift      approve /
              constrain              (OpenCode)   detection   revise_code /
                                                             escalate_to_human
```

1. 📋 **Spec Council** — Clarifies ambiguous requirements into an approved contract (goals, criteria, constraints)
2. 🤝 **Executor** — Passes the contract to any coding agent (currently OpenCode)
3. 🔍 **Reviewer** — Baseline-aware drift detection with structural pre-check + LLM review + post-filter
4. ✅ **Gatekeeper** — Makes approve/revise/escalate decision, with policy engine override
5. 📊 **A/B Evaluation** — Automated comparison of pure executor vs CodeGate-governed execution

## Key Capabilities

| Capability | Status |
|------------|--------|
| Contract-first governance | ✅ |
| Baseline-aware drift detection | ✅ |
| Low-noise approval (0 false positives in testing) | ✅ |
| Silent behavioral change interception | ✅ |
| Ghost pattern suppression (3-layer post-filter) | ✅ |
| Audit evidence persistence | ✅ |
| Automated A/B evaluation | ✅ |
| Batch A/B evaluation | ✅ |
| Auditor-ready evidence reports | ✅ |
| Severity × Disposition classification | ✅ |
| Interactive clarification | ❌ (backlog) |

## Quick Start

```bash
# Install
pip install -e .
cp .env.example .env
# Edit .env with your API key

# Run single A/B evaluation
codegate ab \
  --project /path/to/your/project \
  --input "your requirement" \
  --model kimi-for-coding/k2p6 \
  --case-name "case name"

# Run batch evaluation
codegate ab-batch --cases eval_cases/image2pdf_cases.yaml

# Run governance pipeline only
codegate run --input "your requirement" --executor opencode --executor-model kimi-for-coding/k2p6
```

## Team Alpha Trial

See [`docs/TEAM_ALPHA_TRIAL_GUIDE.md`](docs/TEAM_ALPHA_TRIAL_GUIDE.md) for the complete onboarding guide.

Quick onboarding:

1. Install CodeGate and configure `.env`
2. Run the built-in 4-case batch: `codegate ab-batch --cases eval_cases/image2pdf_cases.yaml`
3. Review `batch_report.md` — expect 3 approve + 1 revise_code (contract conflict)
4. Write your own cases for your project

## Project Structure

```
src/codegate/
├── agents/          # LLM agents: spec_council, executor, reviewer, gatekeeper
├── adapters/        # Executor adapters (OpenCode)
├── analysis/        # Structural pre-check (baseline diff)
├── eval/            # A/B runner + batch runner
├── policies/        # Policy engine (deterministic overrides)
├── prompts/         # LLM prompt templates
├── schemas/         # Pydantic models (contract, review, gate, execution)
├── store/           # Artifact persistence
├── workflow/        # LangGraph state machine
├── cli.py           # CLI entry point
└── config.py        # Configuration

docs/                # Team-facing documentation
eval_cases/          # A/B evaluation case definitions (YAML)
spec/                # Technical reports and test results
ADR/                 # Architecture Decision Records
tests/               # Fixture-based regression tests
scripts/             # Utility scripts
```

## Evidence Reports

Each `codegate ab` run produces:

- **`audit_report.md`** — 7-section auditor-ready report (Clearance → Risk → Findings → A/B → Evidence → Reproducibility → Verdict)
- **`ab_result.json`** — Complete raw data
- **`codegate_artifacts/`** — Full governance evidence chain (contract, findings, structural diff, gate decision)

Each `codegate ab-batch` run produces:

- **`batch_report.md`** — 6-section summary + §7 Blocked Cases (conditional)
- **`batch_summary.json`** — Structured aggregate data
- Per-case subdirectories with individual reports

## License

Apache-2.0
