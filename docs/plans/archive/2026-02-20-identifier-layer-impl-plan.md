# 标识符层重构 - 实施计划

> **状态**: ✅ 已完成 (2026-02-21)

**设计文档**: [2026-02-20-identifier-layer-refactor-design-v2.md](2026-02-20-identifier-layer-refactor-design-v2.md)
**创建**: 2026-02-20
**完成**: 2026-02-21
**任务数**: 7 个

---

## 任务依赖图

```
Task 1 ──┐
         ├──► Task 3 ──┐
Task 2 ──┘             │
                       ├──► Task 5 ──► Task 6 ──► Task 7
Task 4 ────────────────┘
```

---

## Phase 1: DataHub 层基础

### Task 1: 新建 AssetClass 枚举和 Dataset 扩展 `[S]`

**描述**: 在 datahub/models 层建立资产类型枚举，并在 Dataset 枚举中增加 `asset_class` 属性。

**验收标准**:
- [ ] `AssetClass` 枚举定义完整（stock/etf/index/future/bond/fund）
- [ ] `Dataset.asset_class` 属性返回正确的 `AssetClass | None`
- [ ] `Dataset.supports_instrument_ingestion()` 方法可用
- [ ] 单元测试通过

**文件**:
- 新建: `packages/data/src/ditto_data/models/asset_class.py`
- 修改: `packages/data/src/ditto_data/models/dataset.py`
- 新建: `packages/data/tests/unit/models/test_asset_class_unit.py`

**复杂度**: S（单文件枚举 + 属性扩展）

---

### Task 2: 迁移 exchange 转换函数到 datahub `[S]`

**描述**: 将 `source_ticker_to_standard_ticker` 函数从 port 层迁移到 datahub/models 层。

**验收标准**:
- [ ] 新建 `exchange.py` 包含转换函数
- [ ] 函数支持 Tushare exchange 格式转换
- [ ] 单元测试覆盖各种 exchange 组合

**文件**:
- 新建: `packages/data/src/ditto_data/models/exchange.py`
- 新建: `packages/data/tests/unit/models/test_exchange_unit.py`

**复杂度**: S（单文件函数迁移）

---

### Task 3: 删除 dataset_mapping.py 并更新引用 `[S]`

**描述**: 删除 port 层的 `dataset_mapping.py`，所有引用改为使用 `Dataset.asset_class`。

**验收标准**:
- [ ] `dataset_mapping.py` 已删除
- [ ] `DATASET_ASSET_CLASS_MAP` 引用改为 `Dataset.asset_class`
- [ ] `infer_asset_class()` 引用改为 `Dataset(...).asset_class`
- [ ] `source_ticker_to_standard_ticker()` 引用改为 `datahub.models.exchange`
- [ ] 类型检查通过

**文件**:
- 删除: `apps/port/src/ditto_port/services/ingestion/dataset_mapping.py`
- 修改: `apps/port/src/ditto_port/services/ingestion/coordinator.py`
- 修改: `apps/port/src/ditto_port/cli/executor.py`
- 修改: `apps/port/src/ditto_port/jobs/flows/backfill.py`
- 删除: `apps/port/tests/unit/services/ingestion/test_dataset_mapping_unit.py`

**复杂度**: S（删除文件 + 更新 import）

**依赖**: Task 1, Task 2

---

## Phase 2: Port 层模型重构

### Task 4: 迁移 InstrumentIngestParams 并删除 ticker_resolver `[M]`

**描述**: 将 `InstrumentIngestParams` 移动到 `ditto_port/models/ingestion.py`，删除 `ticker_resolver.py` 中重复的功能。

**验收标准**:
- [ ] 新建 `ditto_port/models/ingestion.py` 包含 `InstrumentIngestParams`
- [ ] `ticker_resolver.py` 已删除
- [ ] `AmbiguousTickerError`/`NotFoundError` 引用改为 `datahub.errors`
- [ ] `resolve_source_ticker()` 调用改为 `MetadataService.resolve_source_ticker()`
- [ ] 所有引用已更新
- [ ] 类型检查通过

**文件**:
- 新建: `apps/port/src/ditto_port/models/ingestion.py`
- 删除: `apps/port/src/ditto_port/services/ingestion/ticker_resolver.py`
- 修改: `apps/port/src/ditto_port/services/ingestion/coordinator.py`
- 修改: `apps/port/src/ditto_port/cli/executor.py`
- 修改: `apps/port/src/ditto_port/jobs/flows/backfill.py`
- 删除: `apps/port/tests/unit/services/ingestion/test_ticker_resolver_unit.py`

**复杂度**: M（多文件修改 + 逻辑调整）

---

### Task 5: 删除 IngestionDataSource Protocol `[S]`

**描述**: 删除冗余的 `IngestionDataSource` Protocol，Coordinator 直接依赖 `DataSource` 基类。

**验收标准**:
- [ ] `protocols.py` 已删除
- [ ] Coordinator 类型注解改为 `DataSource`
- [ ] 类型检查通过

**文件**:
- 删除: `apps/port/src/ditto_port/services/ingestion/protocols.py`
- 修改: `apps/port/src/ditto_port/services/ingestion/coordinator.py`

**复杂度**: S（删除文件 + 类型注解修改）

**依赖**: Task 3, Task 4

---

## Phase 3: 命名统一

### Task 6: 统一命名 by_ticker → by_instrument `[M]`

**描述**: 重命名所有使用 `by_ticker` 的方法、类和 Flow，统一为 `by_instrument`。

**验收标准**:
- [ ] `ingest_by_ticker()` → `ingest_by_instrument()`
- [ ] `backfill_single_ticker_flow` → `backfill_single_instrument_flow`
- [ ] `backfill_multiple_tickers_flow` → `backfill_multiple_instruments_flow`
- [ ] `TickerBackfillConfig` → `InstrumentBackfillConfig`
- [ ] `TickerBackfillResult` → `InstrumentBackfillResult`
- [ ] 测试文件重命名 `test_coordinator_ticker_unit.py` → `test_coordinator_instrument_unit.py`
- [ ] 所有引用已更新
- [ ] 类型检查通过

**文件**:
- 修改: `apps/port/src/ditto_port/cli/executor.py`
- 修改: `apps/port/src/ditto_port/jobs/flows/backfill.py`
- 修改: `apps/port/src/ditto_port/services/ingestion/coordinator.py`
- 重命名: `apps/port/tests/unit/services/ingestion/test_coordinator_ticker_unit.py`

**复杂度**: M（多文件重命名 + 批量替换）

**依赖**: Task 5

---

## Phase 4: CLI 命令重构

### Task 7: 合并 ticker 命令到域命令 `[L]`

**描述**: 删除独立的 `ticker.py` 命令文件，在 `market.py`、`fundamental.py`、`capital.py` 中增加单标的摄取能力。

**验收标准**:
- [ ] `ticker.py` 命令文件已删除
- [ ] `__init__.py` 中移除 `ticker_app` 注册
- [ ] `market.py` 支持 `--ticker/--standard-ticker/--instrument-id + --start/--end` 模式
- [ ] `fundamental.py` 支持 `--ticker/--standard-ticker/--instrument-id + --start/--end` 模式
- [ ] `capital.py` 支持 `--ticker/--standard-ticker/--instrument-id + --start/--end` 模式
- [ ] 参数互斥逻辑正确（date vs 标识符+时间范围）
- [ ] CLI 帮助信息清晰
- [ ] 集成测试通过

**文件**:
- 删除: `apps/port/src/ditto_port/cli/commands/ingest/ticker.py`
- 修改: `apps/port/src/ditto_port/cli/commands/ingest/__init__.py`
- 修改: `apps/port/src/ditto_port/cli/commands/ingest/market.py`
- 修改: `apps/port/src/ditto_port/cli/commands/ingest/fundamental.py`
- 修改: `apps/port/src/ditto_port/cli/commands/ingest/capital.py`
- 新建: `apps/port/tests/integration/cli/test_ingest_instrument_integration.py`

**复杂度**: L（多文件修改 + 参数逻辑 + 测试）

**依赖**: Task 6

---

## Phase 5: DataSource 扩展（可选，后续 Phase）

> 以下任务为后续扩展，不在当前实施范围内。

### Task 8: 扩展 etf_daily 支持单标的摄取 `[M]` (后续)

### Task 9: 扩展 index_daily 支持单标的摄取 `[M]` (后续)

### Task 10: 扩展 adj_factor/valuation_metrics 支持单标的摄取 `[M]` (后续)

---

## 验收清单

### 功能验收
- [ ] `pixi run ingest market stock --ticker 000001 --start 2024-01-01 --end 2024-01-31` 正常工作
- [ ] `pixi run ingest market stock 2024-01-15` 正常工作（按日期模式）
- [ ] `pixi run ingest fundamental balance_sheet --ticker 000001 ...` 正常工作

### 代码质量
- [ ] `pixi run -e dev type` 通过
- [ ] `pixi run -e dev lint` 通过
- [ ] `pixi run -e dev test --unit` 通过

### 文件清理
- [ ] `ticker.py` 已删除
- [ ] `ticker_resolver.py` 已删除
- [ ] `protocols.py` 已删除
- [ ] `dataset_mapping.py` 已删除
- [ ] `test_ticker_resolver_unit.py` 已删除
- [ ] `test_dataset_mapping_unit.py` 已删除

---

## 执行顺序

```
1. Task 1 (AssetClass 枚举) ─────────────────────────────┐
                                                          │
2. Task 2 (exchange 转换) ────────────────────────────────┤
                                                          │
3. Task 3 (删除 dataset_mapping) ← Task 1, 2 ─────────────┤
                                                          ├──► 5. Task 5 (删除 Protocol)
4. Task 4 (迁移 InstrumentIngestParams) ──────────────────┘           │
                                                                      │
6. Task 6 (命名统一) ← Task 5 ────────────────────────────────────────┤
                                                                      │
7. Task 7 (CLI 重构) ← Task 6 ────────────────────────────────────────┘
```

**总预计工作量**: 7 个任务，约 2-3 小时
