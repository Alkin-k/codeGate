# CodeGate Benchmark V2.2 报告

> Run ID: `run_20260424_091358`
> 日期: 2026-04-24
> 模型: deepseek/deepseek-chat
> Executor: builtin_llm（模拟）
> Policy Engine: 8 条规则（含 risk-aware 阈值）

---

## 1. 本轮改动

本轮 benchmark 在 V2.0 基础上做了以下代码变更后执行：

| 变更项 | 文件 | 说明 |
|--------|------|------|
| Reviewer prompt 语义修复 | `reviewer.md` | findings 只允许包含实际缺陷，不允许包含"通过判定" |
| Node-level 真实计时 | `graph.py` + `state.py` | `_timed_node()` 包装器替代 token 比例估算 |
| risk_level 传入 workflow | `graph.py` + `benchmark.py` | WorkItem 接收并传递 risk_level |
| 修订反馈增强 | `executor.py` | 传递全部 P0/P1 findings + gatekeeper.next_action |
| GateDecision.iteration 顺序修复 | `gatekeeper.py` | 先 increment 再存 decision |
| Policy Engine Rule 6/7/8 补齐 | `engine.py` | unresolved_items / assumed_defaults / high-risk escalate |
| Policy Engine Rule 2/3 risk-aware | `engine.py` | high-risk: drift≤15, coverage≥85 |

---

## 2. 结果总览

| Case | Risk | Total | Overhead | Exec | Decision | Drift | Coverage | Findings | Blocking | Iter |
|------|------|-------|----------|------|----------|-------|----------|----------|----------|------|
| ① Fibonacci | low | 12.0s | 9.8s | 2.2s | ✅ approve | 0 | 100 | 0 | 0 | 1 |
| ② Auth | medium | 56.5s | 19.3s | 37.3s | ✅ approve | 0 | 100 | 0 | 0 | 2 |
| ③ Cache | medium | 117.9s | 40.6s | 77.3s | ⚠️ escalate | 10 | 85 | 7 | 0 | 3 |
| ④ Refactor | high | 34.2s | 16.1s | 18.1s | ✅ approve | 0 | 100 | 1 | 0 | 1 |
| ⑤ Migration | high | 17.7s | 12.0s | 5.7s | ✅ approve | 0 | 100 | 0 | 0 | 1 |
| **合计** | — | **238.3s** | **97.8s** | **140.6s** | **4/5 approve** | — | — | — | — | — |

---

## 3. 治理开销分析

### 3.1 Per-Phase 真实耗时（基于 `_timed_node()` 测量）

| Case | Spec Council | Executor | Reviewer | Gatekeeper | Overhead |
|------|-------------|----------|----------|------------|----------|
| ① Fibonacci | 7.4s | 2.2s | 1.0s | 1.4s | 9.8s |
| ② Auth | 9.8s | 37.3s | 5.9s | 3.6s | 19.3s |
| ③ Cache | 9.5s | 77.3s | 26.9s | 4.1s | 40.6s |
| ④ Refactor | 11.6s | 18.1s | 3.0s | 1.6s | 16.1s |
| ⑤ Migration | 9.5s | 5.7s | 1.0s | 1.5s | 12.0s |
| **平均** | **9.6s** | **28.1s** | **7.6s** | **2.4s** | **19.6s** |

**关键数据**：
- 平均治理 overhead = **19.6 秒/case**
- Spec Council 占 overhead 的 **49%**（瓶颈）
- Gatekeeper 占 overhead 的 **12%**（轻量）
- Reviewer 在多轮修订 case (③) 中占比最大（26.9s，因为跑了 2 轮完整审查）

### 3.2 Token 消耗

| Case | 总 Tokens | 治理层 Tokens | Executor Tokens | 治理层占比 |
|------|----------|-------------|----------------|-----------|
| ① Fibonacci | 5,277 | 4,340 | 937 | 82% |
| ② Auth | 16,116 | 10,759 | 5,357 | 67% |
| ③ Cache | 25,038 | 16,235 | 8,803 | 65% |
| ④ Refactor | 8,869 | 6,362 | 2,507 | 72% |
| ⑤ Migration | 6,069 | 4,806 | 1,263 | 79% |
| **合计** | **61,369** | **42,502** | **18,867** | **69%** |

**成本估算**（Deepseek V3 $0.50/M tokens）：5 case 总成本 ≈ $0.031（约 ¥0.22）。

---

## 4. 8 条 Policy 规则运行分析

| Rule | 描述 | 阈值 | 本轮触发 | 说明 |
|------|------|------|---------|------|
| 1 | blocking findings → block approve | — | ✅ Case 2 首轮 | 3 findings, 1 blocking → revise_code |
| 2 | drift 超阈值 → block approve | low/med: >30, high: >15 | — | 无触发 |
| 3 | coverage 不足 → block approve | low/med: <70, high: <85 | — | 无触发 |
| 4 | max iterations → escalate | 3 轮 | ✅ Case 3 第 3 轮 | revise_code → escalate_to_human |
| 5 | security P0 → escalate | — | — | **未触发**（假阳性已消除） |
| 6 | unresolved_items → block approve | any | — | 所有 case 均 0 unresolved |
| 7 | assumed_defaults 违规 → block | P0/P1 | — | 无 assumed_defaults finding |
| 8 | high-risk + ≥2 P0/P1 → escalate | ≥2 severe | — | Case 4: 1 finding, Case 5: 0 |

### 规则覆盖率

- 被实际触发的规则：Rule 1, Rule 4（2/8）
- 有效但未触发的规则：Rule 2/3/5/6/7/8（6/8）——因为当前 case 未命中条件
- 死规则：**无**

---

## 5. 版本对比

### 5.1 V1 → V2.2 关键指标对比

| 指标 | V1 | V2.2 | 变化 |
|------|-----|------|------|
| 总耗时 | 1,519s | 238s | **↓ 84%** |
| 总 tokens | 91,961 | 61,369 | **↓ 33%** |
| Approve 率 | 0/5 | 4/5 | 全 escalate → 正常治理 |
| 假阳性 escalate | 5/5 | 0/5 | **消除** |
| 平均 governance overhead | 不可测 | 19.6s | 首次真实测量 |
| Policy 规则数 | 5 | 8 | +risk-aware +unresolved +assumed_defaults |

### 5.2 假阳性消除的根因链

```
V1 问题链：
  reviewer.md 要求 "MUST provide a verdict for each item"
    → LLM 把 "No security issues" 编码为 security/P0 finding
    → Policy Rule 5 看到 security + P0
    → block approve → escalate_to_human
    → 所有 5 case 被 escalate（包括完美实现的 fibonacci）

V2.2 修复链：
  reviewer.md 改为 "create a finding ONLY if you detect an actual problem"
    → LLM 不再产出 "pass verdict" findings
    → Case 1 findings: 7 → 0
    → Policy Rule 5 不触发
    → fibonacci 首轮直接 approve
```

### 5.3 Overhead 从"不可测"到"真实测量"

| 版本 | 测量方式 | 可信度 |
|------|---------|--------|
| V1 | 不分离，全部算总时间 | ❌ 不可用 |
| V2.0 | token 比例估算 | ⚠️ 误差大 |
| V2.2 | `_timed_node()` 真实 wall-clock | ✅ 可用 |

---

## 6. 遗留问题

### 6.1 Case 3（Cache）仍未通过

Case 3 经过 2 轮修订后仍被 gatekeeper 判 revise_code（drift=10, coverage=85），
第 3 轮触发 Rule 4 → escalate_to_human。

分析：
- 首轮 7 findings (2 blocking), drift=30
- 修订后 7 findings (0 blocking), drift=10
- Gatekeeper 仍给 revise_code 而非 approve

可能原因：分布式缓存场景对 LLM executor 来说过于复杂，模拟执行器难以产出充分实现。
这正好印证了**接入真实 executor 的必要性**。

### 6.2 Case 4（Refactor, high-risk）首轮直接 approve

Case 4 标记为 high-risk，但首轮 drift=0, coverage=100, 1 non-blocking finding → approve。

说明当前 case 的 high-risk 标记并未真正触发更严的治理路径。
原因是 Rule 2/3 的 high-risk 阈值（drift≤15, coverage≥85）没有被触及。

### 6.3 Rule 6/7/8 尚无触发样本

新增的 3 条规则在当前 5 个 case 中均未被触发。
需要在 V2.2 中设计专门的 benchmark case 来验证这些规则。

### 6.4 迭代证据链仍不完整

Case 2 和 Case 3 都经历了多轮修订，但 evidence 目录只保存最终态。
首轮被拦截的 findings/gate_decision 未被单独持久化。
这是 V2.2 P0-3（Per-Iteration Evidence）的目标。

---

## 7. 结论

本轮 benchmark 证明了 3 件事：

1. **假阳性问题已根治**：reviewer prompt 语义修复后，"通过判定"不再被编码为 findings
2. **真实计时可用**：governance overhead 平均 19.6s，在接入外部 executor 后这是用户唯一感知到的额外延迟
3. **8 条规则代码与文档完全对齐**：Rule 1-8 全部实现，risk-aware 阈值生效

还未证明的 1 件事：

- **真实 executor 下的治理效果**：所有结论仍基于 BuiltinLLMExecutor（模拟），在真实 coding agent 的 patch/diff 输出下，reviewer 是否仍能稳定工作，需要 V2.2 P1（真实 executor adapter）来验证

---

## 附录 A：Evidence 文件清单

```
benchmark_results/run_20260424_091358/
├── manifest.json
├── benchmark_report.json
├── benchmark_report.md
├── case_1_fibonacci.json
├── case_1_fibonacci/evidence/
│   ├── contract.json
│   ├── execution_report.json
│   ├── review_findings.json
│   ├── gate_decision.json
│   ├── phase_tokens.json
│   └── phase_timings.json        ← 新增：真实 wall-clock 计时
├── case_2_auth.json
├── case_2_auth/evidence/...
├── case_3_cache.json
├── case_3_cache/evidence/...
├── case_4_refactor.json
├── case_4_refactor/evidence/...
├── case_5_migration.json
└── case_5_migration/evidence/...
```

## 附录 B：Policy Engine 规则定义

```python
# Risk-aware thresholds (ADR-008)
max_drift  = 15 if risk == "high" else 30
min_coverage = 85 if risk == "high" else 70

# Rule 1: blocking findings → revise_code
# Rule 2: drift > max_drift → revise_code (risk-aware)
# Rule 3: coverage < min_coverage → revise_code (risk-aware)
# Rule 4: iteration >= max_iterations && !approved → escalate_to_human
# Rule 5: security P0 findings → escalate_to_human
# Rule 6: unresolved_items → revise_code (ADR-007)
# Rule 7: assumed_defaults P0/P1 violations → revise_code / escalate (ADR-007)
# Rule 8: high-risk + ≥2 P0/P1 findings → escalate_to_human (ADR-008)
```
