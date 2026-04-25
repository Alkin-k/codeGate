# ADR-005: Prompt 阈值必须与 Policy Engine 完全对齐

- **日期**: 2026-04-23
- **状态**: 已采纳
- **决策者**: 项目负责人

## 背景

Gatekeeper 的决策逻辑分为两层：

1. **LLM 层**（gatekeeper.md prompt）— 软引导，模型基于 prompt 做判断
2. **Policy 层**（engine.py）— 硬规则，程序化 override

## 问题

| 阈值 | gatekeeper.md | engine.py | 灰区 |
|------|--------------|-----------|------|
| approve: drift_max | ≤20 | ≤30 | 21-30 |
| approve: coverage_min | ≥80 | ≥70 | 70-79 |

灰区导致：
- LLM 判 revise_code（drift=25），但 Policy 不拦 → 矛盾
- 或 LLM 判 approve（coverage=75），但实际应该通过 → 不必要的 escalate

## 决策

1. **阈值统一为 Policy Engine 的值**（drift≤30, coverage≥70）
2. 在 prompt 中新增 **"Hard Policy Rules"** section，明确告知模型存在程序化 override
3. Policy Engine 是最终权威，Prompt 只是引导

```markdown
## Hard Policy Rules (enforced programmatically, cannot be overridden)
- NEVER approve with drift_score > 30
- NEVER approve with coverage_score < 70
- NEVER approve with unresolved P0 findings
- NEVER approve with security P0 findings
- After max iterations without approval → auto-escalate to human
```

## 原则

> **永远只维护一份阈值源**。Policy Engine 是 source of truth，Prompt 引用它。

## 影响

- `gatekeeper.md`: 阈值改为 70/30 + Hard Policy Rules section
- `engine.py`: 不变（已经是 70/30）
- `.agents/rules.md`: 记录为开发约定
