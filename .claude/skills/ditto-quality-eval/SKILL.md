---
name: ditto-quality-eval
description: >
  全维度质量评估 - 6维度并行评估代码/架构/测试/流程/运维/领域质量，
  生成雷达图和改进报告。支持 --full / --quick / --dimension 模式。
  使用多 Agent 并行执行，基线数据预跑注入避免重复。
---

# Ditto 质量评估

全维度系统质量评估，6 个维度并行评估，生成结构化雷达图和改进报告。

## 参数说明

```
$ARGUMENTS: [--full|--quick|--dimension <dims>]

--full        全量评估（6 个维度并行，约 3-5 分钟）
--quick       快速评估（只跑代码+架构+测试，约 1-2 分钟）（默认）
--dimension   指定维度评估（逗号分隔，如 --dimension code,arch,test）

维度标识：
  code        代码质量
  arch        架构质量
  test        测试质量
  eng         工程流程
  ops         运维质量
  domain      领域特有
```

## Agent 分工表

| Agent | 维度 | subagent_type | 核心数据来源 |
|-------|------|--------------|-------------|
| Agent₁ | 代码质量 (code) | `Explore` | lint + type + ruff stats |
| Agent₂ | 架构质量 (arch) | `Explore` | arch-check + import 分析 |
| Agent₃ | 测试质量 (test) | `Explore` | test --fast + coverage |
| Agent₄ | 工程流程 (eng) | `general-purpose` | git log + CI 配置 |
| Agent₅ | 运维质量 (ops) | `Explore` | 日志/安全/配置审查 |
| Agent₆ | 领域特有 (domain) | `general-purpose` | 前视偏差/策略隔离/风控 |

## 执行流程

```
用户调用 /ditto-quality-eval [参数]
  │
  ├─ Phase 0: 准备（编排器直接执行）
  │   ├─ 解析参数 → 确定运行模式
  │   ├─ 读取评价框架文档
  │   │   docs/plans/2026-06-02-software-quality-evaluation-framework.md
  │   ├─ 运行基线数据收集（Bash 并行）：
  │   │   pixi run -e dev lint 2>&1 | tail -20
  │   │   pixi run -e dev type 2>&1 | tail -20
  │   │   pixi run -e dev test --unit --fast 2>&1 | tail -30
  │   │   pixi run -e dev arch-check 2>&1 | tail -30
  │   │   git log --oneline -20
  │   │   find packages/ -name "*.py" ! -path "*/tests/*" | xargs wc -l | tail -1
  │   │   find packages/ -name "test_*.py" -o -name "*_test.py" | xargs wc -l | tail -1
  │   └─ 将所有基线数据合并为 baseline_context
  │
  ├─ Phase 1: 并行评估（Agent tool 一次调用，多个 Agent 同时启动）
  │   │
  │   │   每个 Agent 的 prompt 结构：
  │   │   ─────────────────────────────
  │   │   你是 Ditto 量化交易平台的 {维度名}评估专家。
  │   │
  │   │   ## 基线数据（已预跑，请直接使用）
  │   │   {baseline_context}
  │   │
  │   │   ## 评价标准（请读取并遵循）
  │   │   {references/xxx.md 的内容}
  │   │
  │   │   ## 输出要求
  │   │   严格按照以下 JSON Schema 返回评估结果：
  │   │   {output_schema}
  │   │   ─────────────────────────────
  │   │
  │   ├─ Agent₁ → 读取 references/code-quality.md
  │   ├─ Agent₂ → 读取 references/architecture.md
  │   ├─ Agent₃ → 读取 references/test-quality.md
  │   ├─ Agent₄ → 读取 references/engineering-process.md
  │   ├─ Agent₅ → 读取 references/operations.md
  │   └─ Agent₆ → 读取 references/domain-specific.md
  │
  ├─ Phase 2: 合成报告（编排器内联执行，不另开 Agent）
  │   ├─ 读取 references/radar-template.md 获取报告模板
  │   ├─ 汇总所有 Agent 的 JSON 结果
  │   ├─ 计算加权总分：
  │   │   code=0.20  arch=0.25  test=0.15  eng=0.10  ops=0.15  domain=0.15
  │   ├─ 生成 ASCII 雷达图
  │   ├─ 收集所有 warning/fail 项 → 按优先级排序 Top 10
  │   ├─ 检查 docs/reviews/ 是否有上次报告 → 生成对比表
  │   └─ 写入 docs/reviews/YYYY-MM-DD-quality-eval.md
  │
  └─ Phase 3: 呈现摘要（控制台输出）
      ├─ ASCII 雷达图
      ├─ 综合评分
      ├─ Top 5 改进项
      └─ 报告文件路径
```

## Agent 统一输出 Schema

每个 Agent 必须严格返回以下 JSON 结构：

```json
{
  "dimension": "code | arch | test | eng | ops | domain",
  "dimension_label": "维度中文名",
  "score": 4.2,
  "max_score": 5.0,
  "findings": [
    {
      "id": "C-001",
      "item": "评价项名称",
      "weight": 3,
      "status": "pass | warning | fail",
      "evidence": "具体数据或观察结果",
      "recommendation": "改进建议（pass 时为 null）"
    }
  ],
  "metrics": {
    "metric_name": "value 或 '未度量'"
  },
  "top_issues": [
    {
      "priority": 1,
      "item": "评价项名称",
      "description": "问题描述",
      "recommendation": "改进建议"
    }
  ]
}
```

**评分规则**：
- 每个 pass 项 → 满分（权重分）
- 每个 warning 项 → 权重分的 60%
- 每个 fail 项 → 0 分
- 总分 = Σ(各项得分) / Σ(各项满分) × 5.0
- 硬性项 fail → 维度最高 2★（各 reference 文件中标注）

**星级映射**：
| 分数 | 星级 | 标签 |
|------|------|------|
| 4.0-5.0 | 4-5★ | 🟢 优秀 |
| 3.0-3.9 | 3★ | 🟡 合格 |
| 2.0-2.9 | 2★ | 🟠 待改进 |
| 1.0-1.9 | 1★ | 🔴 需改进 |

## Reference 文件

| 文件 | 维度 | 内容 |
|------|------|------|
| [references/code-quality.md](references/code-quality.md) | 代码质量 | 10 评价项 + SIG 阈值 + 检查命令 |
| [references/architecture.md](references/architecture.md) | 架构质量 | 9 评价项 + ATAM/SIG 阈值 + 技术债四象限 |
| [references/test-quality.md](references/test-quality.md) | 测试质量 | 10 评价项 + 覆盖率阈值 + 检查命令 |
| [references/engineering-process.md](references/engineering-process.md) | 工程流程 | DORA 指标 + SPACE + CI 门禁 + 检查命令 |
| [references/operations.md](references/operations.md) | 运维质量 | 10 评价项 + 可观测性/安全阈值 + 检查命令 |
| [references/domain-specific.md](references/domain-specific.md) | 领域特有 | 10 评价项 + 前视偏差/策略隔离/风控 + 检查命令 |
| [references/radar-template.md](references/radar-template.md) | 报告模板 | ASCII 雷达图 + Markdown 报告 + 加权公式 |

## 确定性约束

### MUST（必须）
- Phase 0 必须先运行基线数据收集，结果注入所有 Agent prompt
- 所有 Agent 必须使用 `Agent` tool 并行启动（一个 tool call block 内多个 Agent）
- 每个 Agent 必须返回符合 Schema 的 JSON
- 报告必须写入 `docs/reviews/YYYY-MM-DD-quality-eval.md`
- 必须计算加权总分并生成雷达图
- 必须检查历史报告并生成对比表（如果存在）

### MUST NOT（禁止）
- 禁止在 Agent 内重复运行 `pixi run -e dev check`（Phase 0 已预跑）
- 禁止使用 `--full` 以外的模式运行超过 6 个 Agent
- 禁止跳过 Phase 0 直接分发 Agent
- 禁止将合成阶段拆分为额外 Agent（主 Claude 内联完成）

### SHOULD（应该）
- 优先使用 `Explore` subagent_type 处理代码扫描类维度
- 使用 `general-purpose` subagent_type 处理需要推理的维度（工程流程、领域特有）
- Agent prompt 中包含评价标准的完整内容（避免 Agent 自行读取文件的额外开销）

## 禁止事项

| ❌ 禁止 | 原因 |
|---------|------|
| 嵌套调用 `/ditto-architecture-audit` | 重复执行 lint/type/test，浪费 token |
| Agent 内运行 `pixi run -e dev check` | Phase 0 已预跑，重复执行浪费时间 |
| 跳过加权计算直接平均 | 各维度权重不同，简单平均不准确 |
| 生成报告但不写入文件 | 报告必须持久化，支持历史对比 |
| 在 CI 中自动运行 | 本 Skill 是交互式评估，不适合自动化 |

## 评价框架来源

完整评价框架文档：`docs/plans/2026-06-02-software-quality-evaluation-framework.md`

业界标准：ISO/IEC 25010:2023、CISQ/ISO 5055、SIG/TÜViT、SQALE、ATAM、Fitness Functions、DORA、SPACE
