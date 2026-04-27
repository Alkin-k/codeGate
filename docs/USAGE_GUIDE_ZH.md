# CodeGate 使用手册

> 版本: Alpha v0.2.0 | 更新日期: 2026-04-27

---

## 一、系统简介

### 1.1 CodeGate 是什么

CodeGate 是一个 **AI 代码变更治理层**。它不替代 AI Coding 工具，而是在 AI 生成代码之后、合入主干之前，自动完成需求澄清、契约生成、漂移检测和放行裁决。

**核心流程：**

```
需求输入 → Spec Council ⇄ 用户澄清 → 实现契约 → Executor → Reviewer → Gatekeeper → 裁决
              │              │              │           │           │           │
          分析需求       交互式提问       goals       AI 执行     漂移检测    approve /
          提取约束       或 --answers    criteria    (OpenCode)   证据链     revise_code /
                                        constraints                        escalate_to_human
```

### 1.2 四层防御机制

| 层级 | 名称 | 类型 | 作用 |
|------|------|------|------|
| 第一层 | Structural Pre-check | 确定性 | 对比 baseline 代码，识别模式变化（注解删除、签名修改等） |
| 第二层 | LLM Review | AI | 对照契约审查实现，输出 findings（类别、严重级别、修复建议） |
| 第三层 | Post-filter | 确定性 | 压掉 Ghost Pattern（LLM 虚构的、baseline 中不存在的 findings） |
| 第四层 | Policy Engine | 确定性 | 即使 Gatekeeper 判 APPROVE，如有 blocking findings 仍强制覆盖为 REVISE_CODE |

### 1.3 三种裁决

| 裁决 | 含义 | 图标 | 后续动作 |
|------|------|------|---------|
| `APPROVE` | 实现符合契约，无阻断问题 | ✅ | 可放行 |
| `REVISE_CODE` | 存在阻断问题，需修改代码 | 🔄 | 查看 findings → 修复 → 重跑 |
| `ESCALATE_TO_HUMAN` | 超出自动裁决范围 | ⚠️ | 人工审查 |

---

## 二、安装与配置

### 2.1 环境要求

- Python 3.9+（推荐 3.11+）
- pip 或 uv 包管理器
- Git
- （可选）OpenCode CLI — 如需使用 `codegate ab` 执行真实代码变更

### 2.2 安装

```bash
# 克隆仓库
git clone git@github.com:Alkin-k/codeGate.git
cd codegate

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装（editable mode）
pip install -e .

# 验证
codegate --help
```

### 2.3 配置 .env

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

```env
# ========== 模型配置 ==========
# 每个角色可以使用不同模型

# Spec Council（需求分析，需要强推理能力）
CODEGATE_SPEC_MODEL=deepseek/deepseek-chat

# Executor（代码生成，需要好的代码生成能力）
CODEGATE_EXEC_MODEL=deepseek/deepseek-chat

# Reviewer（代码审查，需要仔细的比对能力）
CODEGATE_REVIEW_MODEL=deepseek/deepseek-chat

# Gatekeeper（裁决，需要结构化判断）
CODEGATE_GATE_MODEL=deepseek/deepseek-chat

# ========== API Key ==========
# 填写你使用的模型提供商的 Key
DEEPSEEK_API_KEY=sk-your-key-here

# 如使用 OpenAI 兼容 API：
# OPENAI_API_KEY=your-key
# OPENAI_API_BASE=https://your-proxy.com/v1

# ========== 其他配置 ==========
CODEGATE_STORE_DIR=./artifacts      # 证据存储目录
CODEGATE_MAX_CLARIFY_ROUNDS=3       # Spec Council 最大澄清轮次
CODEGATE_LOG_LEVEL=INFO             # 日志级别：DEBUG / INFO / WARNING
```

**配置要点：**

- 所有模型字段使用 [LiteLLM 格式](https://docs.litellm.ai/docs/providers)，如 `deepseek/deepseek-chat`、`openai/gpt-4o`
- 如果团队统一使用同一模型，只需设置一个 Key，所有 `CODEGATE_*_MODEL` 字段填相同值
- `.env` 已被 `.gitignore` 排除，不会被提交

---

## 三、命令总览

CodeGate 提供三个核心命令：

| 命令 | 用途 | 典型场景 |
|------|------|---------|
| `codegate run` | 运行治理管线（需求 → 契约 → 执行 → 审查 → 裁决） | 日常开发、交互式澄清 |
| `codegate ab` | 单个 A/B 评估（对照组 vs 治理组） | 评估 CodeGate 效果 |
| `codegate ab-batch` | 批量 A/B 评估 | 系统性评估多个 case |

---

## 四、`codegate run` — 治理管线

### 4.1 交互式模式（推荐首次使用）

```bash
codegate run \
  --input "为 /api/convert 增加文件名非法字符校验" \
  --executor opencode \
  --executor-model kimi-for-coding/k2p6 \
  --project-dir /path/to/your/project
```

**执行流程：**

1. Spec Council 分析需求，生成澄清问题
2. CLI 展示问题面板，用户逐条回答
3. 回答后自动生成实现契约
4. Executor 执行代码变更
5. Reviewer 审查 → Gatekeeper 裁决
6. 输出结果 + 保存证据

**交互示例：**

```text
🛡️ CodeGate Governance Pipeline
  Requirement: 为 /api/convert 增加文件名非法字符校验
  Executor: opencode

╭─────────────────────────────────────────╮
│ 📋 Spec Council 需要澄清以下问题       │
╰─────────────────────────────────────────╯

  必答 1. [必答] 非法文件名包含哪些字符？
  1> 包含 .. 或 /

  可选 2. [可选] 错误码应该使用什么？
  2> INVALID_FILENAME

╭─── 📋 澄清问答摘要 ────────────────────╮
│ 1. → 包含 .. 或 /                       │
│ 2. → INVALID_FILENAME                   │
╰─────────────────────────────────────────╯

正在生成契约并执行治理管线...
```

**操作说明：**

- `[必答]` 问题不能跳过，必须输入回答
- `[可选]` 问题可直接按回车跳过
- 输入 `q` 可随时退出

### 4.2 预设回答模式（自动化场景）

```bash
codegate run \
  --input "为 /api/convert 增加文件名校验" \
  --answers "抛出 IllegalArgumentException|错误码 INVALID_FILENAME" \
  --executor opencode \
  --executor-model kimi-for-coding/k2p6
```

`--answers` 支持两种格式：

- **管道分隔**：`"答案1|答案2|答案3"`
- **JSON 数组**：`'["答案1", "答案2"]'`

### 4.3 全部参数

| 参数 | 缩写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--input` | `-i` | ✅ | — | 需求描述 |
| `--context` | `-c` | — | `""` | 项目上下文 |
| `--answers` | `-a` | — | — | 预设回答（跳过交互） |
| `--executor` | `-e` | — | `builtin_llm` | 执行器：`builtin_llm` / `opencode` |
| `--executor-model` | — | — | — | Executor 使用的模型 |
| `--project-dir` | — | — | — | 项目目录（opencode 需要） |
| `--timeout` | — | — | `600` | 执行超时（秒） |
| `--output` | `-o` | — | `./artifacts` | 证据输出目录 |
| `--env` | — | — | `.env` | 配置文件路径 |

### 4.4 产出文件

```
artifacts/{work_item_id}/
├── work_item.json              # 原始需求
├── contract.json               # 实现契约（goals、criteria、constraints）
├── clarification_qa.json       # 澄清问答（questions、answers、mode）
├── execution_report.json       # 执行报告
├── review_findings.json        # 最终 findings（post-filter 后）
├── raw_review_findings.json    # LLM 原始 findings（filter 前）
├── suppressed_findings.json    # 被压掉的 findings + 原因
├── structural_diff.json        # 确定性基线 diff
├── gate_decision.json          # Gatekeeper 裁决详情
├── policy_result.json          # Policy Engine 覆盖记录
├── phase_timings.json          # 各阶段耗时
├── iteration_history.json      # 多轮迭代记录
└── summary.json                # 运行摘要
```

---

## 五、`codegate ab` — 单 case A/B 评估

### 5.1 基本用法

```bash
codegate ab \
  --project /path/to/your/project \
  --input "为 /api/convert 增加文件名非法字符校验" \
  --model kimi-for-coding/k2p6 \
  --case-name "文件名校验" \
  --answers "抛出 IllegalArgumentException，由 handleBadRequest 统一处理。错误码 INVALID_FILENAME。" \
  --build-cmd "mvn test -B"
```

### 5.2 它做了什么

```
自动执行 5 步：

1. Clean Copy   — 从源项目复制两份独立副本
2. Baseline     — 验证 git status 干净 + 测试通过
3. Line A       — 纯 AI 执行（无治理，对照组）
4. Line B       — CodeGate + AI 执行（完整治理管线）
5. Report       — 生成 audit_report.md + report.md + ab_result.json
```

> ⚠️ 源项目不会被修改，CodeGate 自动创建临时副本。

### 5.3 全部参数

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--project` | ✅ | — | 源项目路径 |
| `--input` | ✅ | — | 需求描述 |
| `--model` | ✅ | — | Executor 使用的模型 |
| `--case-name` | 建议 | — | 人类可读的 case 名称 |
| `--answers` | 建议 | — | 预设的 clarification 回答 |
| `--build-cmd` | — | `mvn test -B` | 测试命令 |
| `--timeout` | — | `600` | 执行器超时（秒） |
| `--output` | — | `ab_results/` | 输出目录 |

### 5.4 耗时预期

| 阶段 | 典型耗时 |
|------|---------:|
| Clean Copy + Baseline | 5-15s |
| Line A (纯 AI) | 120-300s |
| Line B (CodeGate + AI) | 140-500s |
| **总计** | **4-12 分钟** |

---

## 六、`codegate ab-batch` — 批量评估

### 6.1 编写 YAML 配置

创建 `eval_cases/my_cases.yaml`：

```yaml
# 顶层默认值
project: /path/to/your/project
model: kimi-for-coding/k2p6
build_cmd: mvn test -B
timeout: 600

cases:
  - name: Case 1 名称
    input: >
      需求描述，可以多行。
    answers: >
      预设回答。

  - name: Case 2 名称
    input: >
      另一个需求描述。
    answers: >
      另一个回答。
    # 可覆盖顶层默认值：
    # model: other-model
    # build_cmd: npm test
    # timeout: 300
```

### 6.2 运行

```bash
codegate ab-batch --cases eval_cases/my_cases.yaml
```

### 6.3 产出结构

```
ab_results/batch_{timestamp}/
├── batch_report.md          # 汇总报告（6+1 章节）
├── batch_summary.json       # 结构化汇总数据
├── Case1_{ts}/
│   ├── audit_report.md      # 7 章节完整治理报告
│   ├── report.md            # 紧凑摘要
│   ├── ab_result.json       # 完整 raw 数据
│   └── codegate_artifacts/  # 治理证据
├── Case2_{ts}/
│   └── ...
```

---

## 七、阅读报告

### 7.1 audit_report.md（单 case）

| 章节 | 内容 | 快速阅读 |
|------|------|---------|
| §1 Clearance Decision | ✅/🔄/⚠️ 最终判定 + 依据 | **必看** |
| §2 Risk Summary | 6 维风险评分表 | — |
| §3 Findings Detail | 每个 finding 的 severity、message、location、suggestion | 开发者看 |
| §4 A/B Comparison | Line A vs Line B 对比 | — |
| §5 Evidence Chain | 8 项 artifact 路径 + 存在性 | 审计看 |
| §6 Reproducibility | 项目、模型、命令、时间戳 | 审计看 |
| §7 Verdict | 最终判定 + 阻断原因 | **必看** |

**快速阅读路径**：只看 §1 + §7。如果是 ✅ → 放行；如果是 🔴 → 看 §3 了解具体问题。

### 7.2 batch_report.md（批量）

| 章节 | 内容 |
|------|------|
| §1 Executive Summary | 总案例数、通过率、平均 overhead |
| §2 Case Results | 逐 case 汇总表 |
| §3 Aggregate Findings | 全局 findings 统计 |
| §4 Individual Reports | 每个 case 的 artifact 路径 |
| §5 Reproducibility | cases file、project、model |
| §6 Batch Verdict | 🟢/🟡/🔴 总体判定 |
| §7 Blocked Cases | （仅在有阻断时）每个 blocked case 的详情 |

---

## 八、编写好的 Case

### 8.1 需求描述原则

1. **明确约束** — 写清"不要做什么"：`不要修改已有方法的签名和返回类型`
2. **指定错误码** — `错误码使用 INVALID_FILENAME`
3. **指定异常路径** — `抛出 IllegalArgumentException，由 handleBadRequest 统一处理`
4. **说明保留要求** — `必须保留 @Min(72) 注解，不得删除或修改`

### 8.2 Answers 设计

好的 answers 应该：

- 重申关键约束：`由 GlobalExceptionHandler.handleBadRequest 统一处理`
- 消除歧义：`空字符串或 null 不做校验`
- 指定边界行为：`dpi=600 是合法边界，dpi=601 是非法`

### 8.3 内置参考 Case

`eval_cases/image2pdf_cases.yaml` 包含 4 个已验证 case：

| Case | 类型 | 预期结果 |
|------|------|---------|
| 错误响应一致性 | 输入校验 + 错误处理 | ✅ APPROVE |
| DPI参数保护 | 参数边界校验 | ✅ APPROVE |
| 测试质量-空文件上传 | 参数校验 | ✅ APPROVE |
| 错误处理链路重构 | 逻辑重构 + 5 项保留约束 | 🔄 REVISE_CODE（contract conflict） |

---

## 九、Findings 分级说明

### Severity（严重级别）

| 级别 | 含义 |
|------|------|
| P0 | 关键：约束违反、安全漏洞 |
| P1 | 重要：目标部分达成、静默行为变更 |
| P2 | 次要：风格、优化建议 |

### Disposition（处置方式）

| 处置 | Gate 行为 | 图标 |
|------|----------|------|
| blocking | 必须修复才能 approve | 🚫 |
| advisory | 建议修复，不阻断 | ⚠ |
| info | 仅供参考 | ℹ |

### Policy Override

当 Gatekeeper 判 APPROVE 但存在 blocking findings 时，Policy Engine 强制覆盖为 `REVISE_CODE`：

```
⚠️ Policy Override: Gatekeeper originally decided APPROVE,
but policy enforcement overrode to REVISE_CODE due to 1 blocking finding(s).
```

---

## 十、推荐内测步骤

### 第一步：环境验证

```bash
codegate --help           # 确认安装
codegate run --help       # 查看参数
```

### 第二步：跑内置 Case

```bash
codegate ab-batch --cases eval_cases/image2pdf_cases.yaml
```

预期：3 approve + 1 revise_code（Case 4 是 contract conflict）

### 第三步：审查报告

1. 打开 `batch_report.md` — 看 §2 Case Results
2. 打开 Case 4 的 `audit_report.md` — 看 §1 + §3 + §7
3. 确认你能理解为什么 Case 4 被阻断

### 第四步：用 `codegate run` 体验交互式澄清

```bash
codegate run \
  --input "为你的项目某个 API 增加参数校验" \
  --executor opencode \
  --project-dir /path/to/your/project
```

### 第五步：接入自己的模块

1. 选一个低风险模块（有测试、有清晰 API）
2. 参考第八节编写 case
3. 先用 `codegate ab` 跑单个 case
4. 确认报告可读后，写入 YAML 用 `codegate ab-batch` 批量跑

### 第六步：反馈

请记录：

- 报告能看懂吗？哪里不清楚？
- 决策是否合理？有没有误判？
- 耗时是否可接受？
- 你希望增加什么能力？

---

## 十一、项目结构

```
codegate/
├── src/codegate/
│   ├── agents/          # LLM agents：spec_council、executor、reviewer、gatekeeper
│   ├── adapters/        # 执行器适配器（OpenCode）
│   ├── analysis/        # 确定性结构分析（baseline diff）
│   ├── eval/            # A/B runner + batch runner
│   ├── policies/        # Policy Engine（确定性规则覆盖）
│   ├── prompts/         # LLM prompt 模板
│   ├── schemas/         # Pydantic 数据模型
│   ├── store/           # 证据持久化
│   ├── workflow/        # LangGraph 状态机
│   ├── cli.py           # CLI 入口
│   └── config.py        # 配置管理
├── docs/                # 文档
├── eval_cases/          # A/B 评估用例（YAML）
├── tests/               # 测试
├── .env.example         # 配置模板
├── CHANGELOG.md         # 变更日志
└── pyproject.toml       # 项目定义
```

---

## 十二、术语表

| 术语 | 定义 |
|------|------|
| **Spec Council** | 需求分析 agent，将自然语言需求转换为结构化契约 |
| **Contract** | 实现契约：goals、acceptance criteria、constraints |
| **Executor** | AI coding 工具（如 OpenCode），执行代码变更 |
| **Reviewer** | 审查 agent，对比契约和实现，输出 findings |
| **Gatekeeper** | 裁决 agent，综合 findings 做出 approve/revise/escalate 决策 |
| **Policy Engine** | 确定性规则引擎，在 Gatekeeper 之后强制执行安全策略 |
| **Structural Pre-check** | 确定性代码分析，在 LLM 审查前识别 baseline 模式变化 |
| **Post-filter** | 确定性过滤器，在 LLM 审查后压掉 ghost pattern 假阳性 |
| **Drift** | AI 实现偏离契约或 baseline 的程度（0-100 分） |
| **Line A** | A/B 评估的对照组：纯 AI 执行，无治理 |
| **Line B** | A/B 评估的实验组：CodeGate + AI 执行 |
| **Contract Conflict** | 需求和保留约束之间存在逻辑矛盾 |
| **Ghost Pattern** | LLM 虚构的、baseline 代码中实际不存在的 finding |
| **Clarification** | Spec Council 向用户提出的澄清问题 |
| **Interactive Mode** | 在 CLI 中交互式回答 Spec Council 的问题 |
| **Pre-provided Mode** | 通过 `--answers` 预设回答，跳过交互 |

---

## 十三、已知限制

| 限制 | 说明 | Workaround |
|------|------|------------|
| 单次运行耗时较长 | 典型 4-12 分钟 | 用 batch 模式 |
| 必须在 clean copy 上跑 | `git status` 必须干净 | 提交或 stash 本地修改 |
| LLM 非确定性 | 同一 case 多次运行可能产出不同代码 | 这正是 CodeGate 存在的意义 |
| 仅支持 OpenCode | 当前只有 `opencode` 执行器适配器 | 后续增加 Cursor、Windsurf |
| Maven 中心 | 测试解析器针对 Maven surefire 优化 | `build_cmd` 支持任意命令 |
| 交互式仅限 `codegate run` | `ab` / `ab-batch` 使用 `--answers` | — |
