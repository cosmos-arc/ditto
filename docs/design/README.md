> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Ditto 设计文档索引

**版本**: v1.1.0
**最后更新**: 2026-04-27
**状态**: ✅ 稳定

## 概要

本目录包含 Ditto 量化交易系统的架构设计文档。

## 文档概览

| 文档 | 版本 | 日期 | 概要 |
|------|------|------|------|
| [PRD.md](PRD.md) | v2.0 | 2025-12-08 | 产品需求文档 - 项目目标、功能范围、用户故事 |
| [01_system_design.md](01_system_design.md) | v2.1 | 2025-12-26 | 系统架构设计 - 分层架构、目录结构、核心领域模型 |
| [02_data_design.md](02_data_design.md) | v2.0 | 2025-12-26 | 数据层设计 - 存储、PIT、复权、DQ、Runtime |
| [03_engine_design.md](03_engine_design.md) | v2.0 | 历史参考 | 引擎层设计 - Regime、Factor、Backtest、Risk 引擎 |
| [04_deployment_topology.md](04_deployment_topology.md) | v2.1 | 2025-12-26 | 部署拓扑设计 - 单机部署、Prefect 调度、心跳监控 |
| [05_observability.md](05_observability.md) | v2.0 | 2025-12-23 | 可观测性方案 - 日志、追踪、指标、告警、部署 |
| [06_roadmap.md](06_roadmap.md) | v2.0 | 2025-12-08 | 路线图 - Phase 0-3 时间线、里程碑、验收标准 |
| [07_research_playground.md](07_research_playground.md) | v2.0 | 2025-12-08 | 研究环境 - Notebook、实验管理、规格书流程 |
| [08_risk_constitution.md](08_risk_constitution.md) | v1.0 | 2025-12-08 | 风险宪法 - Kill Switch、仓位控制、操作纪律 |
| [09_data_quality_design.md](09_data_quality_design.md) | v1.1 | 2025-12-28 | 数据质量设计 - DQ 三层架构、YAML 配置、隔离区 |
| [10_data_ingestion_scheduler_design.md](10_data_ingestion_scheduler_design.md) | v2.0 | 2025-12-30 | 数据摄取调度 - Prefect Flows/Tasks、T0/T1/T2/T3 分层 |
| [11_interfaces_architecture.md](11_interfaces_architecture.md) | v1.0 | 2026-01-23 | Interfaces 层架构 - FastAPI、Prefect、CLI、DI |
| [12_quant_architecture_alignment.md](12_quant_architecture_alignment.md) | v1.0 | 2026-02-11 | 行业架构对标 - LEAN/Zipline/Qlib 参考设计（历史参考，最新审计见 `docs/reviews/`） |
| [13_golden_dataset_design.md](13_golden_dataset_design.md) | v1.0 | 2026-02-17 | 黄金数据集设计 - 标的选择标准、配置格式、架构设计 |

## 文档分类

### 系统设计

**核心架构文档**：
- [01_system_design.md](01_system_design.md) - 系统整体架构
  - 分层架构（Engine Layer / Data Layer / Application Services / API Layer）
  - 目录结构设计
  - 核心领域模型（StrategyInstance、Signal、RebalancePlan）
  - 关键流程（数据更新、回测、Kill Switch）

### 数据设计

**数据层架构**：
- [02_data_design.md](02_data_design.md) - 数据层设计
  - 混合存储策略（Parquet + SQLite + DuckDB）
  - PIT（Point-in-Time）查询设计
  - 复权因子独立存储
  - DQ（Data Quality）三层架构
  - Runtime Layer 基础设施

**数据质量**：
- [09_data_quality_design.md](09_data_quality_design.md) - 数据质量设计
  - L1 技术校验（非空、唯一、外键）
  - L2 业务规则（OHLC、涨跌幅）
  - L3 统计异常（Z-score、完整性）
  - YAML + Pydantic 配置架构
  - 隔离区机制

**黄金数据集**：
- [13_golden_dataset_design.md](13_golden_dataset_design.md) - 黄金数据集设计
  - 标的选择标准（流动性分层、市场板块、资产类型、特殊场景）
  - YAML 配置格式
  - 分层架构设计（Core / Port）
  - 对账服务集成

**数据摄取**：
- [10_data_ingestion_scheduler_design.md](10_data_ingestion_scheduler_design.md) - 数据摄取调度
  - Prefect 3 本地 Server 模式
  - T0/T1/T2/T3 分层语义
  - Ingestion Service 层设计
  - 任务记录存储（Log + Cursor）
  - Flow/Task 实现示例

### 引擎设计

**核心引擎**：
- [03_engine_design.md](03_engine_design.md) - 引擎层设计（历史参考，最新实现见 `packages/engine/CLAUDE.md`）
  - Regime Engine（市场状态识别）
  - Factor Engine（因子计算）
  - Backtest Engine（回测引擎）
  - Risk Engine（风控引擎）

### 部署与运维

**部署架构**：
- [04_deployment_topology.md](04_deployment_topology.md) - 部署拓扑
  - 单机 Windows 环境部署
  - Prefect Server + Worker 配置
  - 心跳机制设计
  - 数据库并发控制
  - 健康检查端点
  - Runbook（故障处理手册）

**可观测性**：
- [05_observability.md](05_observability.md) - 可观测性方案
  - 日志规范（Loguru + JSON Lines）
  - Trace 规范（OTel + trace_id）
  - Metrics 规范（VictoriaMetrics）
  - 告警规则（P0-P3 分级）
  - Grafana 仪表盘
  - 部署方案（Docker Compose）

### 规划与研究

**产品规划**：
- [PRD.md](PRD.md) - 产品需求文档
  - 项目目标
  - 功能范围
  - 用户故事
  - 验收标准

**路线图**：
- [06_roadmap.md](06_roadmap.md) - 路线图
  - Phase 0：环境与数据打底（~3 周）
  - Phase 0.5：数据质量验证（~2 周）
  - Phase 1：回测闭环（~6 周）
  - Phase 2：实盘接入（~6 周）[未来]
  - Phase 3：ML 增强（~8 周）[未来]

**研究环境**：
- [07_research_playground.md](07_research_playground.md) - 研究环境
  - Notebook 规范
  - 正式实验管理
  - 研究到生产流程
  - 规格书模板
  - 对齐验证

### 风控规范

**风险宪法**：
- [08_risk_constitution.md](08_risk_constitution.md) - 风险宪法
  - 核心原则（不死原则、规则优先）
  - Kill Switch 三级阈值
  - 仓位控制规则
  - 因子健康度门槛
  - 操作纪律
  - 修订程序

## 如何创建新的设计文档

### 1. 确定文档类型

根据文档内容选择合适的分类：
- 系统设计：整体架构、模块设计
- 数据设计：存储、数据流、数据质量
- 引擎设计：具体引擎的实现细节
- 部署与运维：部署架构、监控、告警
- 规划与研究：需求、路线图、研究环境
- 风控规范：风险控制规则

### 2. 创建新文档

```bash
# 在 docs/design/ 目录下创建新文件
# 格式：{编号}_{主题}_{类型}.md
# 示例：
# 11_trading_engine_design.md
# 12_ml_model_integration.md
```

### 3. 文档结构建议

```markdown
# 文档标题

**版本**：v1.0
**日期**：YYYY-MM-DD
**状态**：Draft | Review | Final

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|

## 1. 设计目标与约束

### 1.1 目标
### 1.2 约束

## 2. 架构设计

### 2.1 整体架构
### 2.2 组件设计
### 2.3 接口定义

## 3. 实现方案

### 3.1 关键技术
### 3.2 数据结构
### 3.3 算法逻辑

## 4. 测试与验证

### 4.1 测试策略
### 4.2 验收标准

## 5. 相关文档

- [相关文档1](xxx.md)
- [相关文档2](yyy.md)
```

### 4. 更新索引

在本文件（README.md）的相应分类中添加新文档信息。

### 5. 提交审查

```bash
git add docs/design/11_xxx.md
git commit -m "docs(design): 添加新设计文档 - 文档标题"
```

## 文档状态说明

| 状态 | 说明 |
|------|------|
| **Draft** | 草稿，正在编写中 |
| **Review** | 评审中，征求反馈 |
| **Final** | 最终版，已批准 |

## 相关文档

- [架构决策记录 (ADR)](../adr/README.md) - 重要架构决策
- [Sprint 规划](../sprints/README.md) - 迭代计划
- [计划文档](../plans/README.md) - 具体实施计划
