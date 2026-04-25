# ADR-003: 状态修改只在 node 函数中执行

- **日期**: 2026-04-23
- **状态**: 已采纳
- **决策者**: 项目负责人

## 背景

LangGraph 的 conditional edge 函数（如 `_route_after_gate()`）用于决定下一步走哪个节点。

## 问题

最初在 `_route_after_gate()` 中做了 `state.iteration += 1`，期望在循环时递增迭代计数器。但实际运行时 iteration 永远停在初始值，导致 max_iterations 检查无效 → 无限循环。

## 根因

LangGraph 的 conditional edge 函数是**只读路由器**。即使在函数体内修改了 state 对象，这些修改不会被 LangGraph 的 state checkpoint 机制持久化。

```python
# ❌ 不会生效
def _route_after_gate(state):
    state.iteration += 1  # 这行修改会被丢弃
    if state.iteration >= state.max_iterations:
        return END
    ...

# ✅ 正确做法：在 node 函数中修改
def run_gatekeeper(state):
    state.iteration += 1  # 在 node 中修改会被持久化
    ...
```

## 决策

所有 state 修改必须在 node 函数中完成，conditional edge 函数只做读取和路由。

## 影响范围

- `graph.py`: 移除了 `_route_after_gate()` 中的 state mutation
- `gatekeeper.py`: 将 `state.iteration += 1` 移到 `run_gatekeeper()` 节点函数中
- `.agents/rules.md`: 记录为架构红线
