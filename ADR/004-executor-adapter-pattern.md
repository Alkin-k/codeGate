# ADR-004: Executor 采用 Adapter 模式而非内建

- **日期**: 2026-04-23
- **状态**: 已采纳
- **决策者**: 项目负责人

## 背景

原方案 §6.2 明确定义 Executor 为外部组件：

> "将批准后的 contract 交给外部执行器，外部执行器可以是：Codex / Claude Code / OpenCode / OMO / OMC"

## 问题

MVP V1 的 executor 是一个内建 LLM prompt，导致：

1. Benchmark 测的是"4 个 LLM 串联 vs 1 个 LLM"，不是"治理层 + 真实执行器 vs 直接用执行器"
2. 治理层承担了不属于它的执行延迟（executor 占总时间 60-70%）
3. Token 成本 11.8x 中，大部分是 executor 消耗的，不是治理层的
4. 修订循环（3 轮）在 LLM executor 场景下几乎无法修复 drift

## 决策

引入 `ExecutorAdapter` 抽象基类：

```python
class ExecutorAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def execute(self, contract, context, feedback) -> ExecutionReport: ...
```

- `BuiltinLLMExecutor` 保留为测试用 adapter
- `executor.py` node 变为薄代理，只调 adapter + 存 state
- Benchmark V2 分别统计 governance overhead 和 executor time

## 下一步

1. 实现 OpenCode / OMO adapter（优先）
2. 实现 Claude Code adapter
3. 在真实 repo 上跑闭环

## 教训

- MVP 验证架构可行性时可以用模拟 executor
- 但 benchmark 度量必须把模拟器的耗时和治理层的耗时分开
- "一起度量"会得出错误的商业可行性结论
