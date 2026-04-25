# ADR-002: Policy Engine 使用 violations 而非 warnings 触发 override

- **日期**: 2026-04-23
- **状态**: 已采纳
- **决策者**: 项目负责人

## 背景

Policy Engine 有一条规则：达到最大迭代次数后，如果仍未 approve，应强制 escalate_to_human。

## 问题

最初实现将此规则写入 `result.warnings`，但 `apply_policy_override()` 只检查 `result.has_violations`。导致 Rule 4 成为死规则，永远不会触发 override。

## 考虑的方案

1. **改为 violations**（选项 A）— 语义更准确：到达 max iterations 未 approve 本身就是一个 violation
2. **让 override 也检查 warnings**（选项 B）— 会让所有 warning-level 的 override 都生效，语义不够严格

## 决策

选择方案 A。

```python
# Before (dead rule)
result.warnings.append(f"Max iterations ({state.max_iterations}) reached")

# After (active rule)
result.violations.append(f"Max iterations ({state.max_iterations}) reached")
```

## 验证

修复后 benchmark 中 Case 2、4、5 在 iteration=3/3 时正确触发：

```
Policy violations: ['Max iterations (3) reached without approval']
Policy override: revise_code → escalate_to_human
```

## 教训

- `warnings` 和 `violations` 的语义区分必须在设计阶段就明确定义
- 规则写入哪个级别，要看它是否影响最终决策路径
