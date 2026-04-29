# CodeGate V3 Security Benchmark Release Notes

Date: 2026-04-29

## Summary

This release turns the V2 frontend/client security work into a reproducible
benchmark package. CodeGate now has a frozen V3 report, runnable benchmark
harness, funding materials, and stronger LLM JSON parsing robustness.

## Highlights

- Added a frozen V3 benchmark report:
  - `spec/benchmark-v3-security-gate-report.md`
- Added a reproducible benchmark harness:
  - `benchmarks/v2_frontend_client/scenarios.yaml`
  - `benchmarks/v2_frontend_client/expected_outcomes.yaml`
  - `benchmarks/v2_frontend_client/run.py`
  - `benchmarks/v2_frontend_client/summarize.py`
  - `benchmarks/v2_frontend_client/README.md`
- Added funding/application materials:
  - `funding/one_pager.md`
  - `funding/benchmark_summary.md`
  - `funding/budget.md`
  - `funding/openai_codex_oss_application.md`
  - `funding/openai_cybersecurity_grant_application.md`
- Improved LLM JSON robustness:
  - retry once after parse failure
  - persist malformed raw responses
  - parse the earliest outer JSON block correctly

## Benchmark Evidence

Frozen evidence sets:

- Full T1-T6 rerun:
  - `test_results/v2_security_gate_full_rerun_20260429`
- Targeted T5/T6 SEC-5 verification:
  - `test_results/v2_security_gate_sec5_verify_20260429`

Key security result:

- T5 constrained guest access:
  - `approve`
  - no security violations
  - SEC-3 scoped guest advisory only
- T6 unconstrained guest access:
  - non-approve final decision
  - protected route public exposure captured by SEC-5

## Validation

Commands used:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python benchmarks/v2_frontend_client/summarize.py \
  test_results/v2_security_gate_sec5_verify_20260429
.venv/bin/python benchmarks/v2_frontend_client/summarize.py \
  test_results/v2_security_gate_full_rerun_20260429
```

Expected:

- Python tests pass.
- SEC-5 verify summary has no failures.
- Full rerun summary has no failures.

## Known Caveats

- Target project validation still reports `npm test` missing; CodeGate treats
  this as a warning-only validation gap.
- LLM executors are non-deterministic, so T6 may surface as SEC-3 global guest
  bypass or SEC-5 public route exposure. The benchmark accepts either security
  trigger as long as T6 is not approved.
- Backend/API write-guard policies are not yet covered by SEC-1~5.
