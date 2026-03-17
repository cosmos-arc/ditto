# Ditto 统一特征/因子引擎设计文档

本目录包含 unified-feature-factor-engine 的主设计、局部 ADR、参考资料与历史评审文档。

> **当前事实基础**:
> 1. [main-design.md](main-design.md)
> 2. [ADR-032 ~ ADR-043](#统一派生模型与控制面)
> 3. [2026-03-13-unified-feature-factor-engine-remediation-design.md](../../plans/2026-03-13-unified-feature-factor-engine-remediation-design.md)
>
> 其中若存在历史文档与上述内容冲突，以较新的 ADR 与整改方案为准。

## 文档结构

```
docs/design/unified-feature-factor-engine/
├── README.md           # 本文件 - 文档索引
├── main-design.md      # 主设计文档 - 基线架构与核心设计
├── issues.md           # 历史问题清单（不再作为当前真相源）
├── design-analysis-report.md  # 历史分析报告（仅供参考）
├── optimization-review.md     # 历史优化评审（仅供参考）
├── optimization-backlog.md    # 历史优化 backlog（仅供参考）
├── decisions/          # 设计决策记录（局部）
│   ├── adr-001-ts-cs-nesting.md
│   ├── ...
│   ├── core/
│   │   ├── adr-024-factor-versioning.md
│   │   ├── adr-032-unified-derived-semantic-model.md
│   │   └── adr-034-publication-lifecycle.md
│   ├── computation/
│   │   ├── adr-002-operator-system.md
│   │   ├── ...
│   │   ├── adr-038-operator-versioning.md
│   │   └── adr-039-expression-cache-persistence.md
│   ├── storage/
│   │   ├── adr-026-duckdb-positioning.md
│   │   ├── adr-027-pushdown-strategy.md
│   │   ├── adr-028-questdb-hot-tables.md
│   │   ├── adr-031-state-snapshot-abi.md
│   │   └── adr-040-hot-cold-retention-state-namespace-policy.md
│   ├── quality/
│   │   ├── adr-021-pit-consistency.md
│   │   ├── adr-022-correction-handling.md
│   │   ├── adr-036-quality-gates.md
│   │   └── adr-037-performance-slo.md
│   ├── research/
│   │   ├── adr-041-research-dataset-spine-availability-contract.md
│   │   ├── adr-042-shadow-publish-dual-read-diff-protocol.md
│   │   └── adr-043-role-profile-certification-compatibility-manifest.md
│   └── archive/
├── archive/            # 已归档的 gap / checklist / 历史文档
└── reference/          # 参考资料
    ├── factor-expression-syntax.md  # 因子表达式语法参考
    ├── operator-reference.md        # 算子参考手册
    ├── catalog-schema.md            # Catalog 表结构参考
    ├── industry-benchmarks.md       # 业界对标分析
    ├── worldquant-alpha101.md       # WorldQuant Alpha101 参考
    └── technical-implementation.md  # 技术实现参考
```

> **注意**: 本目录的 `decisions/` 是设计文档的局部决策记录，项目级 ADR 仍以 [docs/adr/](../../adr/) 为准。

## 主设计文档

[main-design.md](main-design.md) 包含完整的系统架构设计，涵盖：

- **设计目标与非目标** - 明确引擎的职责边界
- **架构评估** - 用户方案的评估与最终决策
- **仓库现状对齐** - 与现有代码库的兼容性分析
- **最终架构** - 分层职责与端到端数据流
- **模块设计** - 文件落点与目录结构
- **统一模型契约** - Spec/RunConfig/Result 模型
- **表达式引擎设计** - Pratt 编译链路
- **执行模型** - FeatureEngine/FactorEngine
- **全量/增量算法** - 一体化计算策略
- **PIT 语义** - Point-in-Time 实现
- **存储与 Catalog** - 分层存储与元数据管理
- **并发与原子提交** - 锁策略与故障恢复
- **集成策略** - 与现有摄取流程的集成
- **观测性** - 指标、日志、质量门禁
- **实施计划** - 三阶段落地路线图

## 当前推荐阅读顺序

1. [main-design.md](main-design.md)
2. [ADR-032](decisions/core/adr-032-unified-derived-semantic-model.md) ~ [ADR-043](decisions/research/adr-043-role-profile-certification-compatibility-manifest.md)
3. [2026-03-13-unified-feature-factor-engine-remediation-design.md](../../plans/2026-03-13-unified-feature-factor-engine-remediation-design.md)

如果当前任务与以下主题相关，建议优先查看新增 ADR 与整改方案：

- 文档真相源收敛
- retention / state namespace: [ADR-040](decisions/storage/adr-040-hot-cold-retention-state-namespace-policy.md)
- research dataset / spine / availability-time: [ADR-041](decisions/research/adr-041-research-dataset-spine-availability-contract.md)
- shadow publish / dual-read diff: [ADR-042](decisions/research/adr-042-shadow-publish-dual-read-diff-protocol.md)
- role/profile certification / compatibility manifest: [ADR-043](decisions/research/adr-043-role-profile-certification-compatibility-manifest.md)

## 历史参考文档

以下文档保留评审轨迹与设计演化信息，但**不再作为当前事实基础**：

- [issues.md](issues.md)
- [design-analysis-report.md](design-analysis-report.md)
- [optimization-review.md](optimization-review.md)
- [optimization-backlog.md](optimization-backlog.md)
- [revision-questdb-hot-layer.md](revision-questdb-hot-layer.md)
- [archive/](archive/)

## 决策索引

### 核心架构决策

| 编号 | 标题 | 状态 | 摘要 |
|------|------|------|------|
| [ADR-001](decisions/adr-001-ts-cs-nesting.md) | TS/CS 嵌套策略 | ✅ 已决策 | 自动分层执行 + 语义向上传播 |
| [ADR-002](decisions/computation/adr-002-operator-system.md) | 算子体系设计 | ✅ 已决策 | 52 个算子（P0/P1/P2）+ WorldQuant 风格命名 |
| [ADR-003](decisions/adr-003-technical-indicators.md) | 技术指标 vs 算子架构 | ✅ 已决策 | 技术指标作为算子实现，不单独建模 |
| [ADR-004](decisions/computation/adr-004-expression-syntax.md) | 表达式语法与数据引用 | ✅ 已决策 | 列引用、算子调用、运算符优先级 |
| [ADR-005](decisions/adr-005-first-batch-features.md) | 首批特征与因子清单 | ✅ 已决策 | Phase 0 需要实现的因子列表 |
| [ADR-006](decisions/computation/adr-006-incremental-computation.md) | 增量计算策略 | ✅ 已决策 | Watermark + Invalidation 机制 |
| [ADR-007](decisions/adr-007-operator-catalog.md) | 算子完整清单 | ✅ 已决策 | 所有算子的属性和签名 |
| [ADR-008](decisions/adr-008-normalization-pipeline.md) | 标准化管线设计 | ✅ 已决策 | Rank → ZScore（WorldQuant 风格） |

### 增量与存储

| 编号 | 标题 | 状态 | 摘要 |
|------|------|------|------|
| [ADR-009](decisions/adr-009-ingestion-flow.md) | 特征/因子摄取完整流程 | ✅ 已决策 | 与现有摄入层的集成方式 |
| [ADR-010](decisions/adr-010-catalog-schema.md) | Catalog 完整表结构与存储架构 | ✅ 已决策 | SQLite + Kvrocks 混合方案（含治理字段） |
| [ADR-011](decisions/adr-011-streaming-mode.md) | 流式模式架构设计 | ⏸️ Phase 2 | 流批一体架构设计 |
| [ADR-012](decisions/computation/adr-012-operator-incremental-impl.md) | 算子增量实现架构 | ✅ 已决策 | 5 层分类 + sortedcontainers |
| [ADR-013](decisions/adr-013-ts-rank-precision.md) | ts_rank 精度策略 | ✅ 已决策 | 始终精确计算 + 完整窗口 |
| [ADR-014](decisions/computation/adr-014-expression-engine-core.md) | 表达式引擎核心设计 | ✅ 已决策 | Polars Expr + 严格 null |
| [ADR-015](decisions/adr-015-dag-optimization.md) | DAG 优化策略 | ✅ 已决策 | 串行执行 + Lazy 内存管理 |
| ~~ADR-016~~ | ~~Catalog 存储架构~~ | ❌ 已废弃 | 合并到 ADR-010 |

### 服务与运维

| 编号 | 标题 | 状态 | 摘要 |
|------|------|------|------|
| [ADR-017](decisions/adr-017-factor-service-api.md) | 因子服务 API | ✅ 已决策 | 声明式 + 异步优先 + Prefect |
| [ADR-018](decisions/adr-018-monitoring-alerting.md) | 监控与告警 | ✅ 已决策 | VictoriaMetrics + Grafana |
| [ADR-019](decisions/adr-019-testing-strategy.md) | 测试策略 | ✅ 已决策 | 单元/集成/E2E + 内存后端 |
| [ADR-020](decisions/adr-020-deployment-ops.md) | 部署与运维设计 | ✅ 已决策 | Docker Compose + testcontainers |
| [ADR-021](decisions/quality/adr-021-pit-consistency.md) | PIT 一致性与因子引擎集成 | ✅ 已决策 | StoreSchema.pit_columns 集成 |
| [ADR-022](decisions/quality/adr-022-correction-handling.md) | 更正数据处理 | ✅ 已决策 | 数据集级依赖 + DAG 级联 |
| [ADR-023](decisions/adr-023-disaster-recovery.md) | 灾备恢复策略 | ⏸️ 暂缓 | 依赖存储引擎自身持久化 |
| [ADR-024](decisions/core/adr-024-factor-versioning.md) | 因子版本管理 | ✅ 已决策 | Git 分支指针模型 |
| [ADR-025](decisions/adr-025-duckdb-unified-architecture.md) | DuckDB 统一数据架构 | ❌ 已废弃 | 改用 ADHOC 定位（ADR-026） |
| [ADR-026](decisions/storage/adr-026-duckdb-positioning.md) | DuckDB 定位与使用规范 | ✅ 已决策 | ADHOC/审计工具，不做常驻服务 |
| [ADR-027](decisions/storage/adr-027-pushdown-strategy.md) | 表达式 Pushdown 策略 | ✅ 已决策 | 三层判定：能力层 + 模式层 + 开关层 |
| [ADR-028](decisions/storage/adr-028-questdb-hot-tables.md) | QuestDB 热表与物化视图 DDL | ✅ 已决策 | 热表设计、 TTL 策略、 SAMPLE BY |
| [ADR-029](decisions/adr-029-intraday-postmarket-paths.md) | 盘中实时路径与盘后批量路径 | ✅ 已决策 | 因子分级（SERIES/STATE/DERIVE/OFFLINE） |
| [ADR-030](decisions/adr-030-online-data-access-boundary.md) | Online Data Access Boundary | ✅ 已决策 | Parquet 隔离 + 运行时模式 + 可观测性 |
| [ADR-031](decisions/storage/adr-031-state-snapshot-abi.md) | State Snapshot ABI | ✅ 已决策 | 简单状态用 Hash， 复杂状态用 Blob |

### 统一派生模型与控制面

| 编号 | 标题 | 状态 | 摘要 |
|------|------|------|------|
| [ADR-032](decisions/core/adr-032-unified-derived-semantic-model.md) | 统一派生语义模型 | ✅ 已决策 | DerivedSpec 完整字段、entity_keys、TimeSpec |
| [ADR-033](decisions/adr-033-derived-query-architecture.md) | 派生查询架构与层边界 | ✅ 已决策 | Port Facade / DataHub 职责划分、查询边界 |
| [ADR-034](decisions/core/adr-034-publication-lifecycle.md) | Derived 发布生命周期协议 | ✅ 已决策 | 5 状态机、发布/回滚协议 |
| [ADR-035](decisions/adr-035-invalidation-cascade.md) | 失效传播级联协议 | ✅ 已决策 | 级联深度 5、异步传播、循环检测 |
| [ADR-036](decisions/quality/adr-036-quality-gates.md) | DQ 门禁设计 | ✅ 已决策 | Schema/空值率/新鲜度门禁、按 role 分层 |
| [ADR-037](decisions/quality/adr-037-performance-slo.md) | 性能 SLO 定义 | ✅ 已决策 | Phase 1 测量框架、SLI 指标、CI 回归预算 |
| [ADR-038](decisions/computation/adr-038-operator-versioning.md) | 算子版本管理 | ✅ 已决策 | SemVer 版本号、变更日志、Spec 快照 |
| [ADR-039](decisions/computation/adr-039-expression-cache-persistence.md) | 表达式缓存持久化 | ✅ 已决策 | L1 内存 + L2 SQLite 两级缓存 |
| [ADR-040](decisions/storage/adr-040-hot-cold-retention-state-namespace-policy.md) | Hot/Cold Retention 与 State Namespace 策略 | ✅ 已决策 | 默认 TTL、分钟冷回放窗口、Kvrocks namespace |
| [ADR-041](decisions/research/adr-041-research-dataset-spine-availability-contract.md) | Research Dataset、Spine 与 Availability-Time 契约 | ✅ 已决策 | 研究左表契约、PIT join、DatasetSnapshot |
| [ADR-042](decisions/research/adr-042-shadow-publish-dual-read-diff-protocol.md) | Shadow Publish 与 Dual-Read Diff 协议 | ✅ 已决策 | 影子发布、双读对拍、DiffReport / TraceReport |
| [ADR-043](decisions/research/adr-043-role-profile-certification-compatibility-manifest.md) | Role/Profile Certification 与 Compatibility Manifest | ✅ 已决策 | 分层认证包、发布兼容契约 |

## 快速导航

### 按主题

- **表达式引擎**: [ADR-004](decisions/computation/adr-004-expression-syntax.md), [ADR-014](decisions/computation/adr-014-expression-engine-core.md)
- **算子系统**: [ADR-002](decisions/computation/adr-002-operator-system.md), [ADR-007](decisions/adr-007-operator-catalog.md), [ADR-012](decisions/computation/adr-012-operator-incremental-impl.md)
- **增量计算**: [ADR-006](decisions/computation/adr-006-incremental-computation.md), [ADR-012](decisions/computation/adr-012-operator-incremental-impl.md), [ADR-015](decisions/adr-015-dag-optimization.md)
- **数据一致性**: [ADR-021](decisions/quality/adr-021-pit-consistency.md), [ADR-022](decisions/quality/adr-022-correction-handling.md)
- **存储架构**: [ADR-010](decisions/adr-010-catalog-schema.md)（已合并 ADR-016）
- **版本管理**: [ADR-024](decisions/core/adr-024-factor-versioning.md), [ADR-038](decisions/computation/adr-038-operator-versioning.md)
- **部署运维**: [ADR-020](decisions/adr-020-deployment-ops.md), [ADR-023](decisions/adr-023-disaster-recovery.md)
- **统一派生模型**: [ADR-032](decisions/core/adr-032-unified-derived-semantic-model.md), [ADR-033](decisions/adr-033-derived-query-architecture.md)
- **控制面协议**: [ADR-034](decisions/core/adr-034-publication-lifecycle.md), [ADR-035](decisions/adr-035-invalidation-cascade.md), [ADR-036](decisions/quality/adr-036-quality-gates.md)
- **性能与缓存**: [ADR-037](decisions/quality/adr-037-performance-slo.md), [ADR-039](decisions/computation/adr-039-expression-cache-persistence.md)
- **Retention 与状态生命周期**: [ADR-028](decisions/storage/adr-028-questdb-hot-tables.md), [ADR-030](decisions/adr-030-online-data-access-boundary.md), [ADR-031](decisions/storage/adr-031-state-snapshot-abi.md), [ADR-040](decisions/storage/adr-040-hot-cold-retention-state-namespace-policy.md)
- **研究数据集与 PIT 检索**: [ADR-021](decisions/quality/adr-021-pit-consistency.md), [ADR-032](decisions/core/adr-032-unified-derived-semantic-model.md), [ADR-033](decisions/adr-033-derived-query-architecture.md), [ADR-041](decisions/research/adr-041-research-dataset-spine-availability-contract.md)
- **发布安全与认证治理**: [ADR-034](decisions/core/adr-034-publication-lifecycle.md), [ADR-036](decisions/quality/adr-036-quality-gates.md), [ADR-042](decisions/research/adr-042-shadow-publish-dual-read-diff-protocol.md), [ADR-043](decisions/research/adr-043-role-profile-certification-compatibility-manifest.md)

### 按实施阶段
- **Phase 0（内核可跑通）**: ADR-001 ~ ADR-010, ADR-014
- **Phase 1（增量与并发）**: ADR-012, ADR-015, ADR-017, ADR-018, ADR-020, ADR-026~031
- **Phase 2（PIT 与闭环）**: ADR-011, ADR-021, ADR-022, ADR-024
- **Phase 3（实时流集成）**: ADR-027 ~ ADR-031（盘中微批量路径）
- **Phase 4（统一模型与控制面）**: ADR-032 ~ ADR-043（DerivedSpec、发布、质量、性能、retention、研究数据集、发布安全）

## 状态说明

| 状态 | 含义 |
|------|------|
| ✅ 已决策 | 设计完成，可开始实施 |
| ⏸️ 暂缓 | 等待后续阶段再评估 |
| 🚧 进行中 | 设计正在进行 |
| ❌ 已废弃 | 已被替代或不再使用 |

## 参考文档

### 设计文档
- [主设计文档](main-design.md) - 完整的系统架构设计
- [整改设计方案](../../plans/2026-03-13-unified-feature-factor-engine-remediation-design.md) - 当前整改执行的入口文档
- [原始设计文档](../../plans/archive/2026-03-04-unified-feature-factor-engine-final-design.md) - 归档的原始设计
- [CLAUDE.md](../../../CLAUDE.md) - 项目规范与开发指南

### 参考资料 (reference/)

| 文档 | 说明 |
|------|------|
| [factor-expression-syntax.md](reference/factor-expression-syntax.md) | 因子表达式语法参考 - 基础语法、算子、嵌套规则 |
| [operator-reference.md](reference/operator-reference.md) | 算子参考手册 - 完整算子定义、属性、实现说明 |
| [catalog-schema.md](reference/catalog-schema.md) | Catalog 表结构参考 - SQLite + Kvrocks 完整 DDL |
| [industry-benchmarks.md](reference/industry-benchmarks.md) | 业界对标分析 - Qlib/Feast/DolphinDB 等对比 |
| [worldquant-alpha101.md](reference/worldquant-alpha101.md) | WorldQuant Alpha101 参考 - 语法规范与因子示例 |
| [technical-implementation.md](reference/technical-implementation.md) | 技术实现参考 - Pratt Parser、增量计算、状态管理 |
