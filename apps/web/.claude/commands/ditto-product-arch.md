---
name: ditto-product-arch
description: Use when designing or iterating information architecture, page blueprints, or user flows for the Ditto quantitative platform. Supports 4-role parallel design, audit mode, and incremental iteration.
disable-model-invocation: true
---

# /ditto-product-arch

产品架构设计与迭代编排。聚焦**信息架构、页面蓝图、用户流程**的产出与优化，通过四角色并行设计（产品策略师、信息架构师、UX 策略师、金融领域专家）确保产出符合业界顶级全资产量化平台的标准。

> **目标**: A 股市场优先的业界顶级全资产量化平台。
> **定位**: 这是 `ditto-design-cycle` 的上游——先在这里定义"做什么/怎么组织"，再去创建和审查"做得好不好"。

---

## 核心理念

> **不是"照搬竞品"，而是"理解业界最佳实践，做出更好的选择"。**

- 参考但不复制 Bloomberg/Wind/TradingView 的 IA
- 四角色可能给出**冲突的建议**（如 Strategist 想加功能 vs IA 想控制复杂度）
- Claude 负责呈现冲突 + 分析权衡 + 推荐折中方案
- **用户是最终决策者**
- 产出物是 spec 文档，不是代码

---

## 规范参考

- **产品定位**: [00_ditto_visual_constitution.md](../../docs/designs/specs/00_ditto_visual_constitution.md)
- **现有 IA**: [01_product_information_architecture.md](../../docs/designs/specs/01_product_information_architecture.md)
- **现有蓝图**: [02_core_page_blueprints.md](../../docs/designs/specs/02_core_page_blueprints.md)
- **交互状态**: [04_interaction_state_spec.md](../../docs/designs/specs/04_interaction_state_spec.md)
- **设计决策**: [docs/designs/decisions/](../../docs/designs/decisions/)
- **产品准则**: [00_ditto_product_criteria.md](../../docs/designs/specs/00_ditto_product_criteria.md)
- **角色定义**: [roles.md](../product-arch/roles.md)

---

## 输入

`$ARGUMENTS` — 设计目标 + 可选参数

```bash
# 首次创建全套文档（IA + 蓝图 + 流程）
/ditto-product-arch --create

# 迭代优化信息架构
/ditto-product-arch --iterate ia

# 迭代优化页面蓝图
/ditto-product-arch --iterate blueprint

# 迭代优化用户流程
/ditto-product-arch --iterate flows

# 审计现有文档完整性和一致性
/ditto-product-arch --audit

# 聚焦特定页面
/ditto-product-arch --iterate blueprint --page markets
/ditto-product-arch --iterate blueprint --page trading

# 聚焦特定领域
/ditto-product-arch --create --focus a-share
```

---

## 四个设计角色

| 角色 | model | 核心关注 | 详情 |
|------|-------|---------|------|
| Product Strategist | opus | 产品定位、用户画像、竞争差异化、功能边界 | [roles.md](../product-arch/roles.md#product-strategist) |
| Information Architect | opus | 导航结构、内容分组、标签体系、跨页关系 | [roles.md](../product-arch/roles.md#information-architect) |
| UX Strategist | sonnet | 用户流程、任务分析、交互模式、渐进展示 | [roles.md](../product-arch/roles.md#ux-strategist) |
| Domain Expert | sonnet | 金融领域知识、A 股特性、量化工作流 | [roles.md](../product-arch/roles.md#domain-expert) |

---

## 模型路由策略

| 阶段 | 模型 | 理由 |
|------|------|------|
| Phase 0: CONTEXT | sonnet | 文件读取，纯机械 |
| Phase 1: RESEARCH | 混合 | Domain Expert/IA 用 sonnet，策略判断用 opus |
| Phase 2: DESIGN | 按角色 | Strategist/IA=opus，UX/Domain=sonnet |
| Phase 3: SYNTHESIS | opus | 多角色冲突权衡取舍 |
| Phase 4: DOCUMENT | sonnet | 文档写入 |
| Phase 5: VALIDATE | sonnet | 一致性检查 |

---

## 产出物

| 产出物 | 路径 | 说明 |
|--------|------|------|
| 信息架构 | [01_product_information_architecture.md](../../docs/designs/specs/01_product_information_architecture.md) | 全局 IA、导航结构、页面层级 |
| 页面蓝图 | [02_core_page_blueprints.md](../../docs/designs/specs/02_core_page_blueprints.md) | 每页的模块、优先级、交互 |
| 用户流程 | （内嵌于 IA 文档或独立） | 核心任务的端到端路径 |
| 术语表 | （内嵌于 IA 文档或独立） | 统一标签/术语/中英对齐 |

---

## 产出物结构

```
信息架构文档 (01_product_information_architecture.md)
├─ 1. 产品定位与价值主张
├─ 2. 用户画像与核心需求
├─ 3. 核心工作流（Observe→Discover→Research→Validate→Execute→Monitor）
├─ 4. 信息架构
│   ├─ 4.1 导航模型（sidebar + tabs + command palette）
│   ├─ 4.2 顶层结构（Home / Markets / Research / Trading / AI / Platform）
│   ├─ 4.3 页面层级关系
│   ├─ 4.4 导航路径矩阵（从 A 可到 B/C/D）
│   └─ 4.5 内容分组逻辑
├─ 5. 标签体系与术语表
│   ├─ 5.1 中文标签体系
│   ├─ 5.2 英文标签对照
│   └─ 5.3 资产类别术语
├─ 6. 用户流程
│   ├─ 6.1 核心任务流程（含 happy path + 错误分支）
│   ├─ 6.2 跨页面流程
│   └─ 6.3 渐进展示策略
└─ 7. 页面优先级（3 批次）

页面蓝图文档 (02_core_page_blueprints.md)
├─ 页面 A
│   ├─ 目标与角色
│   ├─ 主/辅工作面
│   ├─ 默认信息排序（首屏优先级）
│   ├─ 核心模块清单
│   ├─ 主 CTA
│   ├─ 与其他页面的关系
│   └─ 线框图（ASCII art）
├─ 页面 B
│   └─ ...
└─ 页面优先级与批次
```

---

## 执行流程

### 全流程（--create）

```
┌─────────────────────────────────────────────────────────┐
│ Phase 0: CONTEXT（上下文采集）                     [sonnet] │
│                                                         │
│   1. 读取现有 spec 文档（00-15）                         │
│   2. 读取产品定位和设计决策                               │
│   3. 读取 00_ditto_product_criteria.md                   │
│   4. 确定本次产出范围                                    │
│   5. [--audit] 对现有文档做完整性评分                      │
├─────────────────────────────────────────────────────────┤
│ Phase 1: RESEARCH（领域调研）                     [混合]    │
│                                                         │
│   并行调研（2 个 Agent）：                               │
│   ├─ IA + Domain Expert Agent                           │
│   │   ├─ 竞品 IA 对比（Bloomberg/Wind/TradingView）      │
│   │   ├─ A 股量化用户典型工作流                          │
│   │   └─ 全资产平台最佳实践                              │
│   └─ Strategist Agent                                   │
│       ├─ 竞品差异化分析                                  │
│       └─ 用户需求趋势                                    │
│                                                         │
│   输出：调研摘要 + 参考架构                              │
├─────────────────────────────────────────────────────────┤
│ Phase 2: DESIGN（并行设计）                     [按角色]   │
│                                                         │
│   启动 4 个并行 Agent：                                  │
│   ├─ Product Strategist  → opus  → 产品范围 + 用户场景  │
│   ├─ Information Architect → opus  → IA 结构 + 蓝图框架 │
│   ├─ UX Strategist       → sonnet → 用户流程 + 交互模式 │
│   └─ Domain Expert       → sonnet → 领域约束 + 术语验证 │
│                                                         │
│   每个角色的输出格式：                                    │
│   - 📋 设计草案（结构化 Markdown）                       │
│   - 🔍 发现的问题/风险                                   │
│   - 💡 创新建议（超越竞品的差异化设计）                   │
├─────────────────────────────────────────────────────────┤
│ Phase 3: SYNTHESIS（冲突协调 + 合成）              [opus]  │
│                                                         │
│   1. 汇总 4 个角色的设计草案                              │
│   2. 解决冲突：                                          │
│      ├─ Strategist vs IA（功能多 vs 结构简）→ 协商        │
│      ├─ IA vs UX（信息分组 vs 交互路径）→ 先定结构       │
│      └─ Domain vs All（专业正确性 vs 易用性）→ 专业优先  │
│   3. Domain Expert 验证领域合理性                        │
│   4. 输出统一设计方案                                    │
│   5. 使用 AskUserQuestion 呈现关键决策点                  │
├─────────────────────────────────────────────────────────┤
│ Phase 4: DOCUMENT（文档产出）                     [sonnet] │
│                                                         │
│   1. 写入/更新目标文档                                    │
│      ├─ 01_product_information_architecture.md           │
│      ├─ 02_core_page_blueprints.md                       │
│      └─ 用户流程 + 术语表（内嵌或独立）                   │
│   2. 更新设计决策（如有架构变更）                         │
│   3. git commit                                          │
├─────────────────────────────────────────────────────────┤
│ Phase 5: VALIDATE（交叉验证）                     [sonnet] │
│                                                         │
│   1. 检查与现有 spec（10-15）的一致性                     │
│   2. 检查与原型的对齐度                                   │
│   3. 检查术语表一致性                                    │
│   4. 输出一致性报告 + 待同步清单                          │
└─────────────────────────────────────────────────────────┘
```

### 审计模式（--audit）

```
CONTEXT [sonnet] → 完整性评分 [4 角色并行] → 问题汇总 → 修复建议 → 输出审计报告
```

**审计维度：**

| 维度 | 检查内容 |
|------|---------|
| 完整性 | IA 文档是否覆盖所有已知页面、蓝图是否覆盖所有页面 |
| 一致性 | 标签/术语是否跨文档一致、层级关系是否有矛盾 |
| 可达性 | 所有页面是否在导航中可达、所有流程是否有出口 |
| 时效性 | 与最新设计决策是否同步、与原型是否对齐 |
| 扩展性 | 新增页面时 IA 是否需要大规模重构 |

### 迭代模式（--iterate）

```
CONTEXT [sonnet] → 读取现有文档 → RESEARCH（轻量） → DESIGN（聚焦变更部分） → SYNTHESIS → DOCUMENT → VALIDATE
```

**迭代范围：**

| 参数 | 聚焦范围 |
|------|---------|
| `--iterate ia` | 仅 IA 文档（导航/结构/标签） |
| `--iterate blueprint` | 仅页面蓝图（模块/优先级/交互） |
| `--iterate flows` | 仅用户流程（路径/分支/渐进展示） |
| `--page <name>` | 仅指定页面（如 markets、trading） |

---

## 审计输出模板

```
# Ditto 产品架构审计报告

## 审计范围
- IA 文档: [版本/状态]
- 蓝图文档: [版本/状态]
- 审计日期: YYYY-MM-DD

## 完整性评分

| 维度 | 评分 | 说明 |
|------|------|------|
| IA 覆盖度 | X/10 | 已知 N 个页面，蓝图覆盖 M 个 |
| 标签一致性 | X/10 | 发现 K 处标签不一致 |
| 导航可达性 | X/10 | 发现 J 个不可达页面/状态 |
| 流程完整性 | X/10 | 核心任务覆盖 L/M |
| 文档同步度 | X/10 | 与设计决策有 D 处不同步 |

## 发现的问题

### P0: 结构性问题
- [问题描述] — [影响] — [建议修复]

### P1: 一致性问题
- [问题描述] — [影响] — [建议修复]

### P2: 优化建议
- [建议内容] — [预期收益]

## 待同步清单
- [ ] [同步项 1]: [源文档] → [目标文档]
- [ ] [同步项 2]: ...
```

---

## 与 ditto-design-cycle 的关系

```
/ditto-product-arch                    /ditto-design-cycle
（上游：定义做什么）                    （下游：创建 UI + 审查迭代）
        │                                      │
        ├─ 产出 IA 文档                        ├─ --create 模式基于蓝图生成 UI 原型
        ├─ 产出页面蓝图                        ├─ IA Specialist 审查流程完整性
        ├─ 产出用户流程                        ├─ Copy Editor 审查标签一致性
        └─ 产出术语表                          └─ 反馈 → 回到 product-arch 优化
```

**关键区别：**
- `/ditto-product-arch`: **产出型** — 定义 IA/蓝图/流程，创建 spec 文档
- `/ditto-design-cycle`: **创建+审查型** — 基于蓝图生成 UI 原型，审查迭代已有设计
