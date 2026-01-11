# 架构决策记录 (Architecture Decision Records)

本目录包含 Ditto 项目的架构决策记录（ADRs）。

## 什么是 ADR？

ADR 记录项目中的重要架构决策，每个 ADR 包含：
- **背景**：驱动该决策的问题或需求
- **决策**：所做出的选择和方案
- **后果**：决策带来的积极和消极影响
- **替代方案**：考虑过但未采用的其他方案

## ADR 索引

| 编号 | 标题 | 状态 | 日期 | 概要 |
|------|------|------|------|------|
| [0000](0000-use-adrs.md) | 使用 ADR 记录架构决策 | Accepted | 2024-01-01 | 说明 ADR 的目的、模板和用法 |
| [0001](0001-project-stack-selection.md) | 项目技术栈选择 | Accepted | 2024-01-01 | 选择 Python 3.11+、Polars、FastAPI、Prefect 等技术栈 |
| [0002](0002-monorepo-structure.md) | Monorepo 结构 | Accepted | 2024-01-01 | 采用 monorepo + packages 分离的代码组织结构 |
| [0003](0003-data-storage-strategy.md) | 数据存储策略 | Accepted | 2024-01-01 | 混合存储：Parquet（时序数据）+ SQLite（元数据）+ DuckDB（分析查询） |

## ADR 编号规则

- 格式：`NNNN-title.md`
- 编号：4 位数字，从 0001 开始递增
- 标题：使用 kebab-case（小写短横线分隔）

## 如何创建新的 ADR

### 1. 创建新文件

```bash
# 在 docs/adr/ 目录下创建新文件
cp docs/adr/0000-use-adrs.md docs/adr/0004-new-decision.md
```

### 2. 填写内容

使用以下模板：

```markdown
# NNNN - 决策标题

**状态**：Accepted | Proposed | Deprecated | Superseded

**日期**：YYYY-MM-DD

## 背景

为什么要做这个决策？问题是什么？

## 决策

我们选择什么方案？

## 后果

**积极面**：
- 好处 1
- 好处 2

**消极面**：
- 代价 1
- 代价 2

## 考虑的替代方案

### 方案 A
描述及拒绝原因

### 方案 B
描述及拒绝原因

## 相关决策
- [ADR NNNN - 相关决策标题](0004-new-decision.md)
```

### 3. 更新索引

在本文件（README.md）的 ADR 索引表中添加新记录。

### 4. 提交审查

```bash
git add docs/adr/0004-new-decision.md
git commit -m "docs(adr): 添加新决策记录 - 决策标题"
```

## ADR 状态说明

| 状态 | 说明 |
|------|------|
| **Proposed** | 提议中，正在讨论 |
| **Accepted** | 已采纳，当前生效 |
| **Deprecated** | 已废弃，不再推荐但可能仍在使用 |
| **Superseded** | 已被新决策取代 |

## 相关文档

- [设计文档](../design/README.md) - 系统架构设计
- [Sprint 规划](../sprints/README.md) - 迭代计划
- [ADR 最佳实践](https://adr.github.io/) - 官方 ADR 规范参考
