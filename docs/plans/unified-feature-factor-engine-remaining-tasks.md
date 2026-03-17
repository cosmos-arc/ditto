# Unified Feature/Factor Engine 待办事项

**更新日期**: 2026-03-17
**背景**: Phase 1-4 技术债务整改计划已全部完成。本文档梳理剩余待办项。

---

## 按优先级排序

### P0: 架构违规修复

| ID | 问题 | 位置 | 说明 |
|----|------|------|------|
| **ARCH-01** | `compile_cache_service` 违反分层约束 | [compile_cache_service.py:22-24](../../packages/datahub/src/ditto_datahub/services/derived/compile_cache_service.py#L22-L24) | DataHub 导入了 Core 引擎类型（`ExpressionCompiler`、`CompiledDerivedExpression`、`DerivedSpec`）。`pixi run -e dev arch-check` 报 2 条 BROKEN。 |

**修复方案**：
- 方案 A（推荐）：将 `compile_cache_service.py` 上移到 `packages/core/`，因其本质依赖 Core 引擎内部类型
- 方案 B：在 DataHub 定义 Protocol 接口，Core 引擎实现，解除直接依赖

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
| **SM-01** | 丢弃的返回值 | [query_facade.py:124](../../apps/port/src/ditto_port/services/derived/query_facade.py#L124) | `_ = self._mode_resolver.resolve()` — `get_series()` 和 `compare_sources()` 解析了 mode 但未使用。建议移除调用或添加 Phase 5+ TODO 注释。 |
| **SM-02** | `# type: ignore` 集群 | [golden.py:112-149](../../packages/core/src/ditto_core/quality/golden.py#L112-L149) | 4 处 type ignore 集中在 golden 验证逻辑中。需审查是否可通过类型重构消除。 |
| **SM-03** | `# type: ignore` 集群 | [deploy.py:81-92](../../apps/port/src/ditto_port/jobs/flows/deploy.py#L81-L92) | 3 处 `return-value` ignore。需审查。 |
| **SM-04** | `# type: ignore` | [bond_yield.py:248-262](../../packages/datahub/src/ditto_datahub/sources/tushare/adapters/bond_yield.py#L248-L262) | 2 处 `arg-type` ignore。需审查。 |
| **SM-05** | `# type: ignore` | [compile_cache_service.py:169](../../packages/datahub/src/ditto_datahub/services/derived/compile_cache_service.py#L169) | 1 处 `union-attr` ignore。可能在 ARCH-01 修复后解决。 |

---

### P3: 小型技术债务

| ID | 问题 | 位置 | 说明 |
|----|------|------|------|
| **TD-01** | TODO: 批量查询优化 | [tdx/source.py:109](../../packages/datahub/src/ditto_datahub/sources/tdx/source.py#L109) | `# TODO: 实现更高效的批量查询，从 InstrumentStore 获取` |
| **TD-02** | TODO: 告警发送 | [reconciliation_service.py:295](../../apps/port/src/ditto_port/services/ingestion/quality/reconciliation_service.py#L295) | `# TODO: 实现告警发送（邮件、钉钉、微信等）` |
| **TD-03** | `noqa: S110` 宽泛异常捕获 | [query_facade.py:109](../../apps/port/src/ditto_port/services/derived/query_facade.py#L109) | 热层降级的 `except Exception: pass`。当前合理（Phase 4 设计），但生产环境应添加日志。 |
| **TD-04** | `noqa: S110` 宽泛异常捕获 | [observability/testing.py:19](../../packages/infra/src/ditto_infra/foundation/observability/testing.py#L19) | 测试辅助代码中的 shutdown 异常吞没，已有注释说明。 |

---

## 按计划文档分组

### Phase 5+ 延期项

| 计划文档 | 待办项 | 说明 |
|----------|--------|------|
| 技术债务整改 | I-EXPR-01 DAG/CSE 优化 | 低优先级，性能满足需求。 |
| [Phase 6 Hardening](./2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md) | Batch H1: Benchmark 治理 | Nightly pipeline、baseline 存储、diff 命令 |
| [Phase 6 Hardening](./2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md) | Batch H2: Runtime SLI | 端到端时间戳落库 |
| [Phase 6 Hardening](./2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md) | Batch H3: Housekeeping | Shadow report / artifact 保留清理 |
| [Phase 6 Hardening](./2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md) | Batch H4: Release Hardening | Dry-run、runbook、SLO 收敛 |

### 暂缓的 ADR（等待重启条件）

| ADR | 暂缓原因 | 重启条件 |
|-----|---------|---------|
| [ADR-011](../design/unified-feature-factor-engine/decisions/adr-011-streaming-mode.md) | 盘中微批量处理模式 | QuestDB + Kvrocks 基础设施就绪 |
| [ADR-023](../design/unified-feature-factor-engine/decisions/adr-023-disaster-recovery.md) | 灾备恢复策略 | 确认上游数据源支持断点续传 |

---

## 建议执行顺序

```
Week 1:
├── ARCH-01: compile_cache_service 架构修复（解除 arch-check 阻断）
└── ERR-01/02/03: Port 层裸异常替换（扩展 Q-ERR-01 范围）

Week 2:
├── SM-01~05: type: ignore 清理
└── TD-01~04: 小型技术债务清理

Week 3-4:（按需）
└── Phase 6 Batch H1: Benchmark 治理
```

---

## 验证基线（2026-03-17）

| 检查项 | 结果 |
|--------|------|
| `pixi run -e dev lint` | ✅ All checks passed |
| `pixi run -e dev fmt --check` | ✅ 809 files already formatted |
| `pixi run -e dev type` | ✅ 0 errors, 0 warnings, 0 notes |
| `pixi run -e dev test --unit` | ✅ 2202 passed, 0 failed |
| `pixi run -e dev arch-check` | ⚠️ 2 BROKEN (compile_cache_service) |
| 测试覆盖率 | ✅ 80.81% (≥ 80%) |
