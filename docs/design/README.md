> **⚠️ Historical Document**: 本目录（除 `unified-feature-factor-engine/` 子目录）为旧架构（engine/analytics/infra/interfaces）时期的设计文档，已于 2026-07-15 归档至 [`archive/`](archive/)。
> **当前架构**请参阅各包 `CLAUDE.md` 与 [`docs/architecture/`](../architecture/README.md)。

# Ditto 设计文档索引

## 当前设计

| 文档 | 用途 |
|------|------|
| [unified-feature-factor-engine/](../../packages/features/docs/design/unified-feature-factor-engine/README.md) | 统一因子/特征引擎设计（表达式编译、物化、IC、PIT 一致性） |

## 归档设计（旧架构时期）

以下文档撰写于旧 engine/analytics/infra/interfaces 架构时期，已于 2026-07-15 归档至 [`archive/`](archive/)，仅作历史参考：

| 文档 | 主题 |
|------|------|
| [archive/PRD.md](archive/PRD.md) | 产品需求文档（产品路线已被 [母版路线图](../roadmaps/ditto-development-roadmap.md) 取代） |
| [archive/01_system_design.md](archive/01_system_design.md) | 旧系统架构（分层、目录、领域模型） |
| [archive/02_data_design.md](archive/02_data_design.md) | 旧数据层（存储、PIT、复权、DQ） |
| [archive/03_engine_design.md](archive/03_engine_design.md) | 旧引擎层（Regime/Factor/Backtest/Risk） |
| [archive/04_deployment_topology.md](archive/04_deployment_topology.md) | 旧部署拓扑 |
| [archive/05_observability.md](archive/05_observability.md) | 旧可观测性方案 |
| [archive/06_roadmap.md](archive/06_roadmap.md) | 旧路线图（Phase 0-3） |
| [archive/07_research_playground.md](archive/07_research_playground.md) | 旧研究环境 |
| [archive/08_risk_constitution.md](archive/08_risk_constitution.md) | 风险宪法 |
| [archive/09_data_quality_design.md](archive/09_data_quality_design.md) | 旧 DQ 设计 |
| [archive/10_data_ingestion_scheduler_design.md](archive/10_data_ingestion_scheduler_design.md) | 旧摄取调度 |
| [archive/11_interfaces_architecture.md](archive/11_interfaces_architecture.md) | 旧 Port 层架构 |
| [archive/12_quant_architecture_alignment.md](archive/12_quant_architecture_alignment.md) | 行业架构对标（LEAN/Zipline/Qlib） |
| [archive/13_golden_dataset_design.md](archive/13_golden_dataset_design.md) | 黄金数据集设计 |

## 相关文档

- [架构规范](../architecture/README.md) — 当前架构权威来源
- [ADR](../adr/README.md) — 架构决策记录
- [计划文档](../plans/README.md) — 实施计划
