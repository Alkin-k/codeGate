# Benchmark V1 测试结论

> 测试日期: 2026-04-23
> 模型: deepseek/deepseek-chat
> Executor: builtin_llm（模拟）
> 版本: V1（已归档，V2 取代）

## 测试矩阵

| Case | Baseline | Governance | Δ Score | Decision | Drift | Coverage | Iter |
|------|----------|-----------|---------|----------|-------|----------|------|
| ① Fibonacci (easy) | 100 | 100 | 0 | approve→escalate* | 14 | 100 | 1 |
| ② Auth (medium) | 95 | 95 | 0 | escalate | 20 | 95 | 3 |
| ③ Cache (medium) | 85 | 25 | -60 | escalate | 75 | 33 | 2 |
| ④ Refactor (hard) | 95 | 95 | 0 | escalate | 50 | 67 | 3 |
| ⑤ Migration (hard) | 95 | 85 | -10 | escalate | 20 | 100 | 3 |

> *Case 1: gatekeeper 判 approve（drift=14, coverage=100），但 Policy Engine 因 security P0 finding override 为 escalate

## 总成本

| 指标 | Baseline | Governance | 倍率 |
|------|----------|-----------|------|
| 总 tokens | 7,789 | 91,961 | **11.8x** |
| 总耗时 | 300.9s | 1,519.2s | **5.05x** |

## 问题分析

### 为什么倍率这么高

1. **Executor 是内建 LLM**：executor 占总时间 60-70%，这不是治理层的成本
2. **3 轮修订循环**：Case 2/4/5 都到了 max_iterations=3，每轮包含完整的 executor+review+gate
3. **内建 LLM executor 修订效果差**：LLM 重新生成一遍代码很难真正修复 drift，导致循环无效

### 不能从 V1 数据得出的结论

- ❌ "治理层增加 5x 延迟" — 治理层 overhead 没有被单独测量
- ❌ "治理层使 token 成本增加 12x" — 大部分 token 是 executor 消耗的
- ❌ "governance 比 baseline 差" — 对比不公平（4 个 LLM vs 1 个 LLM）

### 可以从 V1 数据得出的结论

- ✅ **状态机架构可行** — 5 个 case 全量跑通，无崩溃
- ✅ **drift 检测有效** — Case 3 被正确标记为高 drift（75），Case 4 被标记为中 drift（50）
- ✅ **Policy Engine override 有效** — Rule 4（max iterations）正确触发 3 次
- ✅ **审计链完整** — 25 个 evidence 文件正确落盘
- ✅ **Schema 设计稳定** — 所有 Pydantic 模型正确序列化/反序列化

## V2 改进方向

- 分离 governance overhead 和 executor time
- 引入 ExecutorAdapter 抽象
- 不再做 baseline vs governance 对比（因为 executor 不同）
- 增加 risk_level 字段
