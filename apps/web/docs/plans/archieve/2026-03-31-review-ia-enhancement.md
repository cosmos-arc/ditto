# Design Cycle IA 增强方案

> **日期**: 2026-03-31
> **状态**: 已实施
> **目标**: 1) Review skill 新增 IA Specialist 角色 2) 新建产品架构产出 skill 3) 扩展为创建+审查双模式

---

## 背景

评估现有 `ditto-design-review` skill，对照 Garrett 五层模型和业界最佳实践（Unicorn Club 5 类审查、Designlab 10 点清单、Nielsen 启发式评估），发现 Structure/Scope 层覆盖不足。

## 变更范围

### 1. Review Skill 改进 → 重命名为 /ditto-design-cycle（4 个文件）

#### roles.md — 新增 IA Specialist 角色

新增第 6 个审查角色，覆盖 4 个检查域：

**信息架构**: 内容分组逻辑、层级深度、导航可达性、标签语义一致性、中英术语对齐

**用户流程**: Happy path 完整性、入口设计、退出/返回路径、错误恢复、死端检测、跨页数据流

**页面蓝图**: 首屏信息优先级、渐进展示、内容边界、信息时效分层

**边界情况**: 长内容处理、短内容处理、极端值处理、多视口信息完整性

模型分配: sonnet（结构化分析，不需要审美判断）

#### review-scoring.md — 从 product-criteria.md 拆分

将审查评分相关内容从 `product-criteria.md` 拆分到 `review-scoring.md`，产品策略部分移入 `design/specs/00_ditto_product_criteria.md`。

新增内容:
- Fixed/Sticky 元素遮挡检测
- 信息密度量化指标
- 量化平台专用准则（数据新鲜度、色觉无障碍、Token 消费率、密度可切换性）
- 各角色补充检查清单

#### product-criteria.md — 拆分

拆分为两个文件:
- `design/specs/00_ditto_product_criteria.md` — 产品策略（模块分层密度、字号映射、间距梯度）
- `.claude/design-review/review-scoring.md` — 审查评分标准

#### ditto-design-cycle.md（原 ditto-design-review.md）— 流程集成 + 创建模式

- **重命名**: ditto-design-review → ditto-design-cycle
- **新增 --create 模式**: Phase 0.5 CREATE，基于 product-arch 产出物生成 UI 原型
- **Phase 0-1 BASELINE**: 增加 IA 上下文采集（读取 IA 文档 + 页面蓝图）
- **Phase 3 PARALLEL REVIEW**: 5 角色 → 6 角色
- **Phase 4 冲突协调**: 增加 IA 参与的冲突规则
  - IA vs AD → 协商，参考 L1/L2/L3 分层
  - IA vs UX → 先 IA 定结构，再 UX 审交互
  - IA vs PM → 协商，IA 可建议"移到其他页面"
- 模型路由表: 增加 IA Specialist 行
- 单角色模式: 增加 `--ia` 参数

### 2. 新 Skill: /ditto-product-arch（2 个文件）

**定位**: 产出和迭代信息架构、页面蓝图、用户流程

**4 角色**:
- Product Strategist (opus) — 产品定位、用户画像、竞争差异化
- Information Architect (opus) — 导航结构、内容分组、标签体系
- UX Strategist (sonnet) — 用户流程、任务分析、交互模式
- Domain Expert (sonnet) — 金融领域知识、A股特性、量化工作流

**产出物**: 01_product_information_architecture.md、02_core_page_blueprints.md、用户流程文档、术语表

**流程**: CONTEXT → RESEARCH → DESIGN → SYNTHESIS → DOCUMENT → VALIDATE

**与 ditto-design-cycle 的关系**:
- product-arch（上游）产出 IA/蓝图 → design-cycle（下游）--create 模式基于蓝图生成 UI 原型
- design-cycle 审查反馈 → product-arch 迭代优化

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `.claude/commands/ditto-design-cycle.md` | 重命名 + 重写（原 ditto-design-review.md） |
| `.claude/commands/ditto-product-arch.md` | 新建 |
| `.claude/design-review/roles.md` | 新增 IA Specialist，PM 瘦身 |
| `.claude/design-review/review-scoring.md` | 新建（从 product-criteria.md 拆分） |
| `.claude/design-review/iterate.md` | 更新引用 |
| `.claude/design-review/sync.md` | 更新引用 |
| `.claude/design-review/templates.md` | 更新引用 |
| `.claude/design-review/product-criteria.md` | 废弃，可删除 |
| `.claude/product-arch/roles.md` | 新建（原 design-review/roles-product-arch.md） |
| `design/specs/00_ditto_product_criteria.md` | 新建（产品策略部分） |

## 参考来源

- Garrett's Elements of User Experience (五层模型)
- Unicorn Club Design Review Framework
- Designlab 10-Point Critique Checklist
- Nielsen's 10 Usability Heuristics
- Bloomberg Terminal / TradingView / Wind IA 分析
