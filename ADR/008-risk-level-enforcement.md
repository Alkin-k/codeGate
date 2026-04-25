# ADR-008: risk_level 从展示字段变为策略字段

> 日期: 2026-04-23
> 状态: Accepted

## 上下文

V2 中 `risk_level`（low/medium/high）虽然在 WorkItem schema 中定义并流转，
但**没有任何 node 或 policy rule 读取它来改变行为**。

`low` 和 `high` 走完全相同的治理路径，这和 system.md 的声明矛盾。

## 决策

### 分级阈值

| 阈值 | low | medium | high |
|------|-----|--------|------|
| max_drift | 30 | 30 | **15** |
| min_coverage | 70 | 70 | **85** |
| P0/P1 auto-escalate | — | — | **≥2 findings** |

### 实现位置

- `policies/engine.py`：Rule 2/3 使用 `state.work_item.risk_level` 动态选阈值
- `policies/engine.py`：Rule 8 只对 high-risk 生效
- `prompts/gatekeeper.md`：Decision Matrix 中标注 risk-aware 阈值
- `agents/gatekeeper.py`：prompt 中传入 risk_level

### 未来扩展（暂不实现）

- low-risk 可跳过 reviewer 直接走快速路径
- high-risk 强制人工 approve（而非自动）
- risk_level 可由 Spec Council 自动评估，而非外部传入

## 后果

- Case 4（refactor, high-risk）首轮 drift=43 → 被 Rule 2 拦截（max_drift=15）
- high-risk 任务需要更高质量的实现才能通过
- low-risk 任务（如 fibonacci）不受影响
