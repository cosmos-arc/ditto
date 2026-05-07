> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR 决策索引

> Unified Feature/Factor Engine 的架构决策记录（ADR），按主题归组。

## 状态图例

| 标记 | 含义 |
|------|------|
| ✅ | 已决策 |
| ⏸️ | 暂缓（有重启条件） |
| ❌ | 已废弃 |

---

## 阅读路径

### 新成员入门

从核心模型开始，理解系统的语义基础：

```
ADR-032 → ADR-024 → ADR-034 → ADR-035
(语义模型) → (版本控制) → (发布生命周期) → (失效级联)
```

### 计算引擎

理解表达式引擎和算子设计：

```
ADR-014 → ADR-002 → ADR-004 → ADR-006
(引擎核心) → (算子系统) → (表达式语法) → (增量计算)
```

### 数据存储

理解存储架构和冷热分层：

```
ADR-026 → ADR-028 → ADR-040 → ADR-031
(DuckDB) → (QuestDB 热表) → (冷热保留) → (状态快照)
```

### 数据质量

```
ADR-021 → ADR-022 → ADR-036 → ADR-037
(PIT 一致性) → (修正处理) → (质量门禁) → (性能 SLO)
```

### Research 数据集

```
ADR-041 → ADR-042 → ADR-043
(Spine 契约) → (Shadow 发布) → (认证兼容)
```

---

## 主题归组

### 核心模型 — [core/](core/)

| ADR | 标题 | 状态 |
|-----|------|------|
| [ADR-032](core/adr-032-unified-derived-semantic-model.md) | 统一派生语义模型 | ✅ |
| [ADR-024](core/adr-024-factor-versioning.md) | 因子版本控制 | ✅ |
| [ADR-034](core/adr-034-publication-lifecycle.md) | 发布生命周期 | ✅ |

### 计算引擎 — [computation/](computation/)

| ADR | 标题 | 状态 |
|-----|------|------|
| [ADR-002](computation/adr-002-operator-system.md) | 算子系统 | ✅ |
| [ADR-004](computation/adr-004-expression-syntax.md) | 表达式语法 | ✅ |
| [ADR-006](computation/adr-006-incremental-computation.md) | 增量计算 | ✅ |
| [ADR-012](computation/adr-012-operator-incremental-impl.md) | 算子增量实现 | ✅ |
| [ADR-014](computation/adr-014-expression-engine-core.md) | 表达式引擎核心 | ✅ |
| [ADR-038](computation/adr-038-operator-versioning.md) | 算子版本控制 | ✅ |
| [ADR-039](computation/adr-039-expression-cache-persistence.md) | 表达式缓存持久化 | ✅ |

### 存储架构 — [storage/](storage/)

| ADR | 标题 | 状态 |
|-----|------|------|
| [ADR-026](storage/adr-026-duckdb-positioning.md) | DuckDB 定位 | ✅ |
| [ADR-027](storage/adr-027-pushdown-strategy.md) | 表达式 Pushdown 策略 | ✅ |
| [ADR-028](storage/adr-028-questdb-hot-tables.md) | QuestDB 热表设计 | ✅ |
| [ADR-031](storage/adr-031-state-snapshot-abi.md) | State Snapshot ABI | ✅ |
| [ADR-040](storage/adr-040-hot-cold-retention-state-namespace-policy.md) | 冷热保留与状态命名空间 | ✅ |

### 数据质量 — [quality/](quality/)

| ADR | 标题 | 状态 |
|-----|------|------|
| [ADR-021](quality/adr-021-pit-consistency.md) | PIT 一致性 | ✅ |
| [ADR-022](quality/adr-022-correction-handling.md) | 修正处理 | ✅ |
| [ADR-036](quality/adr-036-quality-gates.md) | 质量门禁 | ✅ |
| [ADR-037](quality/adr-037-performance-slo.md) | 性能 SLO | ✅ |

### Research 数据集 — [research/](research/)

| ADR | 标题 | 状态 |
|-----|------|------|
| [ADR-041](research/adr-041-research-dataset-spine-availability-contract.md) | Research Dataset Spine 契约 | ✅ |
| [ADR-042](research/adr-042-shadow-publish-dual-read-diff-protocol.md) | Shadow 发布双读比对协议 | ✅ |
| [ADR-043](research/adr-043-role-profile-certification-compatibility-manifest.md) | 角色/Profile/认证兼容清单 | ✅ |

---

## 综合与流程

| ADR | 标题 | 状态 |
|-----|------|------|
| [ADR-001](adr-001-ts-cs-nesting.md) | 时序-截面嵌套 | ✅ |
| [ADR-003](adr-003-technical-indicators.md) | 技术指标 | ✅ |
| [ADR-005](adr-005-first-batch-features.md) | 第一批功能 | ✅ |
| [ADR-007](adr-007-operator-catalog.md) | 算子目录 | ✅ |
| [ADR-008](adr-008-normalization-pipeline.md) | 标准化管道 | ✅ |
| [ADR-009](adr-009-ingestion-flow.md) | 摄入流程 | ✅ |
| [ADR-010](adr-010-catalog-schema.md) | 目录 Schema | ✅ |
| [ADR-013](adr-013-ts-rank-precision.md) | 时序排名精度 | ✅ |
| [ADR-015](adr-015-dag-optimization.md) | DAG 优化 | ✅ |

## 服务与运维

| ADR | 标题 | 状态 |
|-----|------|------|
| [ADR-017](adr-017-factor-service-api.md) | 因子服务 API | ✅ |
| [ADR-018](adr-018-monitoring-alerting.md) | 监控告警 | ✅ |
| [ADR-019](adr-019-testing-strategy.md) | 测试策略 | ✅ |
| [ADR-020](adr-020-deployment-ops.md) | 部署运维 | ✅ |
| [ADR-023](adr-023-disaster-recovery.md) | 灾备恢复 | ⏸️ |
| [ADR-029](adr-029-intraday-postmarket-paths.md) | 盘中/盘后路径 | ✅ |
| [ADR-030](adr-030-online-data-access-boundary.md) | Online 数据访问边界 | ✅ |

## 查询架构

| ADR | 标题 | 状态 |
|-----|------|------|
| [ADR-033](adr-033-derived-query-architecture.md) | 派生查询架构 | ✅ |
| [ADR-035](adr-035-invalidation-cascade.md) | 失效传播级联 | ✅ |

## 暂缓

| ADR | 标题 | 重启条件 |
|-----|------|---------|
| [ADR-011](adr-011-streaming-mode.md) | 盘中微批量处理模式 | QuestDB + Kvrocks 基础设施就绪后重启 |
| [ADR-023](adr-023-disaster-recovery.md) | 灾备恢复 | 确认上游数据源支持断点续传后重启 |

## 已废弃

| ADR | 标题 | 替代 | 说明 |
|-----|------|------|------|
| ADR-016 | 目录存储 | [ADR-010](adr-010-catalog-schema.md) | 2026-03-07 合并到 ADR-010 |
| ADR-025 | DuckDB 统一架构 | [ADR-026](storage/adr-026-duckdb-positioning.md) | 已删除，由 ADR-026 替代 |
