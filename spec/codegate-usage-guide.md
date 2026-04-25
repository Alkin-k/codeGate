# CodeGate 快速使用指南

> 版本: V2.4 | opencode: 1.14.21

---

## 一键运行

只需替换 `<你的需求>` 即可执行治理 + 基准测试，结果输出到 `./benchmark_results/` 目录：

```bash
cd /Users/wukai/Desktop/腾讯云/codegate && \
source .venv/bin/activate && \
python -m codegate.benchmark \
  --cases=case_1_fibonacci \
  --executor=opencode \
  --executor-model=kimi-for-coding/k2p6
```

### 替换说明

| 需要替换的部分 | 说明 | 示例 |
|--------------|------|------|
| `--cases=` | 要跑的 case（或 `all` 跑全部） | `case_1_fibonacci`, `case_4_refactor`, `all` |
| `--executor-model=` | opencode 使用的模型 | `kimi-for-coding/k2p6`, `kimi-for-coding/k2p5` |

### 可用 Case 列表

| Case ID | 风险 | 描述 |
|---------|------|------|
| `case_1_fibonacci` | low | 简单 Fibonacci |
| `case_2_auth` | medium | 认证模块 |
| `case_3_cache` | medium | 缓存系统 |
| `case_4_refactor` | high | API 重构 |
| `case_5_migration` | high | 数据库迁移 |
| `case_6_partial_impl` | medium | 不完整实现 |
| `case_7_assumed_defaults` | high | 重度假设 |
| `case_8_security_critical` | high | 安全敏感 |

---

## 输出结构

运行完成后，结果在 `benchmark_results/run_YYYYMMDD_HHMMSS/` 下：

```
benchmark_results/run_20260424_110223/
├── benchmark_report.json       ← 汇总数据（JSON）
├── benchmark_report.md         ← 汇总报告（可读）
├── manifest.json               ← 运行配置
└── case_1_fibonacci/
    └── evidence/
        ├── contract.json       ← 规约合同
        ├── execution_report.json ← 执行报告（含真实代码）
        ├── review_findings.json  ← 审查发现
        ├── gate_decision.json    ← 门禁决策
        ├── policy_result.json    ← 策略引擎结果
        ├── phase_timings.json    ← 各阶段耗时
        └── iteration_history.json ← 迭代历史
```

---

## 常用命令模板

### 跑全部 8 个 Case

```bash
cd /Users/wukai/Desktop/腾讯云/codegate && \
source .venv/bin/activate && \
python -m codegate.benchmark \
  --cases=all \
  --executor=opencode \
  --executor-model=kimi-for-coding/k2p6
```

### 跑指定的几个 Case

```bash
cd /Users/wukai/Desktop/腾讯云/codegate && \
source .venv/bin/activate && \
python -m codegate.benchmark \
  --cases=case_4_refactor,case_8_security_critical \
  --executor=opencode \
  --executor-model=kimi-for-coding/k2p6
```

### 用内置模拟执行器跑（快速，无需 opencode）

```bash
cd /Users/wukai/Desktop/腾讯云/codegate && \
source .venv/bin/activate && \
python -m codegate.benchmark \
  --cases=all
```

### 单次治理运行（非 benchmark）

```bash
cd /Users/wukai/Desktop/腾讯云/codegate && \
source .venv/bin/activate && \
codegate run \
  -i "实现一个用户注册功能，支持邮箱验证" \
  --executor opencode \
  --executor-model kimi-for-coding/k2p6
```

---

## 前置条件

```bash
# 1. 验证 opencode
opencode --version          # 需要 ≥ 1.14

# 2. 验证可用模型
opencode models

# 3. 确认 .env 已配置
cat /Users/wukai/Desktop/腾讯云/codegate/.env
# 需包含: DEEPSEEK_API_KEY=sk-xxx
```

---

## 执行器对比

| | 内置模拟 (builtin_llm) | opencode |
|---|---|---|
| 用途 | 快速测试/调试 | 真实治理验证 |
| 产出 | 文本模拟 | **真实代码文件** |
| 速度 | ~3s/case | ~90s/case |
| Token | ~1K/case | ~200K/case |
| 参数 | 无需额外参数 | `--executor=opencode --executor-model=xxx` |
