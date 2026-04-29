# Changelog

All notable changes to CodeGate will be documented in this file.

## [0.3.0] - 2026-04-29

### Added

- **Policy Loop Integration**
  - Policy Engine (Rule 1-11 + SEC-1~5) is now a LangGraph node (`policy_check`)
  - Policy-induced `revise_code` decisions auto-trigger executor re-run with
    violation feedback — no human intervention needed
  - Executor feedback now includes deterministic policy violations section

- **Codex CLI Adapter**
  - Added `codegate run --executor codex` support for OpenAI Codex CLI
  - Supports `codex exec` headless mode with `--full-auto`
  - Full evidence pipeline: files_content, baseline_content, validation_result
  - Added 18 mock-based unit tests (`tests/test_codex_adapter.py`)

- **Shared File Detection Utilities**
  - Extracted `adapters/_file_detection.py` from the Gemini/OpenCode pattern
  - Shared: snapshot_files, detect_git_changes, run_validation, path filtering
  - Used by Codex and ready for future adapter consolidation

- **Public Benchmark Fixture**
  - Added `benchmarks/fixtures/security_gate_demo/` with zero-LLM demo
  - 3 Vue Router fixtures: baseline, T5 (constrained), T6 (unconstrained)
  - `run_demo.py` — clone-and-run, no API keys needed
  - Demonstrates SEC-5: T5 approve vs T6 revise_code

- **V3 Security Gate Benchmark**
  - Added frozen benchmark report: `spec/benchmark-v3-security-gate-report.md`
  - Added reproducible harness under `benchmarks/v2_frontend_client/`
  - Added funding/application materials under `funding/`

- **Security Policy Gate (SEC-1~5)**
  - Deterministic auth/routing rules for guard deletion, global guest bypass,
    token weakening, scoped guest access, and protected route exposure
  - Merged security evidence into unified `policy_result.json`

- **Structural Extractors**
  - TypeScript/Vue: router guards, auth conditions, route meta, storage, imports
  - Rust: Tauri commands, function signatures, SQL pagination, imports

- **LLM JSON Robustness**
  - JSON parse retry for malformed model output
  - Persist malformed responses under `llm_parse_errors/`
  - 22 tests covering parse, repair, retry, artifact save, and failure paths

### Changed

- Bumped package version to `0.3.0`
- Policy override removed from CLI, benchmark.py, and benchmark runner
  (now integrated into pipeline graph — **breaking change** for external callers)
- Updated README: removed policy loop limitation, added Codex support

### Verified

- `pytest -q` — **142 passed**
- Security Gate Demo — T5 approve, T6 revise_code (3×SEC-5)
- V3 SEC-5 verify — 2 PASS, 0 WARN, 0 FAIL
- V3 full rerun — 5 PASS, 0 WARN, 0 FAIL

## [0.2.0] - 2026-04-27

### Added

- **交互式需求澄清 (Interactive Clarification)**
  - `codegate run` 不带 `--answers` 时，Spec Council 在 CLI 中交互式提问
  - 支持必答 (`[必答]`) 和可选 (`[可选]`) 问题分类
  - 必答问题不能跳过，可选问题可按回车跳过
  - 完成后展示问答摘要面板，确认后继续执行
  - 用户回答直接进入 contract prompt 影响契约生成

- **Pre-provided Answers 路径修复**
  - `--answers` 和 YAML answers 现在正确进入 contract prompt
  - 添加 `Pre-provided Clarification Answers` 节，标记为 hard constraints

- **Clarification 证据持久化**
  - 新增 `clarification_qa.json` artifact（questions、answers、mode）
  - `summary.json` 新增 `clarification_questions` 和 `clarification_answers` 字段
  - `clarification_mode` 字段使用 `Literal["none", "interactive", "pre_provided"]` 类型

### Fixed

- 修复交互式答案未进入 contract prompt 的 bug（questions 在第二次 pipeline 调用中丢失）
- 修复 `clarification_mode` 推断逻辑（从内容猜测改为显式字段）
- 修复 P2 审计证据链被意外简化回退的问题

### Verified

- `test_clarification_qa.py` — 5/5 通过
  - Interactive Q&A in contract prompt ✅
  - Pre-provided answers fallback ✅
  - No answers → no section ✅
  - State carries questions ✅
  - Literal mode validation ✅
- `test_audit_evidence.py` — structural_diff / raw_review_findings / suppressed_findings / invariant 全部通过
- Smoke test: `--answers` 路径真实 LLM 调用 → contract 正确反映 answers 约束

---

## [0.1.0] - 2026-04-25

### Added

- **核心治理管线** — Spec Council → Executor → Reviewer → Gatekeeper
- **A/B 评估** — `codegate ab` 单 case 自动化评估
- **批量评估** — `codegate ab-batch --cases <yaml>` 批量运行
- **审计报告** — 7 章节 `audit_report.md`（Clearance → Risk → Findings → A/B → Evidence → Reproducibility → Verdict）
- **批量报告** — 6+1 章节 `batch_report.md`（含 §7 Blocked Cases）
- **基线感知漂移检测** — structural pre-check + LLM review + post-filter 三层防御
- **Policy Engine** — 确定性规则覆盖（blocking findings → REVISE_CODE）
- **Ghost Pattern Suppression** — 防止 LLM 虚构不存在于 baseline 的 findings
- **证据持久化** — ArtifactStore 保存完整治理证据链
- **团队试用文档** — `TEAM_ALPHA_TRIAL_GUIDE.md`
