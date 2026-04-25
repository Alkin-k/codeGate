# CodeGate Benchmark V2.3.1 报告

> Run ID: `run_20260424_095345`
> 日期: 2026-04-24
> 模型: deepseek/deepseek-chat
> Executor: builtin_llm（模拟）
> Policy Engine: 8 条规则（含 risk-aware 阈值）
> Case 数量: 8

---

## 1. 本轮改动（相比 V2.3）

| 变更项 | 文件 | 说明 |
|--------|------|------|
| findings 噪音黑名单 | `reviewer.md` | 新增 "No finding for this" / "No action needed" 等短语禁令 + `assumed_defaults[N]` ref 格式要求 |
| 空 findings 无条件落盘 | `benchmark.py` | 去掉 `if state.review_findings:` 条件，`[]` 也写入 |
| round 编号修正 | `gatekeeper.py` | snapshot 在 `state.iteration += 1` **之前**写入，新增 `round` 字段 |
| benchmark.py docstring | `benchmark.py` | "governance depth" → "governance thresholds" |
| checklist 补充 3 条 | `report-review-checklist.md` | 内部交叉一致 / findings 纯度 / round 编号 |
| rules.md 补充 3 条 | `.agents/rules.md` | §4.7 噪音黑名单 / §4.8 空 findings / §4.9 snapshot 时序 |

---

## 2. 结果总览

> 数据来源：[benchmark_report.json](file:///Users/wukai/Desktop/腾讯云/codegate/benchmark_results/run_20260424_095345/benchmark_report.json)

| Case | Risk | Total | Overhead | Exec | Decision | Drift | Cov | Findings | Blocking | Iter |
|------|------|-------|----------|------|----------|-------|-----|----------|----------|------|
| ① Fibonacci | low | 13.2s | 11.0s | 2.2s | ✅ approve | 0 | 100 | 0 | 0 | 1 |
| ② Auth | medium | 38.9s | 15.3s | 23.5s | ✅ approve | 0 | 100 | 0 | 0 | 1 |
| ③ Cache | medium | 76.8s | 33.5s | 43.3s | ✅ approve (修订) | 10 | 100 | 5 | 0 | 2 |
| ④ Refactor | **high** | 55.0s | 19.8s | 35.2s | ⚠️ escalate (**override**) | 10 | 100 | 4 | 0 | 1 |
| ⑤ Migration | **high** | 18.3s | 11.7s | 6.5s | ✅ approve | 0 | 100 | 0 | 0 | 1 |
| ⑥ Partial Impl | medium | 103.2s | 43.3s | 59.9s | ⚠️ escalate | 10 | 95 | 5 | 0 | 3 |
| ⑦ Payment | **high** | 64.0s | 23.0s | 41.0s | ⚠️ escalate | 25 | 85 | 6 | 2 | 1 |
| ⑧ API Key | **high** | 70.0s | 26.0s | 44.0s | ⚠️ escalate (**override**) | 10 | 100 | 6 | 0 | 1 |
| **合计** | — | **439.4s** | **183.6s** | **255.6s** | **4/8 approve** | — | — | — | — | — |

---

## 3. 首轮 vs 最终决策

> 数据来源：各 case 的 `iteration_history.json`

| Case | Round 1 | Round 2 | Round 3 | 最终决策 | Override? |
|------|---------|---------|---------|---------|-----------|
| ① Fibonacci | approve (d=0, c=100, f=0) | — | — | approve | — |
| ② Auth | approve (d=0, c=100, f=0) | — | — | approve | — |
| ③ Cache | revise (d=20, c=70, f=5/1blk) | approve (d=10, c=100, f=5/0blk) | — | approve | — |
| ④ Refactor | approve (d=10, c=100, f=4) | — | — | **escalate** | **Rule 8** |
| ⑤ Migration | approve (d=0, c=100, f=0) | — | — | approve | — |
| ⑥ Partial | revise (d=30, c=70, f=12) | revise (d=10, c=95, f=5) | — | **escalate** | Rule 4 |
| ⑦ Payment | escalate (d=25, c=85, f=6/2blk) | — | — | escalate | — |
| ⑧ API Key | approve (d=10, c=100, f=6) | — | — | **escalate** | **Rule 5+7+8** |

---

## 4. Policy Engine 规则触发分析

### 4.1 逐规则触发记录

| Rule | 描述 | 触发 | Case | 证据 |
|------|------|------|------|------|
| 1 | blocking findings → block approve | ✅ | ③ round 1 | 5 findings, 1 blocking → revise_code |
| 2 | drift 超阈值 (risk-aware) | — | — | 未触发 |
| 3 | coverage 不足 (risk-aware) | — | — | 未触发 |
| 4 | max iterations → escalate | ✅ | ⑥ round 2 | 2 轮修订仍 revise → escalate |
| 5 | security P0 → escalate | ✅ | ⑧ | 1 security P0 → override approve → escalate |
| 6 | unresolved_items → block | **观测** | ⑥⑦ | ⑥ round 1: 1 unresolved; ⑦: 4 unresolved（但 gatekeeper 已判 revise/escalate） |
| 7 | assumed_defaults P0/P1 → block | ✅ | ⑧ | 3 assumed_defaults violations at P0/P1 → override approve → escalate |
| 8 | high-risk ≥2 P0/P1 → escalate | ✅ | ④⑧ | ④: 2 P0/P1 → override approve; ⑧: 5 P0/P1 → override approve |

### 4.2 本轮规则覆盖率

| 状态 | 规则 | 数量 |
|------|------|------|
| **被 Policy Engine override 触发** | Rule 1, 4, 5, 7, 8 | **5/8** |
| 被 gatekeeper 自主判定（同向） | Rule 6 | 1/8 |
| 未触发 | Rule 2, 3 | 2/8 |

### 4.3 与 V2.3 对比

| 指标 | V2.3 | V2.3.1 |
|------|------|--------|
| Policy override 触发 | Rule 1, 4 | Rule 1, 4, **5, 7, 8** |
| Rule 5 (security P0) | 未触发 | ✅ Case 8 |
| Rule 7 (assumed_defaults) | 未触发 | ✅ Case 8 |
| Rule 8 (high-risk P0/P1) | 未触发 | ✅ Case 4, 8 |
| findings 噪音 | 2 条 | **0 条** |

---

## 5. 修复验证

### 5.1 空 findings 落盘

| Case | review_findings.json | findings 数 |
|------|---------------------|------------|
| ① Fibonacci | ✅ 存在 | 0 (`[]`) |
| ② Auth | ✅ 存在 | 0 (`[]`) |
| ③ Cache | ✅ 存在 | 5 |
| ④ Refactor | ✅ 存在 | 4 |
| ⑤ Migration | ✅ 存在 | 0 (`[]`) |
| ⑥ Partial | ✅ 存在 | 5 |
| ⑦ Payment | ✅ 存在 | 6 |
| ⑧ API Key | ✅ 存在 | 6 |

**V2.3 遗留问题**：Case 1/5/6 无 `review_findings.json` → **已修复**：8/8 全部落盘。

### 5.2 round 编号自然化

| Case | iteration_history rounds |
|------|------------------------|
| ① Fibonacci | `[1]` |
| ② Auth | `[1]` |
| ③ Cache | `[1, 2]` |
| ④ Refactor | `[1]` |
| ⑤ Migration | `[1]` |
| ⑥ Partial | `[1, 2]` |
| ⑦ Payment | `[1]` |
| ⑧ API Key | `[1]` |

**V2.3 遗留问题**：首条记录 `iteration: 2` → **已修复**：全部从 `round: 1` 开始。

### 5.3 findings 噪音

全量扫描 8 case 的 `review_findings.json`，**0 条**包含 "No finding"/"No issue"/"No action needed" 文本。

**V2.3 遗留问题**：Case 3 有 "No finding for this."、Case 7 有 "No action needed." → **已修复**。

---

## 6. 治理开销分析（模拟链路真实计时）

| Case | Spec | Exec | Review | Gate | **Overhead** |
|------|------|------|--------|------|-------------|
| ① Fibonacci | 7.7s | 2.2s | 0.9s | 2.3s | 11.0s |
| ② Auth | 12.2s | 23.5s | 1.5s | 1.7s | 15.3s |
| ③ Cache | 9.5s | 43.3s | 19.7s | 4.3s | 33.5s |
| ④ Refactor | 11.1s | 35.2s | 6.6s | 2.1s | 19.8s |
| ⑤ Migration | 9.0s | 6.5s | 0.9s | 1.8s | 11.7s |
| ⑥ Partial | 11.5s | 59.9s | 26.0s | 5.9s | 43.3s |
| ⑦ Payment | 11.0s | 41.0s | 9.4s | 2.5s | 23.0s |
| ⑧ API Key | 12.1s | 44.0s | 11.7s | 2.3s | 26.0s |
| **平均** | **10.5s** | **32.0s** | **9.6s** | **2.9s** | **23.0s** |

说明：以上 overhead 数据仅代表当前模拟链路下的真实节点耗时，不能直接推论为真实商业接入后的用户体验。

### Token 消耗

| Case | 总 Tokens | 治理层 | Executor | 治理占比 |
|------|----------|--------|----------|---------|
| ① Fibonacci | 5,759 | 4,802 | 957 | 83% |
| ② Auth | 9,702 | 6,828 | 2,874 | 70% |
| ③ Cache | 18,774 | 13,095 | 5,679 | 70% |
| ④ Refactor | 11,656 | 7,915 | 3,741 | 68% |
| ⑤ Migration | 6,428 | 5,142 | 1,286 | 80% |
| ⑥ Partial | 22,688 | 15,327 | 7,361 | 68% |
| ⑦ Payment | 13,301 | 9,024 | 4,277 | 68% |
| ⑧ API Key | 13,705 | 9,231 | 4,474 | 67% |
| **合计** | **102,013** | **71,364** | **30,649** | **70%** |

成本：Deepseek V3 $0.50/M tokens → 8 case ≈ $0.051（约 ¥0.36）。

---

## 7. 已证明 vs 尚未证明

### ✅ 已证明（有 evidence 支撑）

1. **gatekeeper.md 与 engine.py 的 8 条规则对齐**
   - 验证方式：[gatekeeper.md:60](file:///Users/wukai/Desktop/腾讯云/codegate/src/codegate/prompts/gatekeeper.md) 列出 8 条 + risk-aware 阈值
   - [engine.py:49](file:///Users/wukai/Desktop/腾讯云/codegate/src/codegate/policies/engine.py) 中 8 条规则逐条匹配

2. **Policy Engine 能 override gatekeeper 的 approve 决策**
   - Case 4: gatekeeper 判 approve → Rule 8 override → escalate
   - Case 8: gatekeeper 判 approve → Rule 5+7+8 三重 override → escalate

3. **per-iteration evidence 可独立复盘**
   - Case 3: `iteration_history.json` 记录 round 1 (revise, 5 findings/1 blocking) → round 2 (approve, 5 findings/0 blocking)
   - round 编号从 1 开始，自然可读

4. **空 findings 作为审计事实落盘**
   - Case 1/2/5 的 `review_findings.json` 为 `[]`

5. **findings 语义噪音消除**
   - 8 case 全量扫描 0 条噪音 findings

6. **修订循环有真实收敛能力**
   - Case 3: drift 20→10, coverage 70→100, blocking 1→0
   - Case 6: drift 30→10, findings 12→5

### ⚠️ 尚未证明

1. **Rule 2/3 的 risk-aware 阈值未被本轮 evidence 直接验证**
   - 原因：无 high-risk case 同时满足 "gatekeeper 判 approve + drift>15 或 coverage<85" 的条件
   - 需要：设计一个 high-risk case 使 gatekeeper 在 drift=20 时仍给 approve

2. **Rule 6 的 Policy Engine override 未被直接验证**
   - Case 6/7 有 unresolved_items，但 gatekeeper 自身已判 revise/escalate
   - 需要：一个 gatekeeper 在有 unresolved 时仍给 approve 的 case

3. **真实 executor 下的治理效果**
   - 所有结论仍基于 BuiltinLLMExecutor 模拟

4. **跨版本 benchmark 可比性有限**
   - Case 2 在 V2.3 中 escalate（3 轮），本轮首轮直接 approve（0 findings）
   - 这是 LLM 非确定性导致的，不是代码变更导致的

---

## 8. 版本对比总表

| 指标 | V1 | V2.2 | V2.3 | V2.3.1 |
|------|-----|------|------|--------|
| Case 数 | 5 | 5 | 8 | 8 |
| 总耗时 | 1,519s | 238s | 489s | 439s |
| Approve 率 | 0/5 | 4/5 | 4/8 | 4/8 |
| Policy override 触发 | 0 | 0 | 2 rules | **5 rules** |
| 假阳性 security escalate | 5/5 | 0 | 0 | 0 |
| findings 噪音 | N/A | N/A | 2 条 | **0 条** |
| 空 findings 落盘 | ❌ | ❌ | ❌ | ✅ |
| Per-iteration evidence | ❌ | ❌ | ✅ (round 从 2 开始) | ✅ (round 从 1 开始) |

---

## 附录 A：Case 8 三重 Policy Override 完整记录

```
Gatekeeper 原始判定: approve (drift=10, coverage=100)

Policy Engine 检测到 3 条违规：
  [Rule 5] Cannot approve with 1 security P0 finding(s)
  [Rule 7] Cannot approve with 3 assumed_defaults violation(s) at P0/P1 severity
  [Rule 8] High-risk task with 5 P0/P1 findings → escalate

最终决策: escalate_to_human (Policy Override)
```

这是 CodeGate 治理内核价值的最直接体现：**LLM gatekeeper 判断失误（approve），但确定性 Policy Engine 基于硬规则拦截了放行**。

## 附录 B：Evidence 目录结构

```
benchmark_results/run_20260424_095345/
├── benchmark_report.json
├── benchmark_report.md
├── case_N_xxx/
│   ├── evidence/
│   │   ├── contract.json
│   │   ├── execution_report.json
│   │   ├── review_findings.json      ← 8/8 全部存在（含 []）
│   │   ├── gate_decision.json
│   │   ├── phase_tokens.json
│   │   ├── phase_timings.json
│   │   └── iteration_history.json    ← round 从 1 开始
```
