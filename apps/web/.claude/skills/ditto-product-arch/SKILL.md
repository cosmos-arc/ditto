---
name: ditto-product-arch
description: 产品架构设计与迭代编排——信息架构、页面蓝图、用户流程的产出与优化。四角色并行设计 + Phase Gate + 上游 Discovery 消费 + Constitution 合规验证。上游: /ditto-product-discovery，下游: /ditto-design-cycle。
disable-model-invocation: true
---

# /ditto-product-arch

产品架构设计与迭代编排。通过四角色并行设计产出 **信息架构、页面蓝图、用户流程**，确保符合业界顶级量化平台标准。

> **定位**: Pipeline 0。上游消费 `ditto-product-discovery` 产出物，下游输出给 `ditto-design-cycle`。
> **产出物是 spec 文档，不是代码。**

---

## 确定性约束 (MUST / MUST NOT)

- 文件路径 MUST 为 `docs/designs/specs/01_product_information_architecture.md` 和 `02_core_page_blueprints.md`
- 模型路由 MUST 按 [agent-protocol.md](references/agent-protocol.md) 执行
- Phase Gate MUST 在 Gate 0→1、Gate 2→3、Gate 4→5 执行
- 每个页面 MUST 包含: Tab Content Sections + Overlay Registry + Component × State Matrix + Page Contract Mapping（缺失 = 不完整）
- 破坏性操作 MUST 在 Overlay Registry 中有 Confirm Dialog
- 数据组件 MUST 在 State Matrix 中定义 loading/empty/failed 三态
- shellFamily MUST 取 7 枚举值之一（见 [enums.md](references/enums.md)）
- pagePattern MUST 取 8 枚举值之一（见 [enums.md](references/enums.md)）
- 模块→Slot 映射中 shell 级区块 MUST 取自 SHELL_SLOT_MAP，页面级 MUST 用 kebab-case
- Constitution 23 条约束 MUST NOT 违反（P0 违规 MUST 修复才能通过 Gate）
- Phase 5 MUST 输出审计报告（6 维评分 + 合规报告 + 覆盖率报告）
- `.arch-manifest.json` MUST 在每个 Phase 完成后更新
- 无 discovery 产出物时 MUST 输出警告但允许继续

---

## 创意指导 (SHOULD / CONSIDER)

- **参考但不复制** Bloomberg/Wind/TradingView 的 IA，做出更好的选择
- **Workflow-first**: 按"用户做什么"组织，而非按"技术模块"组织
- **Context-persistent**: 选中资产后，在所有视图中保持上下文
- **Search-first**: 语义搜索作为最快的跨资产路径
- 四角色 SHOULD 给出**冲突的建议**（功能多 vs 结构简、专业正确性 vs 易用性）
- Claude 负责呈现冲突 + 分析权衡 + 推荐折中方案
- **用户是最终决策者**

---

## Reference 文件

| 文件 | 内容 |
|------|------|
| [roles.md](references/roles.md) | 四角色定义、审查清单、产出物分配 |
| [output-structure.md](references/output-structure.md) | IA 文档模板、Blueprint 模板、审计报告模板 |
| [enums.md](references/enums.md) | shellFamily/pagePattern 枚举、映射规则、通用状态清单 |
| [validation-rules.md](references/validation-rules.md) | 6 维审计规则、Constitution 合规检查、覆盖率报告格式 |
| [agent-protocol.md](references/agent-protocol.md) | 模型路由、Agent dispatch、冲突协调、Phase Gate 规范 |

---

## 输入

`$ARGUMENTS` — 设计目标 + 可选参数

```bash
/ditto-product-arch --create                    # 首次创建全套文档
/ditto-product-arch --create --focus a-share     # 聚焦特定领域
/ditto-product-arch --iterate ia                 # 迭代优化信息架构
/ditto-product-arch --iterate blueprint           # 迭代优化页面蓝图
/ditto-product-arch --iterate blueprint --page markets  # 聚焦特定页面
/ditto-product-arch --iterate flows              # 迭代优化用户流程
/ditto-product-arch --audit                      # 审计现有文档
/ditto-product-arch --phase N                    # 从 Phase N 恢复
```

---

## 上游消费

检测 `.discovery-manifest.json`，自动注入到对应 Phase：

| 上游产出物 | 注入 Phase | 注入方式 |
|-----------|-----------|---------|
| system-description entities/capabilities | Phase 1 RESEARCH | Agent prompt |
| constitution 23 条约束 | Phase 2 DESIGN + Phase 5 VALIDATE | Agent prompt + 验证 |
| assumptions 高风险项 | Phase 3 SYNTHESIS | 冲突协调标记 |
| landscape 竞品矩阵 | Phase 1 RESEARCH | Agent prompt |

无 discovery 时: `⚠️ 未检测到 discovery 产出物，建议先运行 /ditto-product-discovery`

---

## 执行流程

### 全流程 (--create)

```
Phase 0: CONTEXT [sonnet]
  ├─ 检测上游 discovery manifest + digest
  ├─ 读取现有 spec 文档（00-15）
  ├─ 确定本次产出范围
  ├─ 初始化 .arch-manifest.json
  └─ [--audit] 对现有文档做完整性评分

── Gate 0→1: 上游摘要 + 范围确认 ──

Phase 1: RESEARCH [混合]
  ├─ 注入: entities/capabilities + landscape
  ├─ 并行 2 Agent: IA+Domain / Strategist
  └─ 输出: 调研摘要 + 参考架构

Phase 2: DESIGN [按角色]
  ├─ 注入: constitution 约束到每个角色 prompt
  ├─ 并行 4 Agent（见 agent-protocol.md）
  │   ├─ Product Strategist  [opus]  → 产品范围 + 用户场景
  │   ├─ Information Architect [opus] → IA 结构 + 蓝图框架
  │   ├─ UX Strategist       [sonnet] → 流程 + 交互 + 4 项状态定义
  │   └─ Domain Expert       [sonnet] → 领域约束 + 术语验证
  └─ 输出: 4 份设计草案

── Gate 2→3: 冲突清单 + 违规预警 ──

Phase 3: SYNTHESIS [opus]
  ├─ 注入: 高风险假设
  ├─ 冲突协调（见 agent-protocol.md 冲突规则）
  ├─ Domain Expert 验证领域合理性
  └─ AskUserQuestion 呈现关键决策点

Phase 4: DOCUMENT [sonnet]
  ├─ 写入 00_ditto_product_criteria.md（密度准则/字号映射/间距梯度/色彩原则/品牌锚定）
  ├─ 写入 01_product_information_architecture.md
  ├─ 写入 02_core_page_blueprints.md（MUST 含 4 项状态定义 + Token Requirements 章节）
  ├─ 写入 04_interaction_state_spec.md（通用状态定义 + 页面状态映射 + 转换规则）
  ├─ 更新设计决策（如有架构变更）
  └─ 更新 manifest

── Gate 4→5: 变更摘要 + 合规报告 ──

Phase 5: VALIDATE [sonnet]
  ├─ 6 维审计（见 validation-rules.md）
  ├─ Constitution 合规检查（逐条）
  ├─ 状态覆盖率报告
  ├─ 页面合同映射完整性验证
  └─ 输出审计报告 + manifest 完成 + git commit
```

### 审计模式 (--audit)

`CONTEXT → 4 角色并行评分 → 问题汇总 → 修复建议 → 审计报告`

### 迭代模式 (--iterate)

`CONTEXT → 轻量 RESEARCH → 聚焦 DESIGN → SYNTHESIS → DOCUMENT → VALIDATE`

---

## 四角色速览

| 角色 | model | 核心关注 |
|------|-------|---------|
| Product Strategist | opus | 产品定位、用户画像、竞争差异化、功能边界 |
| Information Architect | opus | 导航结构、内容分组、标签体系、跨页关系 |
| UX Strategist | sonnet | 用户流程、交互模式、渐进展示、状态定义 |
| Domain Expert | sonnet | 金融领域知识、A 股特性、量化工作流 |

完整角色定义、审查清单、产出物分配见 [roles.md](references/roles.md)。

---

## 产出物

| 产出物 | 路径 | 说明 |
|--------|------|------|
| 产品准则 | [00_ditto_product_criteria.md](../../../docs/designs/specs/00_ditto_product_criteria.md) | 密度准则、字号映射、间距梯度、色彩原则、品牌锚定 |
| 信息架构 | [01_product_information_architecture.md](../../../docs/designs/specs/01_product_information_architecture.md) | 全局 IA、导航、页面层级、流程、术语 |
| 页面蓝图 | [02_core_page_blueprints.md](../../../docs/designs/specs/02_core_page_blueprints.md) | 每页模块、交互、Tab Content、Overlay、State Matrix、Contract Mapping、Token Requirements |
| 状态规范 | [04_interaction_state_spec.md](../../../docs/designs/specs/04_interaction_state_spec.md) | 通用状态定义、页面状态映射、状态转换规则、Skeleton/Toast/Error boundary |
| 用户流程 | （内嵌于 IA 或独立） | 核心任务端到端路径 |
| 术语表 | （内嵌于 IA 或独立） | 统一标签/术语/中英对齐 |

产出物结构模板见 [output-structure.md](references/output-structure.md)。

---

## Pipeline 关系

```
/ditto-product-discovery (Pipeline -1)  →  /ditto-product-arch (Pipeline 0)
       │                                        │
       ├─ Product Brief                         ├─ 消费 Brief + Research
       ├─ Constitution ──── 注入 DESIGN+VALIDATE ┤
       ├─ System Description ── 注入 RESEARCH ──┤
       ├─ Assumptions ─── 注入 SYNTHESIS ──────┤
       └─ Landscape ───── 注入 RESEARCH ───────┘
                                                │
                              /ditto-design-cycle (Pipeline 1)
                              /ditto-page-contract (Pipeline 2)
                              /ditto-app-dev (Pipeline 3)
```
