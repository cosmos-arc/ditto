# Ditto 设计质量分析 — 过度设计、缺乏抽象与遗留代码

> **视角**: YAGNI / KISS / DRY / Simple Design
> **日期**: 2026-04-17

---

## 一、过度设计与过度抽象（17 项）

### 1.1 DataSource 基类 — 26 个抽象方法的"上帝接口"

**位置**: [sources/base.py:177-876](packages/data/src/ditto_data/sources/base.py#L177-L876)

DataSource ABC 定义了 26 个 `@abstractmethod`，涵盖股票/ETF/指数/外汇/商品/宏观/财报/融资融券等所有数据类型。任何实现者（TushareSource、FredSource、TdxSource）都必须实现全部 26 个方法，即使 FredSource 只需要宏观/商品数据也被迫 `raise NotImplementedError` 约 20 个方法。

**违反原则**: 接口隔离原则（ISP）——不应强迫客户端依赖它不使用的方法。

**业界对比**: NautilusTrader 将数据源接口拆分为 `LiveDataFeedFactory`（行情）、`HistoricalDataClient`（历史）、`DataCatalog`（目录查询）等窄接口。

**建议**: 按数据域拆分为 `MarketSource`、`FundamentalSource`、`CapitalSource`、`MacroSource` 4 个独立 Protocol/ABC，每个 5-7 个方法。

---

### 1.2 104 个 Reader/Writer 类 — CQRS 机械拆分

**位置**: `packages/data/src/ditto_data/storage/` 下 104 个文件

每个数据集被机械拆分为独立的 `*_reader.py` 和 `*_writer.py`。典型示例：

```python
class StockBarsReader:
    DATASET = "market/stock/bars"
    def __init__(self, data_root: Path):
        self._store = ParquetStore(data_root, YearlyPartition())
    def read(self, **kwargs): return self._store.read(self.DATASET, **kwargs)
    def count(self, **kwargs): return self._store.count(self.DATASET, **kwargs)
    # ... 所有 Reader 逻辑完全相同，只是 DATASET 路径不同
```

20+ 个 Parquet Reader 和 20+ 个 Parquet Writer 的代码几乎完全相同，唯一区别是 `DATASET` 字符串。

**违反原则**: DRY + KISS —— 用类继承来参数化一个字符串值。

**建议**: 用 `DatasetReader(data_root, "market/stock/bars")` 一个类替代所有 Parquet Reader，Writer 同理。104 个文件可缩减到 2-3 个。

---

### 1.3 表达式编译器 7 层架构 — 对内部 DSL 过度工程化

**位置**: `packages/analytics/src/ditto_analytics/expression/`（8 个文件，约 2300 行）

完整管线：Lexer → Parser (Pratt) → AST → Analyzer (类型系统) → Codegen → Compiler + Diagnostics + Registry + Cache。

DSL 只有约 40 个算子（ts_mean, cs_rank 等），用户是内部量化研究员。

**过度之处**:
- `analyzer.py` 实现了轻量类型系统（`_ExprType.FLOAT / STRING`），只用于产生 warnings，不影响编译结果
- `registry.py` 的 `int_literal_positions` 和 codegen 的 `_read_int_literal` 功能重叠
- `CompileIdentity` 有 10 个字段做缓存指纹，其中 5 个永远是硬编码常量

**业界对比**: Zipline 的 Pipeline API 直接用 Python AST 操作，无独立 Lexer/Parser；Qlib 的表达式引擎也是单文件约 500 行。

**建议**: 合并 analyzer 和 compiler 为一个模块，去掉类型检查 warning 系统（或提升为真正有用的验证），简化 CompileIdentity 到 3-4 个关键字段。

---

### 1.4 Ports 数据类 — 参数分组过度

**位置**: [services/ports.py:84-266](packages/data/src/ditto_data/services/ports.py#L84-L266)

6 个 dataclass（MarketReadPorts/WritePorts, FundamentalReadPorts/WritePorts, CapitalReadPorts/WritePorts），42 个字段，仅用于解决 `PLR0913` lint 告警。每个 Port 只被一个 Service 使用，没有行为，只是把构造函数参数搬到了容器里。

**违反原则**: YAGNI —— 为每个 Service 创建专属的参数容器类。

**建议**: 如果 DI 容器支持直接注入，让 Service 直接声明需要的 Reader/Writer；否则用通用的 `ServiceDeps` 替代 6 个专属 Ports。

---

### 1.5 5 层异常层次 — 过度分类

**位置**: [sources/base.py:11-175](packages/data/src/ditto_data/sources/base.py#L11-L175)

`DataSourceError → SourceConfigurationError / SourceAuthenticationError / SourceRateLimitError / SourceFetchError / SourceTransformationError`，每个子类有独立的 `details` dict 构建逻辑。

实际使用中，调用方只检查 `isinstance(error, SourceFetchError)`，对其他 4 种子类一视同仁。

**建议**: 用 `DataSourceError(message, error_type="config", **kwargs)` 一个类替代。

---

### 1.6 PartitionStrategy ABC — 只有一个实现

**位置**: [storage/base/partition_strategy.py:8-68](packages/data/src/ditto_data/storage/base/partition_strategy.py#L8-L68)

ABC 基类 + 3 个抽象方法，唯一实现 `YearlyPartition`。没有任何 MonthlyPartition、DailyPartition 存在。

**违反原则**: YAGNI。

**建议**: 删除 ABC，直接使用 `YearlyPartition` 类或函数。

---

### 1.7 DataProvider Protocol — 只有一个实现

**位置**: [provider.py:76-100](packages/data/src/ditto_data/provider.py#L76-L100)

Protocol 定义 4 个方法，唯一实现 `ServiceBackedDataProvider`。

**建议**: 保留（跨层接口定义有文档价值），但标记为单实现。

---

### 1.8 App Process 内部 Protocol — 解耦过度

**位置**:
- [process/ingestion/ports.py](packages/app/src/ditto_app/process/ingestion/ports.py) — `IngestDateHandlerProtocol`, `QualityCheckerProtocol`
- [process/execution/ports.py](packages/app/src/ditto_app/process/execution/ports.py) — `PositionReader`, `SignalDeliveryProtocol`
- [process/execution/strategy_types.py](packages/app/src/ditto_app/process/execution/strategy_types.py) — `RunLifecycleService` (8 个方法)

这些 Protocol 定义在 `ditto_app` 包内部，process 和 command 都在同一包内，不存在跨包依赖问题。每个 Protocol 只有一个实现者。

**违反原则**: Hexagonal Architecture 的 Port 应该定义在跨层边界上，而非包内模块间。

**建议**: 同包内直接使用具体类型，用 Optional 处理可选依赖。

---

### 1.9 FrameCol — 用类做字符串常量

**位置**: [engine/alpha/frame.py:15-30](packages/engine/src/ditto_engine/alpha/frame.py#L15-L30)

```python
class FrameCol:
    __slots__ = ()
    INSTRUMENT_ID: str = "instrument_id"
    SIGNAL: str = "signal_value"
```

带 `__slots__` 的类只存放 6 个字符串常量，返回值类型是 `str`，不提供类型安全。

**建议**: 用模块级常量或 `StrEnum` 替代。

---

### 1.10 DQResult 7 个 property — 重复遍历

**位置**: [kernel/quality.py:61-101](packages/kernel/src/ditto_kernel/quality.py#L61-L101)

`has_errors`、`has_warnings`、`has_alerts` 各遍历一次 issues；`error_count`、`warn_count`、`alert_count` 又各遍历一次。同一列表最多遍历 6 次。`total_count` 就是 `len(self.issues)` 的同义词。

**建议**: 用 `Counter(severity for i in issues)` 一次遍历。

---

### 1.11 CompileIdentity — 过度细化的缓存指纹

**位置**: [analytics/materialization/contracts.py:49-63](packages/analytics/src/ditto_analytics/materialization/contracts.py#L49-L63)

10 个字段中至少 5 个（`engine_codegen_version`, `analysis_version`, `polars_version`, `expr_serialization_format`, `global_compile_flags`）永远是硬编码常量。`operator_versions` 中所有算子版本都是 `"1.0.0"`。

**建议**: 简化为 `cache_key` + `operator_versions` 两个字段。

---

### 1.12 Parselet Protocol — 无外部扩展点

**位置**: [expression/parser.py:29-53](packages/analytics/src/ditto_analytics/expression/parser.py#L29-L53)

`PrefixParselet` / `InfixParselet` Protocol 用于 Pratt Parser，但所有 9 个 Parselet 实现都是内部 frozen dataclass，无外部扩展点。

**建议**: 用普通 ABC 或直接继承替代。

---

### 1.13 IngestionConfig BaseModel — 无消费者

**位置**: [app/process/ingestion/config.py:19-31](packages/app/src/ditto_app/process/ingestion/config.py#L19-L31)

Pydantic BaseModel，但无任何消费者。实际使用的是同文件中的 `IngestionCoordinatorConfig`（普通 dataclass）。

**建议**: 删除。

---

### 1.14 双层 Pipeline Protocol — 重复抽象

**位置**:
- [engine/alpha/protocols.py](packages/engine/src/ditto_engine/alpha/protocols.py) — `DecisionStage(Protocol)`
- [engine/backtest/steps/types.py](packages/engine/src/ditto_engine/backtest/steps/types.py) — `TradingStep(Protocol)`

两者本质都是"接收上下文，处理数据，返回结果"。

**建议**: 考虑统一为一个 `PipelineStage` Protocol。

---

### 1.15 StrategySpec 深层嵌套验证

**位置**: [engine/alpha/specs.py:132-253](packages/engine/src/ditto_engine/alpha/specs.py#L132-L253)

嵌套 6 层 dataclass，`__post_init__` 中 benchmark 白名单（9 个指数）硬编码在模型内部。`CostModelSpec` 在 engine 和 app 各有一个版本。

**建议**: benchmark 白名单移至配置，消除 CostModelSpec 重复定义。

---

### 1.16 6 个 App DI Provider — 注册表膨胀

**位置**: [app/providers.py](packages/app/src/ditto_app/providers.py)（506 行，6 个 Provider 类，30+ `@provide` 方法）

CQRS 的 R8 互斥规则迫使 query/command/process/builders 各自独立 Provider，增加了隔离单元数量。

**建议**: 评估 R8 规则是否可以用更轻量的方式执行（如 lint 规则），而非运行时隔离。

---

### 1.17 100+ Data DI @provide 方法 — 样板代码泛滥

**位置**: `packages/data/src/ditto_data/di/`（5 个 Provider，100+ `@provide` 方法）

70%+ 是 `return XxxReader(settings.data_root)` 或 `return _xxx_r(sqlite_client)` 的单行包装。`market.py` 有 `parquet_store_pair` 工厂可用但未使用。

**建议**: 创建 `register_store_pair()` 自动注册函数，消除手动包装。

---

## 二、缺乏抽象与缺乏简化（17 项）

### 2.1 TushareSource — 双模式参数校验重复 7 次

**位置**: [tushare_source.py:502-799](packages/data/src/ditto_data/sources/tushare/tushare_source.py#L502-L799)

以下 4 行校验在 7 个 fetch 方法中完全相同：

```python
if trade_date and source_ticker:
    raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
if not trade_date and not source_ticker:
    raise ValueError("必须指定 trade_date 或 source_ticker 之一")
```

**建议**: 提取 `_validate_dual_mode(trade_date, source_ticker)` 或 `@dual_mode_fetch` 装饰器。

---

### 2.2 CapitalTushareAdapter — 重复的 fetch 模板方法

**位置**: [adapters/capital.py:43-368](packages/data/src/ditto_data/sources/tushare/adapters/capital.py#L43-L368)

4 个 fetch 方法（valuation/dividend/margin/pledge）各约 40 行，80% 是相同的 logger + error_handler + query + transform + PIT 样板。

**建议**: 实现 `_fetch_with_pit(api_name, fields, mapping, **params)` 模板方法。

---

### 2.3 MarketService — _apply_adjustment 与 _apply_etf_adjustment 近乎相同

**位置**: [market_service.py:443-570](packages/data/src/ditto_data/services/market_service.py#L443-L570)

两个方法各 60+ 行，差异仅在于 adj_df 来源。join + sort + PIT 过滤逻辑完全相同。

**建议**: 合并为 `_apply_adjustment(df, adj_df, asof)` 一个方法。

---

### 2.4 MarketService — 4 个公开方法的 logger+Metrics 样板

**位置**: [market_service.py:648-813](packages/data/src/ditto_data/services/market_service.py#L648-L813)

`get_stock_bars`、`get_etf_bars`、`get_adj_factors`、`get_stock_status` 各约 35 行，实际业务逻辑仅 1 行。

**建议**: 提取 `_simple_read(dataset_name, reader_method, **kwargs)` 模板。

---

### 2.5 MetadataService — 17 个裸参数穿透

**位置**: [metadata_service.py:67-155](packages/data/src/ditto_data/services/metadata_service.py#L67-L155)

`CalendarService`、`InstrumentService`、`UniverseService` 三个子服务已构建好，但 `MetadataService` 仍保留 17 个裸参数，将它们原样保存为 `self._xxx` 形成冗余。

**建议**: 直接接受 3 个子服务作为参数，删除 17 个裸参数。

---

### 2.6 MetadataService — 50+ 个纯委托方法

**位置**: [metadata_service.py:164-558](packages/data/src/ditto_data/services/metadata_service.py#L164-L558)

558 行中约 40 个单行委托方法，每个都带 docstring 和参数签名重复。子服务接口变更需同步修改 facade。

**建议**: 评估 `__getattr__` 动态委托，或至少分组减少 docstring 重复。

---

### 2.7 TushareSource — 892 行纯委托门面

**位置**: [tushare_source.py](packages/data/src/ditto_data/sources/tushare/tushare_source.py)（892 行）

大部分是方法签名 + docstring + 一行 `return self._xxx.method(...)`。只有少数方法包含参数校验逻辑。

**建议**: 纯委托部分用 `__getattr__` 自动生成。

---

### 2.8 Dataset 枚举 @property — 巨型 if-in 元组链

**位置**: [models/common.py:100-169](packages/data/src/ditto_data/models/common.py#L100-L169)

`asset_class` 属性有 10 个枚举值的 `if-in` 判断，`date_schedule` 有 16 个。每新增枚举值都需同步修改。

**建议**: 用类级别字典映射或在枚举定义中直接声明。

---

### 2.9 InstrumentIdRange — 范围定义重复 3 次

**位置**: [models/common.py:293-390](packages/data/src/ditto_data/models/common.py#L293-L390)

`{"stock": (1M, 2M), "etf": (2M, 3M), ...}` 映射在 `get_range`、`detect_asset_class`、`display_names` 三处以不同形式重复。

**建议**: 定义 `_RANGES` 类常量，所有方法引用同一数据源。

---

### 2.10 MarketService — 硬编码资产类别字符串

**位置**: [market_service.py:351-396](packages/data/src/ditto_data/services/market_service.py#L351-L396)

12 处使用 `"stock"`, `"etf"`, `"index"` 等硬编码字符串，而非已存在的 `AssetClass` 枚举。

**建议**: 使用 `AssetClass` 枚举。

---

### 2.11 CLI ingest commands — 重复的 wrapper 函数

**位置**: [cli/commands/ingest/market.py:59-107](interfaces/src/ditto_interfaces/cli/commands/ingest/market.py#L59-L107)

已有 `create_daily_command` 工厂，但手动创建 wrapper 仅为了自定义命令名。

**建议**: 扩展工厂接受命令名参数，或用 `app.command("name")(create_daily_command(...))` 直接注册。

---

### 2.12 IngestionCoordinator — 硬编码 Dataset 枚举列表

**位置**: [coordinator.py:287-298](packages/app/src/ditto_app/process/ingestion/coordinator.py#L287-L298)

手动列举 9 个 Dataset 枚举值判断是否需要交易日检查，与 `Dataset.date_schedule` 属性逻辑重复且不完整。

**建议**: 使用 `dataset_enum.date_schedule == DateScheduleType.TRADING_DAYS`。

---

### 2.13 engine/order_book.py — 硬编码默认 datetime

**位置**: [order_book.py:89](packages/engine/src/ditto_engine/accounting/order_book.py#L89)

`datetime(2026, 1, 1)` 作为默认值出现在 3 处。

**建议**: 定义 `EPOCH_DEFAULT` 常量。

---

### 2.14巨型源文件

| 文件 | 行数 | 建议 |
|------|------|------|
| [factor_analysis.py](packages/analytics/src/ditto_analytics/evaluation/metrics/factor_analysis.py) | 973 | 拆分为 4 个独立算法模块 |
| [tushare_source.py](packages/data/src/ditto_data/sources/tushare/tushare_source.py) | 892 | 纯委托部分自动化（案例 2.7） |
| [sources/base.py](packages/data/src/ditto_data/sources/base.py) | 886 | 异常层级分离 |
| [instrument.py](packages/data/src/ditto_data/services/metadata/instrument.py) | 847 | 评估拆分 |
| [market_service.py](packages/data/src/ditto_data/services/market_service.py) | 813 | 模板方法提取后可缩减 |
| [statistics.py](packages/engine/src/ditto_engine/backtest/statistics.py) | 812 | 评估拆分 |
| [evaluator.py](packages/analytics/src/ditto_analytics/evaluation/evaluator.py) | 750 | 评估拆分 |
| [codegen.py](packages/analytics/src/ditto_analytics/expression/codegen.py) | 740 | 表达式编译器简化后可缩减 |
| [coordinator.py](packages/app/src/ditto_app/process/ingestion/coordinator.py) | 733 | 硬编码消除后可缩减 |
| [parquet_store.py](packages/data/src/ditto_data/storage/base/parquet_store.py) | 732 | 评估拆分 |
| [capital.py (adapter)](packages/data/src/ditto_data/sources/tushare/adapters/capital.py) | 725 | 模板方法提取后可缩减 |

---

## 三、遗留代码与死代码

### 3.1 _KNOWN_DATASETS — 5 处独立维护

以下 5 个位置各自维护了数据集列表，且**互不完全一致**：

| 位置 | 数量 | 缺少 |
|------|------|------|
| [models/common.py](packages/data/src/ditto_data/models/common.py) Dataset 枚举 | 28 | — |
| [interfaces/cli/ops.py](interfaces/src/ditto_interfaces/cli/ops.py) `_KNOWN_DATASETS` | ~25 | 缺 `index_weight`（实际 bug） |
| [app/config.py](packages/app/src/ditto_app/config.py) 数据集配置 | ~20 | 与枚举不同步 |
| [coordinator.py](packages/app/src/ditto_app/process/ingestion/coordinator.py) 交易日列表 | 9 | 不完整 |
| Dataset 枚举 `date_schedule` 属性 | 16 | 与枚举总数不同步 |

**最大风险**: `ops.py` 缺少 `index_weight`，CLI 运维命令会遗漏该数据集的状态检查。

**建议**: Dataset 枚举作为唯一权威数据源，其他位置通过 `Dataset.<enum>.value` 或集中配置获取。

---

### 3.2 TODO/FIXME/HACK 注释

| 位置 | 内容 |
|------|------|
| `packages/analytics/src/ditto_analytics/expression/codegen.py` | 多处 `# TODO: optimize` |
| `packages/engine/src/ditto_engine/backtest/engine.py` | `# FIXME: edge case` |
| `packages/data/src/ditto_data/storage/base/parquet_store.py` | `# HACK: workaround` |

---

### 3.3 空目录

| 目录 | 说明 |
|------|------|
| [services/hot_layer/](packages/data/src/ditto_data/services/hot_layer/) | 预留目录，只有空 `__init__.py` |
| [storage/market/fx/](packages/data/src/ditto_data/storage/market/fx/) | FxBarsReader/Writer 各仅 1 个文件 |

---

### 3.4 未使用的 re-export

| 位置 | 说明 |
|------|------|
| `packages/kernel/src/ditto_kernel/__init__.py` | 导出 `ImpactModel` 但包外无引用 |
| `packages/app/src/ditto_app/command/__init__.py` | re-export 18 个符号 |

---

### 3.5 重复定义

| 内容 | 位置 | 建议 |
|------|------|------|
| `CostModelSpec` | engine/specs.py + app/contracts.py | 保留一份 |
| `AdjType` 枚举 | data/market_service.py (局部) + kernel | 移至 kernel |
| 异常 `DataSourceError` | data/sources/base.py + data/errors.py | 合并 |
| 异常 `SourceFetchError` | data/sources/base.py + data/errors.py | 合并 |
| 异常 `ValidationError` | interfaces/ + data/ | 合并 |

---

## 四、改进建议（按优先级）

### 优先级 1：消除最大维护成本（影响全局）

| # | 建议 | 预估收益 | 难度 |
|---|------|----------|------|
| 1 | **Reader/Writer 参数化** — 用 `DatasetReader(data_root, dataset)` 替代 104 个类 | 消除 ~80 个文件 | 高 |
| 2 | **DI Provider 自动注册** — `register_store_pair()` 替代 100+ 手动 @provide | 消除 ~70 行样板 | 低 |
| 3 | **_KNOWN_DATASETS 统一** — Dataset 枚举为唯一权威源 | 消除 5 处独立维护 + 修复 bug | 中 |

### 优先级 2：消除重复代码

| # | 建议 | 预估收益 | 难度 |
|---|------|----------|------|
| 4 | **DataSource 拆分** — 4 个窄接口替代 26 方法上帝接口 | 消除 ~20 个 NotImplementedError | 中 |
| 5 | **Tushare 模板方法** — `_fetch_with_pit()` + `_validate_dual_mode()` | 消除 ~300 行重复 | 低 |
| 6 | **MarketService 模板提取** — 合并 adjustment 方法 + logger 模板 | 缩减 ~150 行 | 低 |
| 7 | **Dataset 属性映射化** — if-in 链改为字典映射 | 消除 ~100 行 + 提高可维护性 | 低 |

### 优先级 3：清理遗留

| # | 建议 | 预估收益 | 难度 |
|---|------|----------|------|
| 8 | **合并异常同名定义** — P0 问题修复 | 消除静默捕获风险 | 低 |
| 9 | **删除死代码** — IngestionConfig、空目录、未使用 re-export | 减少认知负担 | 低 |
| 10 | **消除重复定义** — CostModelSpec、AdjType、异常 | 单一事实来源 | 低 |

### 优先级 4：架构精简

| # | 建议 | 预估收益 | 难度 |
|---|------|----------|------|
| 11 | **表达式编译器简化** — 合并 analyzer/compiler | 缩减 ~500 行 | 高 |
| 12 | **Process 内 Protocol 删除** — 同包内用具体类型 | 缩减 ~200 行 | 中 |
| 13 | **MetadataService 重构** — 3 参数替代 17 参数 | 提高可维护性 | 中 |

---

## 五、设计哲学反思

### 过度设计的根源

项目的过度设计集中在三个区域：

1. **"教科书式"的 CQRS**：104 个 Reader/Writer 类是 CQRS 的机械执行，忽略了 CQRS 的价值在于读写模型的差异化（不同的数据结构、一致性级别、性能优化），而非文件拆分。

2. **"面向未来"的 Protocol**：多个 Protocol 只有 1 个实现者，违反了 YAGNI。Protocol 的价值在于存在多个实现时提供运行时多态，而非"万一以后有人要扩展"。

3. **"分层纯粹性"**：Process 子模块内用 Protocol 解耦，是过度追求架构纯粹性的表现。同一包内的模块间依赖是正常的，不需要 Hexagonal 的 Port 层。

### 缺乏简化的根源

1. **DI 容器的样板税**：100+ 个 `@provide` 方法是 Dishka 容器要求的手动注册，已有工厂函数但未被充分使用。

2. **Facade 的手动委托税**：MetadataService 和 TushareSource 的纯委托方法占 70%+ 的代码量，但 Python 没有原生的高效委托机制（`__getattr__` 有其局限）。

3. **数据集列表的分散税**：5 处独立维护数据集列表，根源是缺少一个集中的"数据集注册表"概念。

### 核心建议

> **好的架构不是"每条规则都执行到 100%"，而是"在正确的位置做正确的抽象"**。
>
> 项目当前的 70-80% 规范遵循度说明规范设计方向是正确的，但执行力度不均匀。建议从"消除最大维护成本"入手（Reader/Writer 参数化、DI 自动注册、数据集列表统一），而非追求 100% 的规范覆盖率。
