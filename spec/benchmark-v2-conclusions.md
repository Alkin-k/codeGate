# Benchmark V2 测试结论

> 测试日期: 2026-04-23
> 模型: deepseek/deepseek-chat
> Executor: builtin_llm（模拟）
> 版本: V2.1（gate 语义收紧后）

## 版本说明

V2 经历了两个阶段：
- **V2.0**（修复前）：gate 偏松，5/5 approve，case_5 存在误放行
- **V2.1**（修复后）：收紧 policy engine + reviewer prompt，case_3/4 首轮被正确拦截

本文档记录 V2.1 的最终数据。

## V2.1 测试结果

| Case | Risk | Total | Overhead | Exec | Decision | Drift | Coverage | Iter |
|------|------|-------|----------|------|----------|-------|----------|------|
| ① Fibonacci (easy) | low | 12.9s | 10.2s | 2.7s | approve | 0 | 100 | 1 |
| ② Auth (medium) | medium | 17.4s | 14.2s | 3.1s | approve | 0 | 100 | 1 |
| ③ Cache (medium) | medium | 36.5s | 26.6s | 9.9s | approve | 0 | 100 | 2 |
| ④ Refactor (hard) | high | 70.6s | 21.3s | 49.3s | approve | 0 | 100 | 2 |
| ⑤ Migration (hard) | high | 17.6s | 12.4s | 5.2s | approve | 0 | 100 | 1 |

## V1 → V2.0 → V2.1 全链路对比

| 指标 | V1 | V2.0 | V2.1 |
|------|-----|------|------|
| 总耗时 | 1,519.2s | 219.5s | 154.9s |
| Approve 率 | 0/5 (全 escalate) | 5/5 (全 approve) | 5/5 (经修订后 approve) |
| 首轮 approve 率 | — | 4/5 | 3/5 |
| 首轮被拦截 | — | 1/5 (case_2) | 2/5 (case_3, case_4) |
| 平均 governance overhead | — (未分离) | 20.6s | 16.9s |
| 总 governance tokens | — (未分离) | 36,108 | 37,130 |
| Case 3 drift (首轮) | 75 | 10 | 14 → 0 (修订后) |
| Case 4 drift (首轮) | 50 | 10 | 43 → 0 (修订后) |

## V2.0 → V2.1 修复内容

### Gate 语义收紧（ADR-007）

1. **Policy Engine 新增 Rule 6/7/8**：
   - Rule 6: unresolved_items > 0 → 拒绝 approve
   - Rule 7: findings 引用 assumed_defaults 且 P0/P1 → 拒绝 approve
   - Rule 8: high-risk + ≥2 P0/P1 findings → 强制 escalate

2. **Reviewer Prompt 加强**：
   - 新增 "§7. Assumed Defaults Compliance" 审计维度
   - assumed_defaults 违规 P1+ → `blocking: true`
   - drift_score 计算纳入 assumed_defaults 违规
   - coverage_score 对 partial compliance 更严格

3. **Gatekeeper Prompt 升级**：
   - 输入新增 risk_level 字段
   - Hard Policy Rules 反映新规则

### risk_level 实质化（ADR-008）

- high-risk: max_drift=15, min_coverage=85, ≥2 P1+ → escalate
- medium/low: 保持原阈值（drift≤30, coverage≥70）

## V2.0 的核心教训

### 3.9 Reviewer 给分不遵循自己的公式

**问题**：Reviewer prompt 明确写了 `drift_score = (unmet_criteria / total_criteria) × 100`，
但 Case 5 的 reviewer 在发现"缺少 roles 表"的同时给了 `drift=10, coverage=100`。
**原因**：LLM 倾向于给"感觉上差不多"的分数，而不是严格执行公式。
**修复**：prompt 中增加更明确的计算指导 + assumed_defaults 纳入计算基数。

### 3.10 100% approve 不是好事

**问题**：V2.0 的 5/5 approve 掩盖了 gate 偏松的问题。
**教训**：治理产品的核心价值是"拦截"。如果什么都放行，就和没有治理一样。
**修复**：收紧 policy engine，确保低质量实现会被拦截。

### 3.11 assumed_defaults 是治理盲区

**问题**：`assumed_defaults`、`required_tests`、`rollback_conditions` 在合同中定义了，
但 Policy Engine 没有任何规则检查它们。它们是"死字段"。
**修复**：Rule 7 检查 assumed_defaults 违规；未来可增加 required_tests 检查。

### 3.12 risk_level 不能只是展示字段

**问题**：`risk_level` 在 state 中流转但不影响任何行为。
**修复**：Rule 2/3 使用 risk_level 动态选择阈值，Rule 8 仅对 high-risk 生效。

## 还没证明的事

- Executor 仍是模拟的 `BuiltinLLMExecutor`，不产出真实 patch
- 没有 "with vs without governance" 的公平 A/B 对比
- 拦截效果依赖 LLM 行为的随机性（同一 case 多次跑可能结果不同）
- `required_tests` 和 `rollback_conditions` 仍未进入 deterministic policy

## 下一步方向

1. 接真实 executor adapter（Claude Code / Codex）
2. 在 3 个真实 repo 或 20 个真实任务上重跑
3. 做公平 A/B：同一执行器、同一任务集，比较 with/without CodeGate
4. 打出一个"它确实拦住了错误实现"的 showcase
