# CodeGate Budget & Resource Requirements

## Monthly Operating Costs

| Item | Purpose | Est. Monthly Cost |
|------|---------|-------------------|
| DeepSeek API | Spec Council + Reviewer + Gatekeeper (governance LLM calls) | $5-10 |
| Gemini API | Executor adapter (code generation) | $20-50 |
| OpenAI API | Alternative executor / evaluation | $20-50 |
| Anthropic API | Claude executor adapter (planned) | $20-50 |
| **Total API** | | **$65-160/month** |

### Notes on API Costs
- Governance overhead per scenario: ~7K-31K tokens (governance only, excluding executor)
- Executor tokens: 80K-1M per scenario (depends on complexity and iterations)
- DeepSeek is the default governance model at ~$0.14/M tokens — extremely cost-effective
- Monthly cost assumes 50-100 governance runs for benchmarking and testing

## Development Resources

| Role | Scope | Time |
|------|-------|------|
| Lead developer | Core pipeline, policy engine, security rules, benchmark harness | Ongoing |
| Security researcher | Expand SEC rules to backend/API, token management, RBAC bypass | Part-time |
| DevOps | CI/CD, automated benchmark runs, artifact storage | Part-time |

## Infrastructure

| Item | Purpose | Cost |
|------|---------|------|
| GitHub Actions | CI/CD, automated testing | Free (open source) |
| Artifact storage | Benchmark results, audit trails | Minimal (<1GB) |
| Documentation hosting | GitHub Pages or similar | Free |

## Grant Application Budget

### Small Grant ($1,000-5,000)
- 6-12 months of API credits for continuous benchmarking
- Cover development costs for expanding security rules
- Suitable for: OpenAI Codex OSS Fund, cybersecurity micro-grants

### Medium Grant ($5,000-25,000)
- All of the above
- Fund a security researcher for 3-6 months
- Expand executor adapter coverage (Cursor, Windsurf, Copilot)
- Build automated CI benchmark pipeline
- Suitable for: OpenAI Cybersecurity Grant, Anthropic Startup Program

### Large Partnership
- Ecosystem integration with model providers
- Joint evaluation/benchmarking program
- Co-development of model-specific governance rules
- Suitable for: GLM/Kimi ecosystem partnership, model evaluation resource exchange

## ROI Argument

| Investment | Return |
|------------|--------|
| $5/month (DeepSeek governance) | Catches silent behavioral drifts that cost hours to debug |
| 20s overhead per task | Auditable security evidence for every AI-generated change |
| 6-scenario benchmark | Reproducible proof that governance works |

The cost of governance is negligible compared to the cost of a single undetected security vulnerability in production.
