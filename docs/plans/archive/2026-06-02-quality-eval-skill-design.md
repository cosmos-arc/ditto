# Ditto 质量评估 Skill 设计文档

> **版本**: v1.0
> **日期**: 2026-06-02
> **状态**: 设计确认，待实现

---

## 1. 概述

### 1.1 目的

将 [软件系统质量评价框架](./2026-06-02-software-quality-evaluation-framework.md)（六维 59 评价项）实现为一个可执行的 Claude Code Skill，通过多 Agent 并行评估，生成结构化的质量雷达图和改进报告。

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **并行优先** | 6 个维度无依赖，6 个 Agent 同时启动，最小化总耗时 |
| **基线预跑** | 编排器先运行 `pixi run -e dev check`，结果注入所有 Agent，避免重复执行 |
| **结构化输出** | 每个 Agent 返回统一 JSON Schema，编排器合成报告 |
| **增量对比** | 报告追加写入 `docs/reviews/`，支持与上次评估对比 |
| **YAGNI** | 不做自动 CI 集成、不做历史趋势图、不做 Web Dashboard |

### 1.3 业界来源

详见 [评价框架文档](./2026-06-02-software-quality-evaluation-framework.md)：
- ISO/IEC 25010:2023、CISQ/ISO 5055、SIG/TÜViT、SQALE
- ATAM、Fitness Functions、DORA、SPACE
- Google/Microsoft 代码审查标准

---

## 2. Skill 目录结构

```
.claude/commands/
  ditto-quality-eval.md                  # 主编排器 Skill（~200 行）
  quality-eval-references/               # 分维度参考标准
    code-quality.md                      # 维度①：代码质量（评价项 + 阈值 + 检查方法）
    architecture.md                      # 维度②：架构质量
    test-quality.md                      # 维度③：测试质量
    engineering-process.md               # 维度④：工程流程
    operations.md                        # 维度⑤：运维质量
    domain-specific.md                   # 维度⑥：领域特有
    radar-template.md                    # 雷达图 + 报告模板
```

### 2.1 文件职责

| 文件 | 行数（估） | 职责 |
|------|-----------|------|
| `ditto-quality-eval.md` | ~200 | YAML frontmatter + 编排流程 + Agent 分发 + 报告合成 |
| `code-quality.md` | ~80 | 10 个评价项 + 量化阈值 + Bash 命令 |
| `architecture.md` | ~80 | 9 个评价项 + 量化阈值 + 检查方法 |
| `test-quality.md` | ~60 | 10 个评价项 + 量化阈值 + 命令 |
| `engineering-process.md` | ~60 | 15 个评价项 + DORA 阈值 + Git 命令 |
| `operations.md` | ~60 | 10 个评价项 + 量化阈值 + 检查方法 |
| `domain-specific.md` | ~60 | 10 个评价项 + 量化阈值 + 检查方法 |
| `radar-template.md` | ~60 | ASCII 雷达图模板 + Markdown 报告模板 |

---

## 3. SKILL.md 设计（编排器）

### 3.1 YAML Frontmatter

```yaml
---
name: ditto-quality-eval
description: "全维度质量评估 - 6维度并行评估代码/架构/测试/流程/运维/领域质量，生成雷达图和改进报告"
---
```

### 3.2 参数说明

```
$ARGUMENTS: [--full|--quick|--dimension <dims>]

--full        全量评估（6 个维度并行，约 3-5 分钟）
--quick       快速评估（只跑代码+架构+测试，约 1-2 分钟）
--dimension   指定维度评估（逗号分隔，如 --dimension code,arch,test）

维度标识：
  code        代码质量
  arch        架构质量
  test        测试质量
  eng         工程流程
  ops         运维质量
  domain      领域特有
```

### 3.3 执行流程

```
用户调用 /ditto-quality-eval [--full|--quick|--dimension X]
  │
  ├─ Phase 0: 准备（编排器直接执行）
  │   ├─ 解析参数 → 确定运行模式
  │   ├─ 读取评价框架文档 docs/plans/2026-06-02-software-quality-evaluation-framework.md
  │   ├─ 读取 references/ 中对应维度的详细标准
  │   ├─ 运行基线数据收集：
  │   │   pixi run -e dev lint 2>&1 | tail -5
  │   │   pixi run -e dev type 2>&1 | tail -5
  │   │   pixi run -e dev test --unit --fast 2>&1 | tail -10
  │   │   pixi run -e dev arch-check 2>&1 | tail -10
  │   ├─ 收集补充数据：
  │   │   git log --oneline -20
  │   │   git diff --stat main...HEAD
  │   │   find packages/ -name "*.py" ! -path "*/tests/*" | xargs wc -l | tail -1
  │   │   find packages/ -name "test_*.py" -o -name "*_test.py" | xargs wc -l | tail -1
  │   └─ 将所有基线数据注入后续 Agent prompt
  │
  ├─ Phase 1: 并行评估（6 个 Agent 同时启动）
  │   ├─ Agent₁ → 代码质量 JSON
  │   ├─ Agent₂ → 架构质量 JSON
  │   ├─ Agent₃ → 测试质量 JSON
  │   ├─ Agent₄ → 工程流程 JSON
  │   ├─ Agent₅ → 运维质量 JSON
  │   └─ Agent₆ → 领域特有 JSON
  │
  ├─ Phase 2: 合成报告（编排器内联执行）
  │   ├─ 汇总 6 个 JSON → 计算加权总分
  │   ├─ 生成 ASCII 雷达图
  │   ├─ 按优先级排序改进项（Top 10）
  │   ├─ 与上次评估对比（如果 docs/reviews/ 有历史报告）
  │   └─ 输出到 docs/reviews/YYYY-MM-DD-quality-eval.md
  │
  └─ Phase 3: 呈现摘要
      ├─ 控制台输出雷达图 + 评分 + Top 5 问题
      └─ 报告文件路径
```

---

## 4. Agent 设计

### 4.1 统一输出 Schema

每个 Agent 返回统一的 JSON 结构：

```json
{
  "dimension": "code-quality",
  "dimension_label": "代码质量",
  "rating": "🟢 优秀",
  "score": 4.2,
  "max_score": 5.0,
  "findings": [
    {
      "id": "C-001",
      "item": "类型安全",
      "weight": 3,
      "status": "pass",
      "evidence": "basedpyright strict 零错误，0 个 type:ignore",
      "recommendation": null
    },
    {
      "id": "C-004",
      "item": "代码重复度",
      "weight": 2,
      "status": "warning",
      "evidence": "未引入重复度量化工具，无法自动检测",
      "recommendation": "引入 jscpd 或 SonarQube 持续追踪"
    }
  ],
  "metrics": {
    "type_ignore_count": 0,
    "avg_cyclomatic_complexity": "未度量",
    "duplication_rate": "未度量",
    "ruff_violations": 0
  },
  "top_issues": [
    {
      "priority": 1,
      "item": "代码重复度",
      "description": "未引入重复度量化工具",
      "recommendation": "引入 jscpd 或 SonarQube 持续追踪"
    }
  ]
}
```

### 4.2 Agent 配置表

| Agent | subagent_type | 维度标识 | 核心工具调用 | Prompt 核心内容 |
|-------|--------------|---------|-------------|----------------|
| Agent₁ | `Explore` | `code` | `pixi run lint`, `pixi run type`, ruff stats, `find ... wc -l` | 读取 code-quality.md 标准，基于注入的基线数据评估 10 个评价项 |
| Agent₂ | `Explore` | `arch` | `pixi run arch-check`, import 分析, `Read` 各包 `__init__.py` | 读取 architecture.md 标准，评估 9 个评价项 |
| Agent₃ | `Explore` | `test` | `pixi run test --unit --fast`, coverage report 分析 | 读取 test-quality.md 标准，评估 10 个评价项 |
| Agent₄ | `general-purpose` | `eng` | `git log`, PR 统计, CI 配置分析 | 读取 engineering-process.md 标准，评估 15 个评价项 |
| Agent₅ | `Explore` | `ops` | `Read` 配置文件, `Grep` 日志/安全模式 | 读取 operations.md 标准，评估 10 个评价项 |
| Agent₆ | `general-purpose` | `domain` | `Read` 架构文档, `Grep` 前视偏差/策略隔离模式 | 读取 domain-specific.md 标准，评估 10 个评价项 |

### 4.3 Agent Prompt 模板

每个 Agent 的 prompt 遵循统一模板：

```
你是 Ditto 量化交易平台的 {dimension_label}评估专家。

## 任务
基于以下基线数据和评价标准，评估 {dimension_label} 维度的所有评价项。

## 基线数据（已预跑）
{baseline_data}

## 评价标准
{reference_content}

## 输出要求
严格返回 JSON，schema 如下：
{json_schema}

## 注意事项
- status 只能是 pass / warning / fail
- evidence 必须包含具体数据或观察结果
- recommendation 仅在 status 非 pass 时提供
- top_issues 最多 3 个，按优先级排序
- score 为 1.0-5.0 浮点数，保留一位小数
- 未度量的指标在 metrics 中标注 "未度量"
```

### 4.4 Agent 启动方式

```python
# 编排器使用 Agent tool 并行启动 6 个 Agent
# 所有 Agent 在一个 tool call block 中同时启动

agent_1 = Agent(
    description="评估代码质量",
    prompt=code_quality_prompt,
    subagent_type="Explore",
    # schema 参数强制结构化输出
)

agent_2 = Agent(
    description="评估架构质量",
    prompt=architecture_prompt,
    subagent_type="Explore",
)

# ... 以此类推
```

---

## 5. 报告合成

### 5.1 加权评分计算

```python
weights = {
    "code":    0.20,  # 代码质量 20%
    "arch":    0.25,  # 架构质量 25%
    "test":    0.15,  # 测试质量 15%
    "eng":     0.10,  # 工程流程 10%
    "ops":     0.15,  # 运维质量 15%
    "domain":  0.15,  # 领域特有 15%
}

weighted_score = sum(
    results[dim]["score"] * weights[dim]
    for dim in results
)
```

### 5.2 ASCII 雷达图模板

```
              测试质量
               {t}★
                 |
    代码 {c}★ ──┼── {o}★ 运维
                 |
    架构 {a}★ ──┼── {d}★ 领域
                 |
              工程流程
               {e}★

    综合评分: {total} / 5.0 ★
```

### 5.3 报告输出模板

```markdown
# Ditto 质量评估报告 {date}

> 评估模式: {mode} | 评估耗时: {duration}

## 综合评分

{radar_chart}

**综合评分: {total_score} / 5.0 ★** (加权)

## 各维度详情

### ① 代码质量 — {code_rating} ({code_score}★)
| # | 评价项 | 权重 | 状态 | 证据 | 建议 |
|---|--------|------|------|------|------|
| C1 | 类型安全 | ★★★ | ✅ | ... | — |
| C2 | 代码复杂度 | ★★★ | ⚠️ | ... | ... |
...

### ② 架构质量 — {arch_rating} ({arch_score}★)
...

## Top 10 改进项

| # | 维度 | 评价项 | 优先级 | 建议 |
|---|------|--------|--------|------|
| 1 | 代码 | 重复度 | P1 | 引入 jscpd |
...

## 与上次评估对比

| 维度 | 上次 ({prev_date}) | 本次 | 变化 |
|------|-------------------|------|------|
| 代码质量 | 4.0★ | 4.5★ | ↑ +0.5 |
...

## 附录：评估配置

- 评价框架: docs/plans/2026-06-02-software-quality-evaluation-framework.md
- 基线数据: pixi run -e dev check 结果
- 评估时间: {timestamp}
```

---

## 6. 实现计划

### 6.1 文件创建清单

| # | 文件 | 行数（估） | 优先级 |
|---|------|-----------|--------|
| 1 | `.claude/commands/ditto-quality-eval.md` | ~200 | P0 |
| 2 | `.claude/commands/quality-eval-references/code-quality.md` | ~80 | P0 |
| 3 | `.claude/commands/quality-eval-references/architecture.md` | ~80 | P0 |
| 4 | `.claude/commands/quality-eval-references/test-quality.md` | ~60 | P0 |
| 5 | `.claude/commands/quality-eval-references/engineering-process.md` | ~60 | P1 |
| 6 | `.claude/commands/quality-eval-references/operations.md` | ~60 | P1 |
| 7 | `.claude/commands/quality-eval-references/domain-specific.md` | ~60 | P1 |
| 8 | `.claude/commands/quality-eval-references/radar-template.md` | ~60 | P0 |

### 6.2 实现顺序

1. **Step 1**: 创建 `quality-eval-references/` 目录和 6 个维度参考文件
2. **Step 2**: 创建 `radar-template.md` 报告模板
3. **Step 3**: 创建 `ditto-quality-eval.md` 主编排器
4. **Step 4**: 测试 `--quick` 模式（代码+架构+测试）
5. **Step 5**: 测试 `--full` 模式（全量 6 维度）
6. **Step 6**: 迭代优化 Agent prompt 和评分逻辑

### 6.3 测试策略

| 测试场景 | 模式 | 预期结果 |
|---------|------|---------|
| 首次运行 | `--quick` | 3 个 Agent 并行，生成含代码+架构+测试的报告 |
| 全量运行 | `--full` | 6 个 Agent 并行，生成完整雷达图报告 |
| 单维度 | `--dimension code` | 1 个 Agent，仅生成代码质量评估 |
| 历史对比 | `--full`（第二次） | 报告含"与上次对比"章节 |

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Agent 超时 | 某维度无结果 | 设置 timeout，缺失维度标注"评估超时" |
| 基线数据收集失败 | 所有 Agent 无输入 | 降级为 Agent 各自运行命令 |
| JSON Schema 不合规 | 合成失败 | Agent 内置 fallback，重试一次 |
| Token 消耗过高 | 成本问题 | `--quick` 模式仅 3 个 Agent |

---

## 8. 与现有 Skill 的关系

```
/ditto-quality-eval          ← 本 Skill（全维度评估）
  │
  ├── 复用 /ditto-architecture-audit 的部分检查逻辑
  │   （但不调用它，避免嵌套 Skill 的复杂性）
  │
  └── 输出到 docs/reviews/ 与 ditto-architecture-audit 共享目录
      （文件名区分：*-quality-eval.md vs *-architecture-audit.md）
```

**不嵌套调用的原因**：
- ditto-architecture-audit 会运行自己的 lint/type/test
- 本 Skill 已在 Phase 0 预跑基线数据
- 嵌套调用导致重复执行和 token 浪费
- 两者检查项有重叠但侧重点不同（audit 偏深入，eval 偏全局评分）
