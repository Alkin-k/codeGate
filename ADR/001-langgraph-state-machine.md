# ADR-001: 使用 LangGraph 作为状态机编排层

- **日期**: 2026-04-22
- **状态**: 已采纳
- **决策者**: 项目负责人

## 背景

需要一个支持状态驱动、条件分支、回退循环的编排框架来实现治理流水线。

## 考虑的方案

1. **LangGraph** — 状态图 + 条件边 + 持久化
2. **纯代码 while 循环** — 简单但缺乏可视化和回退语义
3. **Temporal / Prefect** — 过重，偏 infra workflow

## 决策

选择 LangGraph。原因：

- 状态驱动天然适合治理流水线（draft → approved → reviewing → gated）
- 条件边直接表达路由逻辑（revise_code → executor, escalate → END）
- 与 LangChain 生态兼容
- 原方案 §8.2 明确推荐

## 踩坑

- **conditional edge 函数不能修改 state**（ADR-003）
- **invoke() 返回 dict 需要手动重建嵌套 Pydantic 模型**
- Python 3.9 下 union type 语法不兼容 LangGraph 内部的 `get_type_hints()`

## 结论

LangGraph 适合做 MVP 骨架，但长期需要关注其 state 序列化边界问题。
