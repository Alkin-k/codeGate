# OpenAI Codex Open Source Fund — Form Answers

Official form:

https://openai.com/form/codex-open-source-fund/

Official program summary, as of 2026-04-29:

- OpenAI describes the fund as a $1M initiative for open-source projects using
  Codex CLI and OpenAI models.
- Applications are reviewed on an ongoing basis.
- Projects may receive grants up to $25,000 in API credits.

## Which open source project are you representing?

CodeGate

## Brief description of the project

CodeGate is an open-source governance and security gate for AI coding agents. It
turns natural-language coding requests into implementation contracts, delegates
the work to external AI coding agents, audits behavioral drift against the
approved contract, and applies deterministic policy/security rules before code
is approved.

The project is model-agnostic and executor-agnostic. It currently supports
Gemini CLI and OpenCode-style executors, and the next adapter target is Codex
CLI. CodeGate is designed to catch "silent behavioral drifts": AI-generated code
changes that look correct and may pass tests, but violate security or system
invariants.

In the frozen V3 benchmark, CodeGate correctly distinguishes safe route-scoped
guest access from unsafe protected-route public exposure in a real Vue 3 +
TypeScript + Tauri project. The deterministic Security Gate leaves auditable
`policy_result.json` evidence for every decision.

## GitHub repository

https://github.com/Alkin-k/codeGate

## How would you use API credits for your project?

We would use OpenAI API credits to make CodeGate a stronger open-source
governance layer for AI coding agents:

1. Build and validate a Codex CLI executor adapter so CodeGate can govern Codex
   coding runs directly.
2. Run continuous benchmark regressions across real-world coding scenarios,
   including frontend auth/routing, backend API authorization, token handling,
   and contract-drift cases.
3. Compare LLM reviewer behavior against deterministic policy gates to measure
   false positives, false negatives, and cost/latency tradeoffs.
4. Generate richer contract-review and security-review explanations for
   developer-facing audit reports.
5. Publish reproducible benchmark results and integration guides for open-source
   maintainers adopting AI coding agents.

We are requesting API credits rather than cash. A grant in the $10,000-$25,000
credit range would support 6-12 months of cross-model benchmark runs, Codex CLI
adapter validation, and public documentation.

## Anything else you would like OpenAI to know?

CodeGate is not another AI coding assistant. It is the governance layer around
AI coding assistants. As agents like Codex become faster and more autonomous,
open-source maintainers need deterministic controls that decide when generated
code is safe to approve.

The V3 benchmark is already reproducible:

```bash
.venv/bin/python benchmarks/v2_frontend_client/run.py --executor gemini
.venv/bin/python benchmarks/v2_frontend_client/summarize.py test_results/<run_id>
```

Current verification:

- 122 Python tests passing
- 6-scenario reproducible benchmark harness
- T5 constrained guest mode: approve
- T6 unconstrained guest mode: non-approve with SEC-5 protected-route exposure
- Apache-2.0 license

OpenAI credits would let us add Codex CLI as a first-class governed executor and
publish benchmark evidence for safer AI-assisted software development.
