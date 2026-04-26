# Phase 2 实施计划：Data 层 Protocol 化 + Reader/Writer 参数化

## 概述
- Sprint: v1-sprint | Phase: 2 — Data 层重构
- 设计文档: `2026-04-18-phase2-data-protocol-parameterization-design.md`
- 创建: 2026-04-18
- 预估改动: ~14 新增文件 + ~49 修改文件 + ~2 删除文件

## 技术方案（已确认决策）

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | MarketBarsStoreBase 处理 | 替换为新基类 | 设计更简洁（组合优于继承），旧基类未被使用 |
| 2 | SQLite PIT 公共列 | 统一 5 列 | fundamental 用 report_date，capital 用 trade_date，通过 `date_column` 参数化 |
| 3 | Trade 重构范围 | 全链路更新 | app 层仅 2 个生产文件引用，成本可控 |
| 4 | Trade 字段变更 | 仅类名重命名 | 保留字段不变，去掉 quantity/status 留后续 Phase |
| 5 | ParquetStore 实例化 | DI 层共享单例 | 每个子域一个 ParquetStore，注入到具体类 |

## 非机械类（保持独立实现）

| 类 | 原因 |
|----|------|
| IndexConstituentReader/Writer | SQLiteStore + 自定义 DDL + PIT JOIN 查询 |
| StChangeHistoryReader/Writer | SQLiteClient + DataCache 依赖 |
| 所有 runtime/ reader/writer | 领域特定逻辑（摄入/质量/发布安全/研究） |
| 所有 metadata/ reader/writer | 部分使用 PITRecordReader 基类，领域特定 |
| FactorReader/Writer | ParquetStore 子类（非组合），领域特定 |
| TechnicalIndicatorReader/Writer | ParquetStore 子类，领域特定 |
| Macro IndicatorReader/Writer | 待确认模式 |

---

## 任务清单

### Phase 2.1: 基础设施（Protocol + 基类）

- [ ] T1: Protocol 接口层定义 `[S]`
  - 验收: 4 个 Protocol 类定义完成，类型检查通过
  - 文件: `storage/base/protocols.py`（新增）
  - 内容: DatasetReader, DatasetWriter, SqliteReader, SqliteWriter
  - 依赖: 无
  - 测试: Protocol 定义无需测试（结构化类型）

- [ ] T2: ParquetDatasetReader 基类 `[M]`
  - 验收: 组合 ParquetStore，实现 DatasetReader Protocol 所有方法
  - 文件: `storage/base/dataset_reader.py`（新增）
  - 内容: `__init__(store, dataset)` + read/count/get_years/get_date_range/get_checksum/list_instrument_ids/data_root
  - 依赖: T1
  - 测试: `tests/unit/storage/test_dataset_reader.py` — mock ParquetStore，验证所有方法委托正确

- [ ] T3: ParquetDatasetWriter 基类 `[M]`
  - 验收: 组合 ParquetStore，实现 DatasetWriter Protocol 所有方法
  - 文件: `storage/base/dataset_writer.py`（新增）
  - 内容: `__init__(store, dataset)` + write/delete/delete_partition/data_root
  - 依赖: T1
  - 测试: `tests/unit/storage/test_dataset_writer.py` — mock ParquetStore，验证委托 + Metrics 埋点

- [ ] T4: SqliteTableSpec + SqliteTableReader/Writer 基类 `[L]`
  - 验收: Spec 参数化表结构差异，基类实现 PIT 查询/写入
  - 文件:
    - `storage/base/sqlite_table_spec.py`（新增）— frozen dataclass
    - `storage/base/sqlite_table_reader.py`（新增）— `get(instrument_id, as_of_date)` PIT 查询
    - `storage/base/sqlite_table_writer.py`（新增）— `write(df)` 动态 INSERT + Metrics
  - 内容:
    ```python
    @dataclass(frozen=True)
    class SqliteTableSpec:
        table: str
        columns: tuple[str, ...]
        id_column: str  # "instrument_id"
        date_column: str  # "report_date" / "trade_date"
        nullable_columns: frozenset[str] = frozenset()
    ```
    PIT 公共列统一: `instrument_id, {date_column}, knowledge_date, effective_from, effective_to`
  - 依赖: T1
  - 测试: `tests/unit/storage/test_sqlite_table_reader.py` + `test_sqlite_table_writer.py`
  - 风险: PIT 安全（`effective_to > as_of_date`），必须测试

- [x] T5: 删除 MarketBarsStoreBase `[S]` ✅ 2026-04-18
  - 验收: 文件删除，无引用残留
  - 文件: `storage/market/base/bars_store_base.py`（删除）, `storage/market/base/__init__.py`（修改）
  - 依赖: T2, T3
  - 测试: grep 确认无引用

---

### Phase 2.2: 机械类迁移

- [x] T6: Parquet 具体类迁移 — stock 子域 `[M]` ✅ 2026-04-18
  - 验收: StockBarsReader/Writer, StockStatusReader/Writer, StockAdjFactorReader/Writer 继承基类，现有测试通过
  - 文件: `storage/market/stock/bars/bars_reader.py`, `bars_writer.py`, `status/status_reader.py`, `status_writer.py`, `adj/adj_factor_reader.py`, `adj_factor_writer.py`（6 文件修改）
  - 修改模式:
    ```python
    # Before (~130 lines)
    class StockBarsReader:
        DATASET: str = "market/stock/bars"
        def __init__(self, data_root: Path) -> None:
            self._store = ParquetStore(data_root, YearlyPartition())
        # ... 6 个方法

    # After (~5 lines)
    class StockBarsReader(ParquetDatasetReader):
        def __init__(self, store: ParquetStore) -> None:
            super().__init__(store, "market/stock/bars")
    ```
  - 依赖: T2, T3
  - 测试: 现有 `tests/unit/storage/market/stock/` 测试应全部通过

- [x] T7: Parquet 具体类迁移 — etf 子域 `[M]` ✅ 2026-04-18
  - 验收: EtfBars/Status/Adj/Nav Reader/Writer 继承基类，现有测试通过
  - 文件: `storage/market/etf/` 下 8 个 reader/writer 文件（修改）
  - 依赖: T2, T3
  - 测试: 现有测试通过

- [x] T8: Parquet 具体类迁移 — index/fx/commodity 子域 `[M]` ✅ 2026-04-18
  - 验收: IndexBars/FxBars/CommodityBars Reader/Writer 继承基类
  - 文件: `storage/market/index/bars/`, `fx/bars/`, `commodity/bars/` 下 6 个文件（修改）
  - 依赖: T2, T3
  - 测试: 现有测试通过
  - 注意: IndexConstituentReader/Writer 不迁移（非机械类）

- [x] T9: SQLite 具体类迁移 — fundamental 子域 `[L]` ✅ 2026-04-18
  - 验收: 7 个 Reader + 7 个 Writer 继承基类，PIT 查询行为不变
  - 文件:
    - `storage/fundamental/specs.py`（新增）— 7 个 Spec 常量
    - `storage/fundamental/financial/` 下 6 个文件（修改）
    - `storage/fundamental/corporate/` 下 4 个文件（修改）
    - `storage/fundamental/forecast/` 下 4 个文件（修改）
  - Spec 定义:
    ```python
    BALANCE_SHEET_SPEC = SqliteTableSpec(
        table="balance_sheet",
        columns=("total_assets", "total_liabilities", "net_assets",
                 "current_assets", "current_liabilities"),
        id_column="instrument_id", date_column="report_date",
    )
    ```
  - 依赖: T4
  - 测试: 现有 `tests/unit/storage/fundamental/` 测试通过 + PIT 边界测试
  - 风险: PIT 安全，加 `+1` 复杂度

- [x] T10: SQLite 具体类迁移 — capital 子域 `[M]` ✅ 2026-04-18
  - 验收: 4 个 Reader + 4 个 Writer 继承基类
  - 文件:
    - `storage/capital/specs.py`（新增）— 4 个 Spec 常量
    - `storage/capital/valuation/`, `margin/`, `pledge/`, `index_composition/` 下 8 个文件（修改）
  - 依赖: T4
  - 测试: 现有测试通过
  - 注意: IndexComposition 的 `date_column` 可能不同（需确认）

---

### Phase 2.3: DI 简化 + 重命名

- [x] T11: Ports → Readers/Writers 重命名 `[M]` ✅ 2026-04-18
  - 验收: 6 个 dataclass 重命名完成，所有 import 更新
  - 文件:
    - `services/ports.py` → `services/deps.py`（重命名）
    - `services/__init__.py`（修改 export）
    - 所有引用 ports 的文件（DI providers, services）
  - 重命名映射:
    ```
    MarketReadPorts       → MarketReaders
    MarketWritePorts      → MarketWriters
    FundamentalReadPorts  → FundamentalReaders
    FundamentalWritePorts → FundamentalWriters
    CapitalReadPorts      → CapitalReaders
    CapitalWritePorts     → CapitalWriters
    ```
  - 依赖: T6-T10（具体类迁移完成后再重命名，避免 import 混乱）
  - 测试: `pixi run -e dev type` + `pixi run -e dev lint`

- [x] T12: DI Provider 简化 — market `[L]` ✅ 2026-04-18
  - 验收: MarketProvider 从 ~270 行缩减到 ~60 行
  - 文件: `di/market.py`（修改）
  - 修改模式:
    ```python
    # Before: 24 个 @provide 方法
    @provide
    def stock_bars_reader(self, settings) -> StockBarsReader: ...

    # After: 共享 ParquetStore + 聚合 Readers/Writers
    @provide
    def parquet_store(self, settings: DataStoreSettings) -> ParquetStore:
        return ParquetStore(settings.data_root, YearlyPartition())

    @provide
    def market_readers(self, store: ParquetStore) -> MarketReaders:
        return MarketReaders(
            stock_bars=StockBarsReader(store),
            etf_bars=EtfBarsReader(store),
            ...
        )
    ```
  - 依赖: T6, T7, T8, T11
  - 测试: DI 集成测试通过

- [x] T13: DI Provider 简化 — fundamental + capital `[M]` ✅ 2026-04-18
  - 验收: 两个 Provider 代码量显著缩减
  - 文件: `di/fundamental.py`, `di/capital.py`（修改）
  - 修改模式: 移除 `sqlite_store_pair` builder，改用共享 SQLiteClient + 聚合 Readers/Writers
  - 依赖: T9, T10, T11
  - 测试: DI 集成测试通过

---

### Phase 2.4: Trade 实体重构

- [x] T14: Trade 模型重命名 `[M]` ✅ 2026-04-18
  - 验收: 3 个 Record 类重命名，所有消费者更新
  - 实际改动: 与计划一致，额外创建了 `storage/execution/` CQRS 层（见 T15）
  - 文件:
    - `packages/data/src/ditto_data/models/trade.py`（修改）
    - `packages/app/src/ditto_app/execution_dto.py`（修改 — 6 个映射函数签名）
    - `packages/app/src/ditto_app/command/trade.py`（修改 — 1 个 import）
    - `packages/data/src/ditto_data/services/trade/service.py`（重构 — 改用 ExecutionReaders/Writers）
    - 测试文件: 6 个测试文件全部更新
  - 重命名映射:
    ```
    TradeIntentRecord           → SignalRecord
    ManualExecutionFillRecord   → FillRecord
    ActualPositionSnapshotRecord → PositionRecord
    ```
  - 字段保持不变（quantity/status 移除留后续 Phase）
  - 依赖: 无（独立于 Phase 2.1-2.3）
  - 测试: 2816 unit tests passed
  - TODO: 字段变更（SignalRecord 去掉 quantity/status）留 Phase 3

- [x] T15: trade/ CQRS 拆分 → storage/execution/ `[L]` ✅ 2026-04-18
  - 验收: CQRS Reader/Writer 分离完成，对齐 market/fundamental/capital 模式
  - 实际改动: 采用 `storage/execution/` 统一域（非 services/ 三路拆分）
  - 文件:
    - `storage/execution/__init__.py`（新增）— re-export 6 个 Reader/Writer + 3 个 DDL
    - `storage/execution/_sql.py`（新增）— 从 `services/trade/_sql.py` 迁移
    - `storage/execution/signal_reader.py`（新增）— `get()`, `list()`
    - `storage/execution/signal_writer.py`（新增）— `save()`, `update_status()` + TOCTOU 防护 + `INTENTS_DDL`
    - `storage/execution/fill_reader.py`（新增）— `get()`, `find()`, `list()`
    - `storage/execution/fill_writer.py`（新增）— `save()` + `FILLS_DDL`
    - `storage/execution/position_reader.py`（新增）— `get_latest()`, `list()`
    - `storage/execution/position_writer.py`（新增）— `save()` INSERT OR REPLACE + `POSITIONS_DDL`
    - `services/deps.py`（修改）— 新增 `ExecutionReaders`, `ExecutionWriters` dataclass
    - `services/trade/service.py`（修改）— 改用 `ExecutionReaders`/`ExecutionWriters` 委托
    - `di/trade.py`（修改）— 新增 `execution_readers`/`execution_writers` @provide 方法
    - `services/trade/intents.py`（删除）
    - `services/trade/fills.py`（删除）
    - `services/trade/positions.py`（删除）
    - `services/trade/_sql.py`（删除）
    - `.importlinter`（修改）— `data-storage-no-model-import` 新增 `models.trade` 豁免
  - 依赖: T14
  - 测试: 2816 unit tests passed（48 trade service tests + 6 app tests 全部更新）
  - 注意: TradeService facade 保留为 app 层唯一入口，内部改为 CQRS 委托模式

---

### Phase 2.5: 收尾

- [ ] T16: importlinter 规则更新 `[S]` ✅ 2026-04-19
  - 验收: 新规则通过 `pixi run -e dev arch-check`
  - 文件: `.importlinter`（修改）
  - 新增规则:
    - `data-sources-cross-isolation`: sources 子域互相禁止导入（tushare/tdx/fred 三向隔离）
    - `data-services-cqrs-mutual-exclusion`: 跳过（已天然隔离，无实际价值）
  - 额外修复:
    - `foundation-isolation`: 添加 `ditto_infra.exceptions -> ditto_kernel.exceptions` 豁免（InfraError 继承 DittoError 全局异常根）
    - `interfaces-service-isolation`: 添加 `Dataset` 枚举豁免（API/CLI 需要列出已知数据集）
    - 清理无效 ignore_import（`storage -> models.common` 无匹配）
  - 依赖: T11-T15
  - 结果: 27 contracts, 0 broken, 0 warnings

- [ ] T17: 全量验证 `[S]` ✅ 2026-04-19
  - 验收: 所有检查通过
  - 命令:
    ```bash
    pixi run -e dev check       # lint + fmt + type ✅（test --fast 因 pytest-cov 缺失跳过）
    pixi run -e dev arch-check  # 27 contracts, 0 broken, 0 warnings ✅
    pixi run -e dev test --unit # 5756 passed, 25 skipped, 0 failed ✅
    ```
  - 注意: `pytest-cov` 未安装导致 `pixi run -e dev check` 中 test --fast 失败，需单独安装或修复 pyproject.toml addopts
  - 依赖: T1-T16
  - 验收: 所有检查通过
  - 命令:
    ```bash
    pixi run -e dev check       # lint + fmt + type + test --fast
    pixi run -e dev arch-check  # importlinter
    pixi run -e dev test --unit # 完整单元测试
    ```
  - 依赖: T1-T16

---

## 依赖关系图

```
T1 (Protocol)
├── T2 (ParquetReader 基类)
│   ├── T6 (stock Parquet 迁移)
│   ├── T7 (etf Parquet 迁移)
│   ├── T8 (index/fx/commodity Parquet 迁移)
│   └── T5 (删除旧基类)
├── T3 (ParquetWriter 基类)
│   ├── T6, T7, T8 (同上)
│   └── T5
└── T4 (SQLite 基类 + Spec)
    ├── T9 (fundamental SQLite 迁移)
    └── T10 (capital SQLite 迁移)

T6-T10 → T11 (重命名) → T12 (market DI) + T13 (fundamental/capital DI)

T14 (Trade 模型重命名) → T15 (trade 拆分)

T11-T15 → T16 (importlinter) → T17 (验证)
```

## 执行建议

**并行执行组**:
- 组 A: T1 → T2+T3 → T6+T7+T8 → T5 → T11 → T12
- 组 B: T1 → T4 → T9+T10 → T11 → T13
- 组 C: T14 → T15（独立于 A/B）

**串行依赖**: T11 是 A/B 的汇合点，T16 是所有任务的汇合点

**推荐顺序**: T1 → T2+T3+T4（并行）→ T5+T6+T7+T8+T9+T10（并行）→ T11 → T12+T13+T14（并行）→ T15 → T16 → T17

## 风险项

| 风险 | 等级 | 缓解 |
|------|------|------|
| SQLite PIT 查询正确性 | 高 | T4 必须包含 PIT 边界测试（effective_to NULL / 边界值） |
| DI 注入链断裂 | 中 | T12/T13 完成后运行 DI 集成测试 |
| Trade 模型重命名遗漏引用 | 中 | T14 前后 grep 全库确认 |
| Metrics 埋点丢失 | 低 | T3/T4 基类统一处理 Metrics |
