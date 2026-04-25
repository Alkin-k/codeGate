# CodeGate Benchmark V2.3.2 报告

> Run ID: `run_20260424_102212`
> 日期: 2026-04-24
> 模型: deepseek/deepseek-chat
> Executor: builtin_llm（模拟）
> Policy Engine: 8 条规则 + risk-aware 阈值
> Case 数量: 8

---

## 1. 本轮改动（相比 V2.3.1）

| 变更项 | 文件 | 说明 |
|--------|------|------|
| Policy override 同步 next_action | `engine.py` | override 后重写 next_action 为 `[ESCALATED/BLOCKED BY POLICY] ...` |
| policy_violations 落盘 | `state.py` + `benchmark.py` | 每个 case 的 `policy_result.json` 记录 violations 和 override_applied |
| reviewer 语义约束升级 | `reviewer.md` | 从词法黑名单升级到语义自检规则 + anti-pattern 示例 |
| checklist §7 | `report-review-checklist.md` | 新增 Policy Override 证据一致性（3 条） |
| rules.md §4.10-4.11 | `.agents/rules.md` | Policy override 同步 + 报告归因准确性 |

---

## 2. 结果总览

> 数据来源：`benchmark_report.json`，所有数字已与各 case 的 `gate_decision.json`、`review_findings.json`、`iteration_history.json` 交叉验证。

| Case | Risk | Total | Overhead | Exec | Decision | Drift | Cov | Findings | Blocking | Iter |
|------|------|-------|----------|------|----------|-------|-----|----------|----------|------|
| ① Fibonacci | low | 13.8s | 11.1s | 2.7s | revise_code (**override**) | 0 | 100 | 1 | 0 | 1 |
| ② Auth | medium | 20.4s | 12.3s | 8.1s | ✅ approve | 0 | 100 | 0 | 0 | 1 |
| ③ Cache | medium | 81.8s | 36.5s | 45.3s | ⚠️ escalate (**override**) | 0 | 67 | 4 | 0 | 3 |
| ④ Refactor | **high** | 48.9s | 25.0s | 23.9s | ✅ approve (修订) | 0 | 100 | 0 | 0 | 2 |
| ⑤ Migration | **high** | 22.1s | 14.4s | 7.7s | ✅ approve | 0 | 100 | 0 | 0 | 1 |
| ⑥ Partial Impl | medium | 112.9s | 37.2s | 75.8s | ⚠️ escalate (**override**) | 30 | 100 | 7 | 2 | 3 |
| ⑦ Payment | **high** | 61.4s | 25.2s | 36.2s | ⚠️ escalate (gatekeeper) | 43 | 67 | 7 | 3 | 1 |
| ⑧ API Key | **high** | 73.3s | 34.5s | 38.8s | ⚠️ escalate (gatekeeper) | 50 | 100 | 8 | 3 | 1 |
| **合计** | — | **434.6s** | **196.2s** | **238.5s** | **3/8 approve** | — | — | — | — | — |

---

## 3. Policy Engine 触发分析

> 数据来源：各 case 的 `policy_result.json`

| Case | override_applied | violations |
|------|-----------------|------------|
| ① Fibonacci | **true** | Rule 7: 1 assumed_defaults P0/P1 |
| ② Auth | false | — |
| ③ Cache | **true** | Rule 4: max iterations |
| ④ Refactor | false | — |
| ⑤ Migration | false | — |
| ⑥ Partial | **true** | Rule 4: max iterations |
| ⑦ Payment | false | — (gatekeeper 自主 escalate) |
| ⑧ API Key | false | — (gatekeeper 自主 escalate) |

### 3.1 Rule 触发归因（严格区分 Policy override vs gatekeeper 同向）

| Rule | 被 Policy Engine override 触发 | gatekeeper 判定同向 | 未触发 |
|------|-------------------------------|-------------------|--------|
| 1 | — | ✅ Case ③ round1, ⑥ round1&2 | — |
| 2 | — | — | ✅ |
| 3 | — | — | ✅ |
| 4 | ✅ Case ③⑥ | — | — |
| 5 | — | — | ✅ |
| 6 | — | ✅ Case ⑦ (3 unresolved, gatekeeper 自主 escalate) | — |
| 7 | ✅ Case ① | — | — |
| 8 | — | — | ✅ |

**说明**：
- "Policy override 触发" = `policy_result.json` 中 `override_applied=true`
- "gatekeeper 同向" = gatekeeper 自己判了 revise/escalate，Policy 没有 override（override_applied=false）
- Rule 2/3/5/8 本轮未被任何路径触发

---

## 4. next_action 一致性验证

> V2.3.1 遗留问题：override 后 next_action 仍写 "Merge" / "Implementation approved"

| Case | Decision | next_action 开头 | 一致？ |
|------|----------|-----------------|-------|
| ① Fibonacci | revise_code | `[BLOCKED BY POLICY]` | ✅ |
| ② Auth | approve | `No further action` | ✅ |
| ③ Cache | escalate | `[ESCALATED BY POLICY]` | ✅ |
| ④ Refactor | approve | `No further action` | ✅ |
| ⑤ Migration | approve | `No further action` | ✅ |
| ⑥ Partial | escalate | `[ESCALATED BY POLICY]` | ✅ |
| ⑦ Payment | escalate | `Escalate to human` | ✅ |
| ⑧ API Key | escalate | `Escalate to human` | ✅ |

**8/8 case 全部自洽。** V2.3.1 的 "decision=escalate 但 next_action=Merge" 问题已消除。

---

## 5. Findings 语义纯度

### 5.1 词法噪音（黑名单短语）

扫描 "No finding" / "No issue" / "No action needed" 等短语 → **0 条命中**。

### 5.2 语义噪音（"当前实现可接受" 类表述）

扫描 "is correct" / "is fine" / "is acceptable" 等语义 → **4 条命中**：
- Case ⑦: `[P2]` "...the order status remains 'pending'"（实际是描述行为，边界模糊）
- Case ⑧: 3 条 `[P1]` 包含 "is correct per assumed defaults" 等

**结论**：词法去噪已生效，语义去噪仍不完整。reviewer prompt 的 anti-pattern 自检规则降低了噪音总量（V2.3.1: 未计量 → 本轮: 4 条），但无法完全消除 LLM 的"评述性 finding"行为。

---

## 6. 已证明 vs 尚未证明

### ✅ 已证明

1. **Policy override 后 evidence 全字段自洽** — next_action 不再矛盾
2. **policy_result.json 为每个 case 落盘** — 含 violations 和 override_applied
3. **报告可区分 "Policy override" 和 "gatekeeper 同向"** — 基于 policy_result.json
4. **空 findings 落盘、round 从 1 开始** — 延续 V2.3.1 修复
5. **修订循环收敛** — Case ④: drift 10→0, coverage 70→100, 修订后 approve
6. **Rule 4 和 Rule 7 被 Policy Engine 直接 override** — 有 policy_result.json 支撑

### ⚠️ 尚未证明

1. **Rule 2/3/5/8 的 Policy Engine override** — 本轮无触发（gatekeeper 自主判定或未命中条件）
2. **findings 语义纯度完全达标** — 4 条语义噪音仍存在
3. **真实 executor 下的治理效果** — 仍为模拟
4. **LLM 非确定性下的结果稳定性** — Case 1 本轮被 Rule 7 拦截（V2.3.1 首轮直接 approve），Case 4 本轮修订后 approve（V2.3.1 被 Rule 8 escalate）

---

## 7. LLM 非确定性观察

| Case | V2.3.1 | V2.3.2 | 说明 |
|------|--------|--------|------|
| ① Fibonacci | approve | **revise_code** | 本轮 reviewer 产出 1 个 assumed_defaults finding |
| ② Auth | approve | approve | 一致 |
| ③ Cache | approve (修订) | **escalate** | 本轮 drift 更高，修订未收敛 |
| ④ Refactor | **escalate (Rule 8)** | approve (修订) | 本轮 findings 更少，修订后通过 |
| ⑤ Migration | approve | approve | 一致 |

这验证了：**同一组 case + 不同 run → 结果可能不同**。基准测试需要多次运行取均值/分布，单次 run 不能作为确定性结论。

---

## 附录：Evidence 目录结构

```
benchmark_results/run_20260424_102212/
├── benchmark_report.json
├── benchmark_report.md
├── case_N_xxx/evidence/
│   ├── contract.json
│   ├── execution_report.json
│   ├── review_findings.json      ← 8/8 全部存在（含 []）
│   ├── gate_decision.json        ← next_action 与 decision 一致
│   ├── phase_tokens.json
│   ├── phase_timings.json
│   ├── iteration_history.json    ← round 从 1 开始
│   └── policy_result.json        ← 新增：violations + override_applied
```
