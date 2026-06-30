# 架构整改遗留修复

## 概述

- 来源: `docs/plans/2026-05-15-architecture-remediation-plan.md` 审计发现的 4 项遗留问题
- 创建: 2026-05-18
- 分支: `remediation/architecture-remediation-batch-1`（工作区未提交变更之上）

## 修复清单

| ID | 问题 | 批次 | 严重度 |
|----|------|------|--------|
| FIX-1 | D1A-5: `Dataset.date_schedule` 未迁移到 registry | Batch 1 | 中 |
| FIX-2 | P-2: `ObservabilityRegistry` 仍为可变模块级单例 | Batch 6 | 中 |
| FIX-3 | E2B-4: Reconciliation Recovery ADR 仅为内联 docstring | Batch 2 | 低 |
| FIX-4 | PF2D-3: 测试 helper 中 `instrument_id` 用 `int` 非 `InstrumentId` | Batch 2 | 低 |

## 技术方案

### FIX-1: date_schedule 迁移到 DatasetRegistration

**策略**: 在 `DatasetRegistration` 新增 `date_schedule` 字段，`coordinator.ingest_range()` 从 registry 读取。`DateScheduleType` 枚举保留在 `ditto_data.models`（减少迁移面），删除 `Dataset.date_schedule` property。

**影响面**:
- 源码: `dataset_registry.py`（新增字段 + 23 处注册配置）、`coordinator.py`（1 处调用点）、`common.py`（删除 property）
- 测试: `test_dataset_registry_unit.py`（7 处构造更新）、`test_coordinator_unit.py`（4 处 ingest_range 测试）

### FIX-2: ObservabilityRegistry 改 contextvars

**策略**: 将模块级可变单例替换为 `contextvars.ContextVar` 存储 frozen dataclass。模块级函数保持签名不变（`is_initialized()` / `set_initialized()` / `get_config()` / `set_config()` / `reset()`），内部从 ContextVar 读写。`reset()` 使用 `_var.set(None)` 实现，天然支持测试隔离。

**影响面**:
- 源码: `_registry.py`（重写）、`_lifecycle.py`（无需修改，仍调用同名函数）
- 测试: 3 个测试文件无需修改（函数签名不变）
- 外部包: 零影响（公共 API `init()`/`shutdown()` 不变）

### FIX-3: Reconciliation Recovery 独立 ADR

**策略**: 从 `reconciler.py` 模块 docstring 提取 ADR 内容，创建独立文档。

### FIX-4: 测试 helper 类型修正

**策略**: 以 `test_projection_unit.py` 为标杆，修正 `test_account_unit.py` 和 `test_account_events_unit.py` 中的 helper 函数和裸 `int` 使用。

---

## 任务清单

- [x] FIX-1: 迁移 date_schedule 到 DatasetRegistration `[M]`
  - 验收: `Dataset.date_schedule` property 删除；`coordinator.ingest_range()` 从 registry 读取；`DateScheduleType` 仅被 registry 和 coordinator 引用；`pixi run -e dev check` 全绿
  - 文件:
    - `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py`
    - `packages/application/src/ditto_application/processes/ingestion/coordinator.py`
    - `packages/data/src/ditto_data/models/common.py`
    - `packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py`
    - `packages/application/tests/unit/process/ingestion/test_coordinator_unit.py`
  - 测试: 新增 `date_schedule` 字段默认值测试；修改 `ingest_range` 测试验证 registry 来源

- [x] FIX-2: ObservabilityRegistry 改 contextvars `[S]`
  - 验收: `_registry.py` 使用 `ContextVar` 存储 frozen dataclass；`_lifecycle.py` 零修改；3 个测试全绿；无 class-level mutable state
  - 文件:
    - `packages/platform/src/ditto_platform/foundation/observability/_registry.py`
  - 测试: 现有测试无需修改；行为等价验证

- [x] FIX-3: Reconciliation Recovery 独立 ADR `[S]`
  - 验收: `docs/architecture/adr-reconciliation-recovery.md` 存在且内容完整
  - 文件:
    - `docs/architecture/adr-reconciliation-recovery.md`（新建）

- [x] FIX-4: 测试 helper InstrumentId 类型修正 `[S]`
  - 验收: `test_account_unit.py` 和 `test_account_events_unit.py` 中 `instrument_id` 全部使用 `InstrumentId`；`test_projection_unit.py` 不变（已正确）
  - 文件:
    - `packages/portfolio/tests/unit/accounting/test_account_unit.py`
    - `packages/portfolio/tests/unit/test_account_events_unit.py`
  - 测试: 行为等价（`InstrumentId = NewType("InstrumentId", int)` 运行时无差异）

## 执行顺序

4 项任务互相独立，可并行执行。建议顺序: FIX-3 → FIX-4 → FIX-2 → FIX-1（由简到繁）。

## 完成标准

```bash
pixi run -e dev check  # lint + fmt + type + test --fast + arch-check
```

- 37/37 import-linter 合约保持
- 0 type errors
- 全部测试通过
