> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# Ditto Unified Derived Engine 文档索引

本目录保存 unified-feature-factor-engine 的当前主设计、ADR 决策、参考资料与历史归档文档。

## 当前真相源

当前请只把以下文件当作有效事实基础：

1. [主设计文档](main-design.md)
2. [ADR 决策索引](decisions/00-index.md)

如果历史评审、历史优化文档或已归档计划与上述文件冲突，以这四类文档与当前实现为准。

## 阅读顺序

### 首次阅读

1. [main-design.md](main-design.md)
2. [00-index.md](decisions/00-index.md)

### 必读 ADR

以下 ADR 直接定义当前系统骨架：

- [ADR-032](decisions/core/adr-032-unified-derived-semantic-model.md)
- [ADR-033](decisions/adr-033-derived-query-architecture.md)
- [ADR-034](decisions/core/adr-034-publication-lifecycle.md)
- [ADR-035](decisions/adr-035-invalidation-cascade.md)
- [ADR-036](decisions/quality/adr-036-quality-gates.md)
- [ADR-040](decisions/storage/adr-040-hot-cold-retention-state-namespace-policy.md)
- [ADR-041](decisions/research/adr-041-research-dataset-spine-availability-contract.md)
- [ADR-042](decisions/research/adr-042-shadow-publish-dual-read-diff-protocol.md)
- [ADR-043](decisions/research/adr-043-role-profile-certification-compatibility-manifest.md)

### 补充专题 ADR

以下 ADR 更偏专题细化、实现附录或规格参考：

- 表达式与算子: ADR-001, 002, 003, 004, 006, 007, 008, 012, 013, 014, 015, 038, 039
- 存储与运维: ADR-009, 010, 017, 018, 019, 020, 026, 027, 028, 029, 030, 031
- 暂缓项: ADR-011, ADR-023

## 目录结构

```text
packages/features/docs/design/unified-feature-factor-engine/
├── README.md            # 本文件：真相源导航
├── main-design.md       # 当前完整主设计文档
├── decisions/           # ADR 决策与专题细化
├── reference/           # 参考资料与规范附录
└── archive/             # 已退出当前真相源的历史设计与评审文档
```

## 当前设计边界

### 已落地

- `DerivedSpec` 作为统一根模型
- 统一表达式编译链路与编译缓存
- artifact-first 物化主链
- query facade / publication / research dataset
- cascade invalidation 单协议
- UoW 事务边界与层边界收口

### 明确保留但未激活

- `grain="1m"`
- 复合键 `entity_keys`
- `SIGNAL / LABEL`
- `TimeSpec / ExecutionPolicy` 的完整行为迁移
- `STATE` 热态物理路径

### 暂缓

- [ADR-011](decisions/adr-011-streaming-mode.md): QuestDB + Kvrocks 基础设施就绪后重启
- [ADR-023](decisions/adr-023-disaster-recovery.md): 上游断点续传边界明确后重启

## 已归档历史文档

以下文档已退出当前真相源，移动到 [archive/](archive)：

- [2026-03-04-main-design-baseline.md](archive/2026-03-04-main-design-baseline.md)
- [issues.md](archive/issues.md)
- [design-analysis-report.md](archive/design-analysis-report.md)
- [optimization-review.md](archive/optimization-review.md)
- [optimization-backlog.md](archive/optimization-backlog.md)
- [revision-questdb-hot-layer.md](archive/revision-questdb-hot-layer.md)
- [technical-debt-review-2026-03-14.md](archive/technical-debt-review-2026-03-14.md)
- [review-2026-03-15.md](archive/review-2026-03-15.md)
- [archive/design-gaps-complete.md](archive/design-gaps-complete.md)
- [archive/gap-checklist.md](archive/gap-checklist.md)
- [archive/adr-016-catalog-storage.md](archive/adr-016-catalog-storage.md)

这些文档保留设计演化轨迹，但不再用于回答“当前系统是如何设计的”。

## 参考资料

- [factor-expression-syntax.md](reference/factor-expression-syntax.md)
- [operator-reference.md](reference/operator-reference.md)
- [catalog-schema.md](reference/catalog-schema.md)
- [technical-implementation.md](reference/technical-implementation.md)
- [industry-benchmarks.md](reference/industry-benchmarks.md)
- [worldquant-alpha101.md](reference/worldquant-alpha101.md)
