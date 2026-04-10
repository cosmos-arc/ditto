# Layer 1: 数据摄取缺口实施计划

**日期**: 2026-03-19
**状态**: ✅ 已完成（13/15 gap 已实施，2/15 延后）
**范围**: 全部 15 个缺口（P0×3 + P1×7 + P2×5）
**来源**: [2026-03-18-daily-strategy-readiness-gap-analysis.md](2026-03-18-daily-strategy-readiness-gap-analysis.md)

---

## Context

Layer 1 数据摄取层当前完备度 90%，目标 100%。15 个缺口中，**大部分基础设施已就绪**（DQ YAML 规则、Quarantine、FreezeManager、FileLockManager），核心问题是**未接入摄入写路径**。少数缺口是数据源字段遗漏（out_date、weight、财报字段）和功能缺失（Cursor 持久化、调度器）。

**Gap 文档修正**: ING-DQ-1 说"DQ YAML 规则为空"不准确——5 个 YAML 规则文件已存在且完善（stock_daily, index_daily, etf_daily, adj_factor, index_weight），真正缺口是 QualityService 未接入 coordinator 写路径。

---

## 实施分阶段

```
Phase 1: 基础设施 (ING-CU-1)                    ← 无依赖，立即开始
Phase 2: 写路径集成 (ING-DQ-1/2, ING-FL-1)       ← 依赖 Phase 1
Phase 3: 数据正确性 (ING-IC-1, ING-IC-2, ING-A-1) ← 依赖 Phase 2
Phase 4: 数据丰富度 (ING-F-1, ING-SS-1, ING-ST-1, ING-X-2) ← 依赖 Phase 2（与 Phase 3 并行）
Phase 5: 调度+增强 (ING-X-1, ING-SS-2, ING-C-1, ING-C-2)    ← 依赖全部
```

---

## Phase 1: IngestionCursor 持久化 (ING-CU-1) [P0, M]

**问题**: `IngestionCursor` model 存在但无 Reader/Writer/SQLite 表，断点续传不可用。

### 修改清单

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `packages/data/src/ditto_data/scripts/schema.sql` | 添加 `ingestion_cursor` 表（PK: dataset+source） |
| Create | `packages/data/src/ditto_data/stores/runtime/ingestion/ingestion_cursor_writer.py` | SQLite UPSERT，复用 `IngestionLogWriter` 模式 |
| Create | `packages/data/src/ditto_data/stores/runtime/ingestion/ingestion_cursor_reader.py` | `get_cursor()`, `list_cursors()`, `get_last_success()` |
| Create | `packages/data/src/ditto_data/services/ingestion_cursor_service.py` | 组合 Reader/Writer |
| Modify | `packages/data/src/ditto_data/stores/runtime/ingestion/__init__.py` | 导出新类 |
| Modify | `apps/port/src/ditto_port/registry/datahub/runtime.py` | DI 注册 provider |
| Modify | `apps/port/src/ditto_port/services/ingestion/coordinator.py` | `__init__` 接受 `IngestionCursorService`，`_fetch_and_ingest()` 成功/失败后更新 cursor |
| Modify | `apps/port/src/ditto_port/services/ingestion/factory.py` | 传递 cursor service |
| Create | `packages/data/tests/unit/stores/runtime/ingestion/test_ingestion_cursor_writer.py` | |
| Create | `packages/data/tests/unit/stores/runtime/ingestion/test_ingestion_cursor_reader.py` | |

### 关键实现

SQLite 表结构（复用 `IngestionLogWriter` 的 `_create_tables()` 模式）：
```sql
CREATE TABLE IF NOT EXISTS ingestion_cursor (
    dataset TEXT NOT NULL,
    source TEXT NOT NULL,
    last_success TEXT,
    last_attempted TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (dataset, source)
);
```

Coordinator 集成点：`_fetch_and_ingest()` 成功返回前（line ~458）调用 `cursor_service.update_cursor()`，异常返回前更新 `last_attempted`。

---

## Phase 2: 写路径集成 (ING-DQ-1, ING-DQ-2, ING-FL-1) [P0/P1, M]

**问题**: DQ YAML 规则已存在（5 个文件），QualityService 和 QuarantineWriter 已实现，但未接入 `_fetch_and_ingest()` 写路径。FreezeManager 已 DI 注册但从未调用。

### 修改清单

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `apps/port/src/ditto_port/services/ingestion/coordinator.py` | `__init__` 增加 `QualityService` + `FreezeManager` 参数；`_fetch_and_ingest()` 在 fetch→write 间插入 DQ check，write 成功后创建 freeze |
| Modify | `apps/port/src/ditto_port/services/ingestion/factory.py` | `create_coordinator()` 传递 quality_service 和 freeze_manager |
| Create | `apps/port/tests/unit/services/ingestion/test_coordinator_dq_freeze.py` | DQ block/quarantine/freeze 的 mock 测试 |

### 关键实现

`_fetch_and_ingest()` 新流程（当前 line 429-460）：
```
fetch → empty_check → [DQ check: cleaned_df, should_block] → quarantine if blocked → write → freeze → success
```

DQ check 位置：line 429（empty check）和 line 435（write）之间：
```python
if self._quality_service is not None:
    cleaned_df, should_block = self._quality_service.check_and_quarantine(
        df=df, dataset=dataset, context={"trade_date": trade_date}
    )
    if should_block:
        return self._result_handler.handle_dq_blocked(dataset, trade_date, WriteResult(blocked=True))
    df = cleaned_df
```

Freeze 位置：line 457（success handler）之后：
```python
if self._freeze_manager is not None:
    try:
        self._freeze_manager.create(
            freeze_id=f"{dataset}_{trade_date}",
            description=f"Auto-freeze: {dataset} @ {trade_date}",
            datasets=[...],
        )
    except Exception as e:
        logger.warning(f"Freeze failed (non-blocking): {e}")
```

**设计决策**：
- DQ/Freeze 参数为 `Optional`，None 时跳过（向后兼容）
- Freeze 失败不阻塞摄入（fire-and-forget）
- FreezeManager 已有 `cleanup_expired()` (TTL 90天)，T2 调度器中定期清理

---

## Phase 3: 数据正确性 (ING-IC-1, ING-IC-2, ING-A-1) [P0/P1, M]

### ING-IC-1: 指数成分 out_date [P0, S]

**问题**: `capital.py:402` fetch fields 缺少 `out_date`，PIT 查询返回已退出成分。

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `packages/data/src/ditto_data/sources/tushare/adapters/capital.py:402` | fields 加 `"ts_code,in_date,out_date,is_new"` |
| Modify | `packages/data/src/ditto_data/sources/tushare/processors/mappings/capital.py` | `INDEX_COMPOSITION_MAPPING` 添加 `out_date` 到 `date_columns`，添加 `computed_columns: effective_to` |
| Modify | `packages/data/src/ditto_data/sources/tushare/adapters/capital.py:411-423` | 移除 `pl.lit(None).alias("effective_to")` 硬编码，改用 mapping 产生的 `effective_to` |

### ING-IC-2: 指数权重 [P1, M]

**问题**: `capital.py:413` 权重硬编码 `pl.lit(1.0)`。

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `packages/data/src/ditto_data/sources/tushare/adapters/capital.py` | 新增 `fetch_index_weight(index_code, trade_date)` 方法，调用 Tushare `index_weight` API |
| Modify | `packages/data/src/ditto_data/sources/tushare/adapters/capital.py:398-440` | `fetch_index_composition()` 增加 `with_weight: bool = False` 参数，True 时调用 weight API 并 join |

**设计决策**: `with_weight=False` 默认值保持向后兼容。

### ING-A-1: 复权因子按 ticker 回填 [P1, S]

**问题**: `stock.py:242-276` 仅支持 `trade_date` 单日批量，无 `ts_code + start_date + end_date` 模式。

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `packages/data/src/ditto_data/sources/tushare/adapters/stock.py` | 新增 `fetch_adj_factor_by_ticker(ts_code, start_date, end_date)` 方法 |
| Modify | `packages/data/src/ditto_data/sources/base.py` | DataSource ABC 添加抽象方法 |

---

## Phase 4: 数据丰富度 (ING-F-1, ING-SS-1, ING-ST-1, ING-X-2) [P1/P2, L+M]

**注意**: Phase 4 与 Phase 3 可并行开发。

### ING-F-1: 财报字段扩展 [P1, L]

**问题**: 三张财报表仅取 5-6 个字段。

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `packages/data/src/ditto_data/sources/tushare/adapters/fundamental.py` | 扩展三个 adapter 方法的 fetch fields |
| Modify | `packages/data/src/ditto_data/sources/tushare/processors/mappings/capital.py` | 扩展 `BALANCE_SHEET_MAPPING`, `INCOME_STATEMENT_MAPPING`, `CASH_FLOW_MAPPING` |
| Modify | `packages/data/src/ditto_data/scripts/schema.sql` | 三个 SQLite 表添加新列（ALTER TABLE ADD COLUMN） |

扩展字段（Tushare API 支持）：
- **Balance Sheet**: +inventory, fixed_assets, cash_equivalents, accounts_receivable, short_term_debt, long_term_debt, money_cap, total_share
- **Income**: +operate_cost, sale_exp, admin_exp, fin_exp, rd_exp, total_profit, income_tax, diluted_eps
- **Cash Flow**: +depreciation, interest_paid, tax_paid

SQLite 列新增使用 `ALTER TABLE ADD COLUMN ... DEFAULT NULL`，不影响现有数据。

### ING-SS-1: list_status 历史 [P1, M]

**问题**: `stock_basic` API 无日期参数，返回当前快照。

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `packages/data/src/ditto_data/sources/tushare/adapters/stock.py` | `_fetch_list_status_data()` 改用 `list_date` 参数获取历史快照 |

**Tushare API**: `stock_basic` 支持 `list_date` 参数返回该日期的有效证券列表。Fallback: 若 API 不支持则退回当前快照。

### ING-ST-1: ST 状态变更历史 [P1, M]

**问题**: `stock_st` 返回当前 ST 股票，无变更日期。

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `packages/data/src/ditto_data/sources/tushare/adapters/stock.py` | 新增 `fetch_st_history()` 方法，使用 `namechange` API（提供 start_date, change_reason） |

**Tushare API**: `namechange` 返回历史名称变更记录，`change_reason` 包含 "ST"/"*ST"/"撤销ST" 等标记。可据此推算 ST 的 effective_from/to。

### ING-X-2: 并发写入安全 [P2, M]

**问题**: read-modify-write 竞态。

| 操作 | File | 说明 |
|------|------|------|
| Audit | 所有 Parquet Writer | 确认 FileLock + atomic_write 使用情况 |
| Modify | 未覆盖的 Writer | 添加 FileLock 保护 |

**关键**: `MarketService.save_bars()` 已使用 FileLock。需审计 FundamentalService、CapitalService、MetadataService 的写路径。

---

## Phase 5: 调度+增强 (ING-X-1, ING-SS-2, ING-C-1, ING-C-2) [P2, L+S+M]

### ING-X-1: Prefect 调度器 [P2, L]

**问题**: T0/T1/T2/T3 需手动触发。

| 操作 | 文件 | 说明 |
|------|------|------|
| Modify | `apps/port/src/ditto_port/jobs/flows/daily.py` | 添加 cron schedule 定义 |
| Create | `apps/port/src/ditto_port/jobs/flows/t2_gap_scan.py` | T2 空洞扫描 Flow（查 cursor → 对比日历 → 回填） |
| Create | `apps/port/src/ditto_port/jobs/flows/scheduler.py` | Prefect deployment 配置 |

调度时间：
- T0: 每日 8:00（交易日）
- T1: 每日 18:30（交易日）
- T2: 每日 2:00 AM
- T3: T1 完成后自动触发

### ING-SS-2: IPO 日期过滤 [P2, S]

| 操作 | File | 说明 |
|------|------|------|
| Modify | universe 相关 service | 添加 `min_list_days` 参数过滤 |

### ING-C-1 + ING-C-2: 股本变动+回购/配股 [P2, M each]

| 操作 | File | 说明 |
|------|------|------|
| Modify | `packages/data/src/ditto_data/sources/tushare/adapters/capital.py` | 新增 `fetch_share_float()` + `fetch_rights_bonus()` |
| Modify | `packages/data/src/ditto_data/sources/tushare/processors/mappings/capital.py` | 新增 `SHARE_FLOAT_MAPPING` + `RIGHTS_BONUS_MAPPING` |
| Create | 新 Store files | 股本变动和回购数据的读写 |

---

## 复用的现有基础设施

| 组件 | 位置 | 复用方式 |
|------|------|----------|
| `QualityService.check_and_quarantine()` | `apps/port/.../quality/service.py` | 直接注入 Coordinator |
| `FreezeManager` | `packages/data/.../runtime/freeze_manager.py` | 直接注入 Coordinator |
| `FileLockManager` | `packages/infra/.../concurrency/` | 审计+补充到未覆盖 Writer |
| `ParquetStore.atomic_write()` | `packages/data/.../base/parquet_store.py` | 确保所有 Writer 使用 |
| `IngestionLogWriter` 模式 | `packages/data/.../ingestion/ingestion_log_writer.py` | Cursor Writer 参考实现 |
| `DQ YAML rules` (5 files) | `packages/data/config/dq_rules/` | 已完备，无需修改 |
| `QuarantineWriter/Reader` | `packages/data/.../quality/` | 通过 QualityService 自动触发 |
| `TushareClient` (rate limit + retry) | `packages/data/.../tushare/client.py` | 所有新 API 调用复用 |

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| DQ check 增加写入延迟 | 每次摄入多 L1/L2 检查 | QualityEngine 对无规则的 dataset 立即返回；L2 仅 warning |
| Freeze point 膨胀 | 数千个 manifest 文件 | `cleanup_expired()` TTL 90天，T2 定期清理 |
| SQLite ALTER TABLE | 现有数据兼容 | ADD COLUMN DEFAULT NULL，不影响现有查询 |
| Tushare API 限流 | 新增 API 调用 | 已有 `tushare_fetch_error_handler` (3次重试 + 限流) |
| ST 历史 API 可用性 | namechange API 可能不全 | Fallback 到当前快照，系统降级但不中断 |

---

## 验证计划

```bash
# 单元测试
pixi run -e dev test --unit

# 类型检查
pixi run -e dev type

# 完整检查
pixi run -e dev check

# 集成测试（需要 Tushare token）
pixi run -e dev test --integration -m ingestion
```

Phase 1 验证重点：
- Cursor writer upsert 幂等性
- Coordinator 成功/失败后 cursor 更新正确

Phase 2 验证重点：
- DQ block 时数据不写入 store、quarantine 被触发
- DQ pass 时数据正常写入
- quality_service=None 时跳过 DQ（向后兼容）
- Freeze 在成功后创建、失败时不创建

Phase 3 验证重点：
- 指数成分含 out_date 的 PIT 查询正确
- Per-ticker adj_factor 回填数据完整

Phase 4 验证重点：
- 扩展财报字段正确映射
- list_date 历史快照正确
- 并发写入无数据损坏

Phase 5 验证重点：
- Prefect flow 编排正确
- T2 空洞检测+回填完整
