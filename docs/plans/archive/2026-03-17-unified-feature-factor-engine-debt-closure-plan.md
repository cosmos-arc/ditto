# Unified Feature/Factor Engine 技术债务收尾计划

**创建日期**: 2026-03-17
**前序**: [技术债务整改计划 Phase 1-4](./2026-03-16-unified-feature-factor-engine-technical-debt-remediation-plan.md) 已全部完成
**目标**: 清零剩余技术债务，通过全部质量门禁

---

## 整改目标

| 维度 | 当前 | 目标 |
|------|------|------|
| **架构合规** | `arch-check` 2 BROKEN | 0 BROKEN |
| **异常一致性** | Port 层 3 处裸异常 | Derived 域零裸异常 |
| **命名一致性** | 2 处 Service 应为 Orchestrator | derived 域命名统一 |
| **类型安全** | 10 处 `# type: ignore` | 最小化（≤ 3 处，有注释说明） |
| **工程清洁** | 2 处 TODO、2 处 noqa: S110 | 清理或注释说明 |

---

## 核心约束

| 约束项 | 内容 |
|--------|------|
| 新功能 | **完全冻结** |
| 验证策略 | **严格 TDD** |
| 向后兼容 | **不需要**，直接迁移重构 |

---

## Batch 总览

| Batch | 名称 | 问题数 | 核心目标 | 依赖 |
|-------|------|--------|----------|------|
| **Batch 1** | 架构合规 + 异常收尾 | 4 | arch-check 零 BROKEN，异常体系统一 | 无 |
| **Batch 2** | 命名对齐 + 代码清洁 | 7 | Service → Orchestrator，type: ignore 清理 | Batch 1 |
| **Batch 3** | 生产加固 | 3 | 日志、TODO 处理、noqa 清理 | Batch 2 |

---

## Batch 1: 架构合规 + 异常收尾

### 问题清单

| ID | 问题 | 类型 | 严重程度 |
|----|------|------|----------|
| **ARCH-01** | `compile_cache_service` 违反分层约束 | 架构 | 高 |
| **ERR-01** | Port 层裸 `KeyError`（config.py） | 异常 | 中 |
| **ERR-02** | Port 层裸 `KeyError`（research.py） | 异常 | 中 |
| **ERR-03** | Port 层裸 `ValueError`（publication.py） | 异常 | 中 |

### 1.1 ARCH-01: compile_cache_service 架构修复

**当前状态**：

```
arch-check BROKEN:
  ditto_data.services.derived.compile_cache_service
    → ditto_core.engine.expression (L22)
    → ditto_core.engine.materialization (L23)
    → ditto_core.engine.specs (L24)
```

DataHub 层不可导入 Core 层。`compile_cache_service` 依赖 Core 引擎内部类型（`ExpressionCompiler`、`CompiledDerivedExpression`、`DerivedSpec`），本质上是一个 Core 层服务。

**修复方案**：将 `compile_cache_service.py` 上移到 `packages/core/`

```
修改前:
  packages/data/src/ditto_data/services/derived/compile_cache_service.py

修改后:
  packages/core/src/ditto_core/engine/compile_cache.py
```

**具体步骤**：

1. `git mv` 移动文件到 `packages/core/src/ditto_core/engine/compile_cache.py`
2. 重命名类：`SQLiteCompileCacheService` → `SQLiteCompileCache`（去掉 Service 后缀，Core 层不使用 Service 命名）
3. 更新所有导入：
   - `packages/data/src/ditto_data/services/derived/__init__.py`
   - 任何引用 `from ditto_data.services.derived.compile_cache_service import ...` 的文件
4. 移除 `.importlinter` 中针对此文件的 `ignore_imports` 规则
5. 更新测试文件导入

**预期效果**：`pixi run -e dev arch-check` → 0 BROKEN

### 1.2 ERR-01/02/03: Port 层异常统一

**替换规则**（延续 Q-ERR-01）：

| 文件 | 旧异常 | 新异常 |
|------|--------|--------|
| `apps/port/.../models/config.py:645` | `KeyError("Dataset ... not found")` | `DerivedNotFoundError(derived_id=dataset)` |
| `apps/port/.../services/derived/research.py:383` | `KeyError("research spine spec not found ...")` | `DerivedNotFoundError(derived_id=spine_id)` |
| `apps/port/.../services/derived/publication.py:103` | `ValueError("shadow baseline not found ...")` | `DerivedNotFoundError(derived_id=derived_id)` |

**注意**：`config.py` 的异常上下文不是 derived domain（是 dataset registry），需评估是否应该用 `DerivedNotFoundError` 还是保留 `KeyError`。如果 dataset 是 derived spec 的一部分，则替换；否则保留 `KeyError` 并添加注释说明。

**测试更新**：
- `apps/port/tests/` 中所有 `pytest.raises(KeyError)` 或 `pytest.raises(ValueError)` 对应上述 3 处的测试

### Batch 1 验收标准

| 检查项 | 标准 |
|--------|------|
| arch-check | 0 BROKEN |
| 裸异常 | derived 域（含 Port derived 服务）零裸 KeyError/ValueError |
| 测试 | 全部通过 |
| 类型检查 | 0 errors |

---

## Batch 2: 命名对齐 + 代码清洁

### 问题清单

| ID | 问题 | 类型 | 严重程度 |
|----|------|------|----------|
| **Q-NAME-01a** | `DerivedInvalidationService` 应为 Orchestrator | 命名 | 低 |
| **Q-NAME-01b** | `InvalidationCascadeService` 应为 Orchestrator | 命名 | 低 |
| **SM-01** | `query_facade.py` 丢弃返回值 | 代码异味 | 低 |
| **SM-02** | `golden.py` 4 处 `# type: ignore` | 类型安全 | 中 |
| **SM-03** | `deploy.py` 3 处 `# type: ignore` | 类型安全 | 中 |
| **SM-04** | `bond_yield.py` 2 处 `# type: ignore` | 类型安全 | 低 |
| **SM-05** | `compile_cache_service.py` 1 处 `# type: ignore` | 类型安全 | 低 |

### 2.1 Q-NAME-01a/01b: Service → Orchestrator

**判定标准**：协调多步骤工作流（涉及多个 Service 协作）的类应命名为 Orchestrator。

| 当前名称 | 新名称 | 理由 |
|----------|--------|------|
| `DerivedInvalidationService` | `DerivedInvalidationOrchestrator` | 协调 fan-out + repair，委托 `DerivedMaterializationOrchestrator` |
| `InvalidationCascadeService` | `InvalidationCascadeOrchestrator` | BFS 图遍历 + 状态机 + 批量修复，协调多个 Service |

**不需要重命名的类**：

| 类名 | 理由 |
|------|------|
| `DerivedQueryService` | 纯查询/读取，无多步骤编排 |
| `SQLiteCompileCacheService` | 基础设施缓存，单一职责（Batch 1 移动后也可能改名） |

**修改文件清单**：

1. `apps/port/src/ditto_port/services/derived/invalidation.py` — 类定义 + `__init__.py` 导出
2. `apps/port/src/ditto_port/services/derived/cascade_protocol.py` — 类定义 + `__init__.py` 导出
3. `apps/port/src/ditto_port/registry/datahub/derived.py` — DI wiring
4. 所有测试文件中的 `pytest.importorskip` / `unittest.mock.patch` 路径
5. 测试文件名：`test_cascade_protocol_unit.py` 中对类名的引用

### 2.2 SM-01: 丢弃返回值清理

**位置**：[query_facade.py:124, 142](../../apps/port/src/ditto_port/services/derived/query_facade.py#L124)

**方案**：移除 `get_series()` 和 `compare_sources()` 中的 `_ = self._mode_resolver.resolve()` 调用。这两个方法当前不消费 RuntimeMode，调用只会造成困惑。

### 2.3 SM-02~05: `# type: ignore` 逐个审查

每个 `# type: ignore` 需要读取上下文后判断：

| ID | 文件 | 数量 | 处理策略 |
|----|------|------|---------|
| SM-02 | `golden.py:112-149` | 4 | 审查 Polars API 调用，可能需要泛型注解 |
| SM-03 | `deploy.py:81-92` | 3 | 审查 prefect task 返回值类型 |
| SM-04 | `bond_yield.py:248-262` | 2 | 审查数据转换参数类型 |
| SM-05 | `compile_cache_service.py:169` | 1 | Batch 1 移动后可能自动解决 |

**原则**：能通过重构消除的必须消除；不能消除的添加注释说明原因。

### Batch 2 验收标准

| 检查项 | 标准 |
|--------|------|
| 命名一致 | derived 域无应改未改的 Service 命名 |
| type: ignore | 目标 ≤ 5 处（从 10 处减少） |
| 代码异味 | 无丢弃返回值 |
| 测试 | 全部通过 |

---

## Batch 3: 生产加固

### 问题清单

| ID | 问题 | 类型 | 严重程度 |
|----|------|------|----------|
| **TD-01** | TODO: TDX 批量查询优化 | 功能 | 低 |
| **TD-02** | TODO: 告警发送 | 功能 | 低 |
| **TD-03** | `noqa: S110` 热层降级无日志 | 安全 | 中 |
| **TD-04** | `noqa: S110` 测试辅助异常吞没 | 安全 | 低 |

### 3.1 TD-01: TDX 批量查询 [OUT OF SCOPE]

**位置**：[tdx/source.py:109](../../packages/data/src/ditto_data/sources/tdx/source.py#L109)

> **已转出为独立 feature，不在本技术债务计划范围内。** 将创建独立的 feature request 跟踪。

### 3.2 TD-02: 告警发送 [OUT OF SCOPE]

**位置**：[reconciliation_service.py:295](../../apps/port/src/ditto_port/services/ingestion/quality/reconciliation_service.py#L295)

> **已转出为独立 feature，不属于技术债务。** 将创建独立的 feature request 跟踪。

### 3.3 TD-03: 热层降级添加日志

**位置**：[query_facade.py:109](../../apps/port/src/ditto_port/services/derived/query_facade.py#L109)

```python
# 修改前
except Exception:  # noqa: S110
    pass

# 修改后
except Exception:
    logger.warning("Hot layer read failed, falling back to cold layer", exc_info=True)
```

需要导入 `loguru` logger。添加结构化日志后可移除 `noqa: S110`。

### 3.4 TD-04: 测试辅助异常

**位置**：[observability/testing.py:19](../../packages/infra/src/ditto_infra/foundation/observability/testing.py#L19)

已有注释说明意图（shutdown 失败不应阻塞测试）。**保留现状**，已有充分的文档说明。

### Batch 3 验收标准

| 检查项 | 标准 |
|--------|------|
| noqa: S110 | 生产代码零裸异常捕获（TD-03 修复） |
| 日志 | 热层降级有结构化日志 |
| TD-01/02 | 已转出为独立 feature（不影响本计划验收） |

---

## 修复顺序

```
Batch 1（Day 1-2）: 架构合规 + 异常收尾
├── ARCH-01: compile_cache_service 上移 Core 层
├── ERR-01/02/03: Port 层异常替换
└── 验证: arch-check + check

Batch 2（Day 3）: 命名对齐 + 代码清洁
├── Q-NAME-01a/01b: 2 个 Service → Orchestrator
├── SM-01: 移除丢弃返回值
├── SM-02~05: type: ignore 审查与修复
└── 验证: check

Batch 3（Day 4）: 生产加固
├── TD-03: 热层降级日志
├── TD-01/02: 转出为独立 feature
└── 验证: check

最终验证:
└── pixi run -e dev ci
```

---

## 全局验收标准

| 检查项 | 当前 | 目标 |
|--------|------|------|
| `pixi run -e dev arch-check` | 2 BROKEN | **0 BROKEN** |
| `pixi run -e dev lint` | All passed | All passed |
| `pixi run -e dev type` | 0 errors | 0 errors |
| `pixi run -e dev test --unit` | 2202 passed | 全部 passed |
| `pixi run -e dev fmt --check` | 809 formatted | 全部 formatted |
| 裸异常（derived 域） | 3 处遗留 | **0 处** |
| `# type: ignore` | 10 处 | **≤ 5 处** |
| 测试覆盖率 | 80.81% | ≥ 80% |

---

## 不在本计划范围内

| 项目 | 原因 | 位置 |
|------|------|------|
| I-EXPR-01 DAG/CSE 优化 | 性能满足需求，复杂度高 | 独立计划 |
| Phase 6 Benchmark 治理 | 运维阶段 | [Phase 6 计划](./archive/2026-03-14-unified-feature-factor-engine-phase-6-hardening-plan.md) |
| ADR-011 盘中微批量 | 等待 QuestDB + Kvrocks | 已暂缓 |
| ADR-023 灾备恢复 | 等待上游数据源确认 | 已暂缓 |
| TD-01 TDX 批量查询 | 功能增强 | 独立 feature（已转出） |
| TD-02 告警发送 | 新功能 | 独立 feature（已转出） |

---

## 完成总结

### 本计划实际范围调整

| 项目 | 原始计划 | 调整后 | 原因 |
|------|----------|--------|------|
| TD-01 TDX 批量查询 | Batch 3 实施 | **已转出** | 功能增强，非技术债务 |
| TD-02 告警发送 | Batch 3 实施 | **已转出** | 新功能，非技术债务 |

本计划技术债务实际项从 18 项缩减为 16 项（TD-01、TD-02 转出），所有 16 项技术债务验收标准不变。转出的 2 项将创建独立 feature request 跟踪，不影响本计划的全局验收。
