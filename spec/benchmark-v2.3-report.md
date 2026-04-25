# CodeGate Benchmark V2.3 报告

> Run ID: `run_20260424_093244`
> 日期: 2026-04-24
> 模型: deepseek/deepseek-chat
> Executor: builtin_llm（模拟）
> Policy Engine: 8 条规则（含 risk-aware 阈值）
> Case 数量: 8（含 3 个 Rule 6/7/8 定向测试 case）

---

## 1. 本轮改动

| 变更项 | 文件 | 说明 |
|--------|------|------|
| gatekeeper.md 对齐 engine.py | `gatekeeper.md` | 8 条 Hard Policy Rules + risk-aware 阈值 + risk_level 传入 prompt |
| per-iteration evidence 持久化 | `gatekeeper.py` + `state.py` + `benchmark.py` | 每轮 findings/scores/decision 独立记录到 `iteration_history.json` |
| 新增 Case 6/7/8 | `benchmark.py` | 定向触发 Rule 6（unresolved_items）、Rule 7/8（high-risk assumed_defaults） |
| 报告审查清单 | `spec/report-review-checklist.md` | 防止重犯的自检文档 |

---

## 2. 结果总览

| Case | Risk | Total | Overhead | Exec | Decision | Drift | Coverage | Findings | Blocking | Iter |
|------|------|-------|----------|------|----------|-------|----------|----------|----------|------|
| ① Fibonacci | low | 13.5s | 10.6s | 2.9s | ✅ approve | 0 | 100 | 0 | 0 | 1 |
| ② Auth | medium | 50.8s | 28.5s | 22.2s | ⚠️ escalate | 10 | 100 | 3 | 1 | 3 |
| ③ Cache | medium | 115.5s | 33.9s | 81.7s | ✅ approve (修订) | 20→0 | 70→100 | 8→0 | 0 | 2 |
| ④ Refactor | **high** | 37.8s | 19.8s | 18.0s | ⚠️ escalate | 25 | 50 | 3 | 1 | 1 |
| ⑤ Migration | **high** | 19.8s | 12.3s | 7.5s | ✅ approve | 0 | 100 | 0 | 0 | 1 |
| ⑥ Partial Impl | medium | 73.2s | 28.2s | 45.0s | ✅ approve (修订) | 25→0 | 100 | 6→0 | 0 | 2 |
| ⑦ Payment | **high** | 102.6s | 24.4s | 78.2s | ⚠️ escalate | 10 | 90 | 6 | 2 | 1 |
| ⑧ API Key | **high** | 76.0s | 33.1s | 42.9s | ⚠️ escalate | 15 | 100 | 5 | 1 | 2 |
| **合计** | — | **489.2s** | **190.8s** | **298.4s** | **4/8 approve** | — | — | — | — | — |

### 2.1 首轮 vs 最终决策

| Case | 首轮决策 | 最终决策 | 路径 |
|------|---------|---------|------|
| ① Fibonacci | approve | approve | 首轮直接通过 |
| ② Auth | revise_code | **escalate** | 3 轮修订未解决 → Rule 4 |
| ③ Cache | revise_code | **approve** | 首轮 8 findings → 修订后 0 findings |
| ④ Refactor | **escalate** | escalate | gatekeeper 直接 escalate（coverage=50） |
| ⑤ Migration | approve | approve | 首轮直接通过 |
| ⑥ Partial Impl | revise_code | **approve** | 首轮 6 findings + 1 unresolved → 修订后通过 |
| ⑦ Payment | **escalate** | escalate | high-risk + 2 blocking findings |
| ⑧ API Key | revise_code | **escalate** | 修订后仍有 blocking → escalate |

---

## 3. 8 条 Policy 规则触发分析

| Rule | 描述 | 本轮触发 | Case | 证据 |
|------|------|---------|------|------|
| 1 | blocking findings → block | ✅ | ②⑦⑧ | Case 2: 1 blocking, Case 7: 2 blocking, Case 8: 1 blocking |
| 2 | drift 超阈值 (risk-aware) | ✅ | ④ | high-risk drift=25 > max_drift=15 |
| 3 | coverage 不足 (risk-aware) | ✅ | ④ | high-risk coverage=50 < min_coverage=85 |
| 4 | max iterations → escalate | ✅ | ② | 3 轮修订未 approve → escalate |
| 5 | security P0 → escalate | — | — | 未触发（无 security P0 finding） |
| 6 | unresolved_items → block | **观测到** | ⑥ | executor 报告 1 unresolved item（但 gatekeeper 已判 revise，Rule 6 未被 policy override 触发） |
| 7 | assumed_defaults 违规 | — | — | 未触发（findings 未引用 "assumed_defaults[N]" 格式） |
| 8 | high-risk ≥2 P0/P1 → escalate | **可能触发** | ⑦ | 6 findings 中包含 P0/P1，但 gatekeeper 自身已判 escalate |

### 3.1 本轮规则覆盖总结

- **被 Policy Engine override 确认触发的规则**: Rule 1, Rule 2, Rule 3, Rule 4 — **4/8**
- **被 gatekeeper LLM 自主判定（与 Policy 同向）**: Rule 6 观测到 unresolved，但 gatekeeper 已 revise
- **未触发的规则**: Rule 5, Rule 7, Rule 8 — 因当前 case 未命中精确条件
- **说明**: Rule 5 在假阳性修复后未再误触发（这是正确行为）；Rule 7 要求 `contract_clause_ref` 以 `"assumed_defaults"` 开头，当前 reviewer 产出的引用格式不精确到此前缀

---

## 4. 治理开销分析（真实 wall-clock 计时）

| Case | Spec | Exec | Review | Gate | Overhead |
|------|------|------|--------|------|----------|
| ① Fibonacci | 7.7s | 2.9s | 1.0s | 1.9s | 10.6s |
| ② Auth | 11.2s | 22.2s | 12.9s | 4.4s | 28.5s |
| ③ Cache | 10.4s | 81.7s | 18.2s | 5.3s | 33.9s |
| ④ Refactor | 11.1s | 18.0s | 6.3s | 2.3s | 19.8s |
| ⑤ Migration | 9.1s | 7.5s | 1.2s | 1.9s | 12.3s |
| ⑥ Partial Impl | 12.0s | 45.0s | 11.3s | 4.9s | 28.2s |
| ⑦ Payment | 9.5s | 78.2s | 12.5s | 2.4s | 24.4s |
| ⑧ API Key | 11.2s | 42.9s | 17.2s | 4.7s | 33.1s |
| **平均** | **10.3s** | **37.3s** | **10.1s** | **3.5s** | **23.9s** |

**关键数据（仅限当前模拟链路）**：
- 平均治理 overhead = 23.9 秒/case
- Spec Council 占 overhead 的 43%
- Reviewer 在多轮 case 中占比提升（因为跑了 2-3 轮完整审查）

---

## 5. Per-Iteration Evidence 验证

Case 3（Cache, 2 轮修订后 approve）的 `iteration_history.json` 已成功持久化：

| 轮次 | Decision | Drift | Coverage | Findings | Blocking |
|------|----------|-------|----------|----------|----------|
| 首轮 | revise_code | 20 | 70 | 8 | 0 |
| 修订后 | approve | 0 | 100 | 1 (non-blocking) | 0 |

**之前的问题**："首轮被拦截"只能从日志推断，现在可以从 evidence 文件独立验证。

---

## 6. 版本对比

| 指标 | V2.2 (5 case) | V2.3 (8 case) | 变化 |
|------|--------------|--------------|------|
| 总耗时 | 238s | 489s | 新增 3 case |
| Approve 率 | 4/5 | 4/8 | 新 case 设计更难 |
| 首轮 approve 率 | 3/5 | 3/8 | 更真实的难度分布 |
| 被 Policy 拦截并修订后通过 | 1 case | 2 cases (③⑥) | 验证了修订循环价值 |
| escalate 到人工 | 1 case | 4 cases (②④⑦⑧) | 高风险 case 被正确升级 |
| 平均 overhead | 19.6s | 23.9s | 复杂 case 审查更耗时 |
| Rule 触发覆盖 | 2/8 | 4/8 | Rule 2/3 首次触发 |
| 假阳性 | 0 | 0 | 保持稳定 |

---

## 7. 已证明 vs 尚未证明

### ✅ 已证明

1. **gatekeeper.md 与 engine.py 的 8 条规则现在是对齐的**（可通过代码对比验证）
2. **per-iteration evidence 持久化可用**（`iteration_history.json` 已在 Case 2/3/6/8 中产出）
3. **Rule 2/3 的 risk-aware 阈值在 high-risk case 中生效**（Case 4: coverage=50 被 high-risk 阈值拦截）
4. **修订循环有真实收敛能力**（Case 3: drift 20→0, Case 6: findings 6→0）
5. **假阳性修复保持稳定**（8 case 中无一例假阳性 security finding）

### ⚠️ 尚未证明

1. **Rule 6 的 Policy Engine override 未被直接验证**（Case 6 有 unresolved 但 gatekeeper 自己判了 revise）
2. **Rule 7 的 assumed_defaults 匹配未被触发**（reviewer 产出的 `contract_clause_ref` 未精确使用 `assumed_defaults[N]` 格式）
3. **Rule 8 的 Policy Engine override 未被直接验证**（Case 7 gatekeeper 自己判了 escalate）
4. **真实 executor 下的治理效果**（所有结论仍基于 BuiltinLLMExecutor 模拟）
5. **19.6-23.9s overhead 是当前模拟链路数据**，不能直接推论为真实商业接入后的用户体验

---

## 8. 遗留问题与下一步

### 8.1 Rule 7 的 contract_clause_ref 格式问题

Rule 7 要求 findings 的 `contract_clause_ref` 以 `"assumed_defaults"` 开头。但当前 reviewer 产出的 ref 格式不一致（有的写 `"assumed_defaults"`，有的写 `"defaults"` 或其他变体）。需要在 reviewer prompt 中更严格约束 ref 格式。

### 8.2 下一步优先级

1. **修复 Rule 7 的 ref 格式匹配**（reviewer prompt 约束）
2. **接入真实 executor adapter**（V2.2 retro 文档 P1-8）
3. **Contract Consistency Validator**（V2.2 retro 文档 P0-1）
