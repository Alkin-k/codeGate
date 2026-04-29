# OpenAI Codex Open Source Fund — CodeGate Application

## Project Name
**CodeGate** — The governance and security gate for AI coding agents

## GitHub Repository
https://github.com/Alkin-k/codeGate

## License
Apache 2.0

## One-Line Description
CodeGate is an open-source governance layer that sits between coding requirements and AI coding agents, enforcing contract-first development and deterministic security policies to prevent silent behavioral drifts.

## What does this project do?

CodeGate adds a governance layer to AI coding workflows. When a developer asks an AI agent to make code changes, CodeGate:

1. **Clarifies** the requirement into a structured implementation contract (goals, acceptance criteria, constraints)
2. **Executes** the contract through any AI coding agent (Gemini CLI, OpenCode, etc.)
3. **Reviews** the AI-generated code against the contract using structural diff and LLM-based analysis
4. **Gates** the changes through 11 deterministic policy rules and 5 security rules that cannot be bypassed by LLM hallucination

The key insight: as AI coding agents get faster, the governance gap widens. Tests catch functional bugs but miss behavioral invariant violations. CodeGate fills this gap.

## Why is this project important to the open-source community?

AI coding tools are becoming ubiquitous. Every major IDE now has AI code generation. But there is no standard governance layer:

- **Cursor, Copilot, Codex** generate code but don't verify behavioral invariants
- **Code review** is manual and doesn't scale with AI-generated volume
- **Tests** catch what they're written for but miss silent behavioral drifts

CodeGate provides the missing governance layer. It's model-agnostic (works with any executor) and produces auditable evidence for every decision.

### Real-World Impact

In our benchmark, an AI agent was asked to "add guest mode" to a Vue.js application. Without constraints, the agent made protected routes public — a security vulnerability that passed all existing tests. CodeGate's deterministic SEC-5 rule caught this automatically and blocked the change.

## How will you use the funding?

1. **API credits** — Continuous benchmarking and regression testing across multiple LLM providers
2. **Expand executor adapters** — Add support for Codex CLI, Cursor, and Windsurf as executors
3. **Expand security rules** — Backend API security, RBAC bypass detection, token management
4. **Community building** — Documentation, tutorials, contributor onboarding

## Technical Details

- **Language**: Python 3.9+
- **Dependencies**: LiteLLM (multi-provider LLM), LangGraph (state machine), Pydantic (schemas)
- **Architecture**: Modular pipeline with pluggable executor adapters
- **Testing**: 122 unit/integration tests, 6-scenario reproducible benchmark harness
- **Documentation**: English + Chinese

## Metrics

| Metric | Value |
|--------|-------|
| Stars | Growing (early stage) |
| Contributors | 1 (looking to grow) |
| Test suite | 122 tests passing |
| Benchmark scenarios | 6 (reproducible) |
| Security gate precision | 100% (0 false positives, 0 false negatives) |
| Governance overhead | ~20s per task |

## Relevant Links

- Benchmark Report: `spec/benchmark-v3-security-gate-report.md`
- Release Notes: `spec/release-notes-v3-security-benchmark.md`
- Architecture Decisions: `ADR/` directory (9 ADRs)
- Usage Guide: `docs/USAGE_GUIDE_ZH.md`
