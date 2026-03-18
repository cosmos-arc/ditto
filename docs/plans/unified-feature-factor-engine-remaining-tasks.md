# Unified Feature/Factor Engine 待办事项

**更新日期**: 2026-03-18
**背景**: Phase 1-4 技术债务整改计划及 Convergence Plan (P1-P4) 已全部完成。本文档梳理剩余待办项。

### Convergence Plan 完成项（2026-03-18）

以下项目已由 [Convergence Plan](./2026-03-18-unified-engine-convergence-plan.md) 完成：

| 阶段 | 项目 | 状态 |
|------|------|------|
| P1-1 | UoW 事务边界落地 | ✅ 完成 |
| P1-2 | Record 类型守卫 | ✅ 完成 |
| P1-3 | ts_rank/ts_argmax/ts_argmin codegen | ✅ 完成 |
| P2-1 | 废弃旧 Invalidation 协议 | ✅ 完成 |
| P3-1 | ResearchDatasetFacade 层边界修复 | ✅ 完成（新增 ResearchArtifactService） |
| P3-2 | RuntimeDerivedInputProvider 收回 Store 访问 | ✅ 完成 |
| P3-3 | MaterializationOrchestrator 收回 Store 访问 | ✅ 完成（ArtifactPersistenceService） |
| P3-4 | UniverseProvider 注入修复 | ✅ 完成 |
| P4-1 | 去掉 materialize 自动 shadow save | ✅ 完成 |
| P4-2 | Research 版本绑定 PUBLISHED | ✅ 完成（_resolve_primary_online 增加 status 过滤） |
| P4-3 | Profile 物理路径收敛 | ✅ 已收敛（无需额外改动） |
| P4-4 | 文档同步 | ✅ 完成（engine README 重写） |

---

## 按优先级排序

### P0: 架构违规修复

> ~~ARCH-01~~：`compile_cache_service.py` 已在 Convergence Plan 中移除，arch-check 现在 0 BROKEN。

---

### P1: 代码质量（Q-ERR-01 遗留）

| ID | 问题 | 位置 | 说明 |
|----|------|------|------|
| **ERR-01** | 裸 `KeyError` 未替换 | [config.py:645](../../apps/port/src/ditto_port/models/config.py#L645) | `raise KeyError(f"Dataset {dataset} not found in registry")` |
| **ERR-02** | 裸 `KeyError` 未替换 | [research.py:383](../../apps/port/src/ditto_port/services/derived/research.py#L383) | `raise KeyError(f"research spine spec not found for spine_id={spine_id}")` |
| **ERR-03** | 裸 `ValueError` 未替换 | [publication.py:103](../../apps/port/src/ditto_port/services/derived/publication.py#L103) | `raise ValueError(f"shadow baseline not found for derived_id={derived_id}")` |

> Q-ERR-01 范围限定在 `packages/datahub/services/derived/` 和 `packages/core/engine/`。上述 3 处位于 `apps/port/`，属于范围扩展。建议统一替换为 `DerivedNotFoundError`。

---

### P2: 代码异味

| ID | 问题 | 位置 | 说明 |
|----|------|------|------|
| **SM-02** | `# type: ignore` 集群 | [golden.py:112-149](../../packages/core/src/ditto_core/quality/golden.py#L112-L149) | 4 处 type ignore 集中在 golden 验证逻辑中。需审查是否可通过类型重构消除。 |
| **SM-03** | `# type: ignore` 集群 | [deploy.py:81-92](../../apps/port/src/ditto_port/jobs/flows/deploy.py#L81-L92) | 3 处 `return-value` ignore。需审查。 |
| **SM-04** | `# type: ignore` | [bond_yield.py:248-262](../../packages/datahub/src/ditto_datahub/sources/tushare/adapters/bond_yield.py#L248-L262) | 2 处 `arg-type` ignore。需审查。 |
| ~~**SM-05**~~ | ~~`# type: ignore`~~ | ~~compile_cache_service.py~~ | 已随文件移除解决。 |

---

### P3: 小型技术债务

| ID | 问题 | 位置 | 说明 |
|----|------|------|------|
| **TD-01** | TODO: 批量查询优化 | [tdx/source.py:109](../../packages/datahub/src/ditto_datahub/sources/tdx/source.py#L109) | `# TODO: 实现更高效的批量查询，从 InstrumentStore 获取` |
| **TD-02** | TODO: 告警发送 | [reconciliation_service.py:295](../../apps/port/src/ditto_port/services/ingestion/quality/reconciliation_service.py#L295) | `# TODO: 实现告警发送（邮件、钉钉、微信等）` |
| **TD-04** | `noqa: S110` 宽泛异常捕获 | [observability/testing.py:19](../../packages/infra/src/ditto_infra/foundation/observability/testing.py#L19) | 测试辅助代码中的 shutdown 异常吞没，已有注释说明。 |

---

## 按计划文档分组

### Phase 5+ 延期项

| 计划文档 | 待办项 | 说明 |
|----------|--------|------|
| 技术债务整改 | I-EXPR-01 DAG/CSE 优化 | 低优先级，性能满足需求。 |
| [Phase 6 Hardening](./archive/2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md) | Batch H1: Benchmark 治理 | Nightly pipeline、baseline 存储、diff 命令 |
| [Phase 6 Hardening](./archive/2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md) | Batch H2: Runtime SLI | 端到端时间戳落库 |
| [Phase 6 Hardening](./archive/2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md) | Batch H3: Housekeeping | Shadow report / artifact 保留清理 |
| [Phase 6 Hardening](./archive/2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md) | Batch H4: Release Hardening | Dry-run、runbook、SLO 收敛 |

### 暂缓的 ADR（等待重启条件）

| ADR | 暂缓原因 | 重启条件 |
|-----|---------|---------|
| [ADR-011](../design/unified-feature-factor-engine/decisions/adr-011-streaming-mode.md) | 盘中微批量处理模式 | QuestDB + Kvrocks 基础设施就绪 |
| [ADR-023](../design/unified-feature-factor-engine/decisions/adr-023-disaster-recovery.md) | 灾备恢复策略 | 确认上游数据源支持断点续传 |

---

## 建议执行顺序

```
Week 1:
└── ERR-01/02/03: Port 层裸异常替换（扩展 Q-ERR-01 范围）

Week 2:
├── SM-01~05: type: ignore 清理
└── TD-01~04: 小型技术债务清理

Week 3-4:（按需）
└── Phase 6 Batch H1: Benchmark 治理
```

---

## 验证基线（2026-03-18）

| 检查项 | 结果 |
|--------|------|
| `pixi run -e dev lint` | ✅ All checks passed |
| `pixi run -e dev fmt --check` | ✅ 807 files already formatted |
| `pixi run -e dev type` | ✅ 0 errors, 0 warnings, 0 notes |
| `pixi run -e dev test --fast` | ✅ 2254 passed, 0 failed |
| `pixi run -e dev arch-check` | ✅ 0 BROKEN (6 KEPT) |
| 测试覆盖率 | ✅ ≥ 80% |
