# Data 架构规范

## 目录结构

```
ditto_data/
├── config/              # 数据层配置（数据源/存储/存储路径）
│   ├── data_source.py            # 数据源配置
│   ├── data_source_validation.py # 数据源特定校验（DataSourceValidationProvider，如 TUSHARE_TOKEN）
│   ├── data_store.py             # 数据存储配置（含 all_directories() 目录唯一真源）
│   ├── dataset_checksum.py       # 数据集校验和排序键映射（dataset_sort_keys()）
│   └── storage.py                # 存储路径配置
├── di/                  # DI 注册（data 域 Provider；trade/strategy/execution/features/analysis DI 已迁移至各能力包）
│   ├── builders.py      # DI Builder
│   ├── _factory.py      # DI 工厂
│   ├── sources.py       # 数据源 Provider
│   ├── market.py        # 行情 Provider
│   ├── metadata.py      # 元数据 Provider
│   ├── fundamental.py   # 基本面 Provider
│   ├── macro.py         # 宏观 Provider
│   ├── capital.py       # 资金 Provider
│   ├── quality.py       # 质量 Provider
│   ├── golden.py        # 黄金标准 Provider
│   └── runtime.py       # 运行时 Provider
├── errors.py            # DataError 异常层级
├── events.py            # 数据事件定义
├── catalog/             # DataCatalog 运行时（Protocol contracts / metadata / store）
│   ├── contracts.py     # DataCatalog Protocol
│   ├── metadata.py      # 目录元数据
│   └── store.py         # 目录存储
├── lineage/             # 数据血缘（contracts 占位）
│   └── contracts.py     # 血缘 Protocol contracts
├── helpers/             # 辅助工具（复权调整/PIT 策略与 DataFrame）
│   ├── adjustment.py    # 复权调整辅助
│   └── pit/             # PIT（Point-in-Time）辅助
├── ingestion/           # 摄入存储（游标/日志/冻结/晚到数据/质量记录）
│   ├── freeze_store.py                     # 冻结存储
│   ├── ingestion_cursor_store.py           # 摄入游标存储
│   ├── ingestion_log_store.py              # 摄入日志存储
│   ├── late_arrival.py                     # 晚到数据处理
│   └── quality_record_store.py             # 质量记录存储
├── models/              # 数据模型（市场/元数据/宏观/摄入/存储等；策略/交易/衍生/发布安全模型已迁移至各能力包或 kernel）
│   ├── common.py               # 公共模型
│   ├── market.py               # 行情模型
│   ├── metadata.py             # 元数据模型
│   ├── macro.py                # 宏观模型
│   ├── ingestion.py            # 摄入结果模型
│   ├── storage.py              # 存储相关模型
│   └── source_codes.py         # 数据源代码
├── provider.py          # DataProvider Protocol 定义
├── quality/             # 数据质量引擎
│   ├── checkers/        # L1-L4 检查器（技术/业务/统计/跨源）
│   ├── quality_types.py # DQ 类型（DQLevel / DQSeverity / DQIssue / DQResult）
│   ├── config.py        # DQ 配置加载
│   ├── engine.py        # 质量引擎主类
│   ├── golden.py        # 黄金标准参考
│   ├── protocols.py     # 质量检查 Protocol
│   ├── report.py        # 质量报告生成
│   └── spec.py          # 质量规格定义
├── runtime/             # 运行时基础设施
│   ├── freeze_manager.py         # 冻结管理器
│   ├── instrument_id_allocator.py # 工具 ID 分配器
│   └── sql_engine.py             # SQL 引擎
├── observability/       # 可观测性
│   └── metrics.py       # 数据层指标
├── scripts/             # 工具脚本
├── services/            # 域服务/存储（market/metadata/fundamental/macro/capital/source + metadata 子目录）
│   ├── deps.py          # 服务依赖聚合（DI 参数分组）
│   ├── _enrichment.py   # 数据富化辅助
│   ├── market_service.py         # 行情服务
│   ├── market_write_service.py   # 行情写入服务
│   ├── metadata_service.py       # 元数据服务
│   ├── fundamental_store.py      # 基本面存储（Reader/Writer 组合）
│   ├── macro_service.py          # 宏观服务
│   ├── capital_store.py          # 资金存储（Reader/Writer 组合）
│   ├── source_accessor.py        # 数据源访问器
│   └── metadata/        # 元数据子服务（日历/工具/Universe）
│       ├── calendar.py   # 日历服务
│       ├── instrument.py # 工具服务
│       └── universe.py   # Universe 服务
├── sources/             # 外部数据源
│   ├── base.py          # 数据源基类
│   ├── source.py        # 数据源注册
│   ├── source_schema.py # 数据源 Schema 基类
│   ├── exchange_transformers.py  # 交易所转换器
│   ├── normalization.py # 数据标准化
│   ├── fred/            # FRED 数据源（宏观/商品适配器）
│   │   ├── adapters/    # 适配器（base/commodity/macro）
│   │   ├── client.py    # FRED API 客户端
│   │   ├── indicators.py# 指标定义
│   │   └── fred_source.py
│   ├── schemas/         # 数据源 Schema 定义（capital/commodity/fx/macro/market/metadata）
│   ├── tdx/             # 通达信数据源
│   │   ├── reader.py    # 本地文件读取
│   │   ├── source.py    # TDX 数据源
│   │   └── transformer.py
│   └── tushare/         # Tushare 数据源（适配器/处理器/映射）
│       ├── adapters/    # 数据适配器（ETF/股票/宏观/资金/债券/外汇/金属/指数/行业等）
│       ├── processors/  # 数据处理器（列映射/合并/转换）
│       │   └── mappings/  # 字段映射定义（basic/capital/common/macro）
│       └── utils/       # 工具（HTTP/限流）
├── storage/             # 存储引擎（Reader/Writer CQRS；factors/features/execution 存储已迁移至各能力包）
│   ├── base/            # 存储基类（SQLite 数据集读写）
│   │   ├── dataset_reader.py     # Parquet 数据集读取基类
│   │   ├── dataset_writer.py     # Parquet 数据集写入基类
│   │   ├── sqlite_store.py       # SQLite 存储基类
│   │   ├── sqlite_table_reader.py  # SQLite 表读取基类
│   │   ├── sqlite_table_spec.py    # SQLite 表规格定义
│   │   └── sqlite_table_writer.py  # SQLite 表写入基类
│   ├── capital/         # 资本数据（估值/融资融券/质押/指数成分）
│   │   ├── valuation/   # 估值指标
│   │   ├── margin/      # 融资融券
│   │   ├── pledge/      # 质押
│   │   └── index_composition/  # 指数成分
│   ├── fundamental/     # 基本面存储（财报/预测/公司行为）
│   │   ├── financial/   # 财报（利润表/资产负债表/现金流量表）
│   │   ├── forecast/    # 预测（业绩快报/一致性预测）
│   │   └── corporate/   # 公司行为（分红/公司行动）
│   ├── macro/           # 宏观数据存储
│   │   └── indicator/   # 宏观指标（reader/writer/metadata）
│   ├── market/          # 市场数据存储（ETF/股票/指数/商品/外汇）
│   │   ├── etf/         # ETF（bars/nav/adj/status）
│   │   ├── stock/       # 股票（bars/adj/status）
│   │   ├── index/       # 指数（bars/constituent）
│   │   ├── commodity/   # 商品（bars）
│   │   └── fx/          # 外汇（bars）
│   ├── metadata/        # 元数据存储（日历/工具/行业/Universe/PIT/费率/交易规则）
│   │   ├── calendar/    # 日历（reader/writer）
│   │   ├── instrument/  # 工具（reader/writer/name_history）
│   │   ├── industry/    # 行业（reader/writer/mapping）
│   │   ├── universe/    # Universe（reader/writer/rebalance）
│   │   ├── _pit_base.py # PIT 存储基类
│   │   ├── fee_schedule_reader/writer.py  # 费率表
│   │   └── trading_rule_reader/writer.py  # 交易规则
│   ├── runtime/         # 运行时存储（摄入游标/日志/质量）
│   │   ├── ingestion/   # 摄入游标/日志
│   │   ├── quality/     # 质量（比较/隔离）
│   │   └── unit_of_work.py      # 工作单元
│   └── schemas/         # 存储层 Schema（market/metadata/store）
└── utils/               # 工具函数（时区等）
```

## 分层职责

| 层级 | 职责 | 禁止 | 必须 |
|------|------|------|------|
| storage (Reader/Writer) | 数据读写操作（CQRS 分离） | 包含业务逻辑 | 类型注解 |
| services | 域服务/存储（market/metadata/fundamental/macro/capital/source + metadata 子目录） | 直接访问文件系统 | 通过 storage |
| sources | 外部数据源接入 | 包含业务逻辑 | 重试、限流、监控埋点 |
| ingestion | 数据摄入存储（游标/日志/冻结/质量记录） | 绕过质量检查 | 游标管理 |
| quality | 数据质量引擎（含 protocols.py） | 包含业务逻辑 | L1-L4 检查 |
| runtime | 运行时基础设施（SQL 引擎/冻结管理/ID 分配） | 包含业务逻辑 | SQL/PIT/Freeze |
| models | 数据模型定义（市场/元数据/宏观/摄入/存储等；策略/交易/衍生/发布安全模型已迁移至各能力包或 kernel） | 包含行为方法 | 纯数据类 |
| di | DI 注册 | 包含业务逻辑 | Provider 注册 |

## CQRS 模式（Command Query Responsibility Segregation）

`storage/` 层采用 CQRS 模式，将读写操作分离：

### Reader 组件（`storage/**/reader.py`）
- **职责**：数据查询（read/count/get_*）
- **特点**：无副作用，可并发执行
- **方法**：`read()`, `count()`, `get_*()`

### Writer 组件（`storage/**/writer.py`）
- **职责**：数据写入/删除（write/delete）
- **特点**：有副作用，需要并发控制
- **方法**：`write()`, `delete()`

### 命名约定
- 查询类：`*_reader.py`（如 `instrument_reader.py`）
- 写入类：`*_writer.py`（如 `instrument_writer.py`）
- 存储类（Reader/Writer 组合）：`*_store.py`（如 `capital_store.py`、`fundamental_store.py`）
- 访问器（外部资源查找/访问）：`*_accessor.py`（如 `source_accessor.py`）
- 服务类（有非平凡业务编排）：`*_service.py`（如 `metadata_service.py`、`market_service.py`）
- 存储基础设施：`storage/base/` 保留 data-specific SQLiteStore / DatasetWriter / TableReader / TableWriter；ParquetStore / PartitionStrategy / SQLiteClient 等共享基类位于 `platform.foundation.storage`

命名决策依据（详见架构攻坚计划 §3.3）：
| 名称 | 使用条件 | 禁止 |
|------|----------|------|
| `*Store` | Reader/Writer 组合、集合式数据访问 | 混入校验、富化、跨表工作流 |
| `*Service` | 有非平凡业务/应用内编排 | 只有 1-line pass-through |
| `*Accessor` | 外部资源查找/访问 | 承担业务编排 |

## 层级访问规则（2026-02-10 更新）

### Interfaces 层访问规则

| 访问类型 | ✅ 允许 | ❌ 禁止 | 说明 |
|---------|--------|--------|------|
| **通过 Domain Service** | `MetadataService`, `MarketService` 等 | - | **推荐方式**，通过 DI 容器注入 |
| **通过 Query Provider** | `QueryProvider` | - | 统一查询路由 |
| **直接导入** | `from ditto_data.sources.*` | `from ditto_data.storage.*` | Sources 可直接访问，Storage 禁止 |
| **Reader/Writer** | - | 直接实例化 | **禁止**直接访问 storage 层 |

### 正确示例

```python
# ✅ 推荐：通过 DI 容器注入 Domain Service
from dishka import Container
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.market_service import MarketService

container = Container()
metadata_service: MetadataService = container.get(MetadataService)
market_service: MarketService = container.get(MarketService)

# 使用 Service
trading_days = metadata_service.get_trading_days("2024-01-01", "2024-01-31")
bars = market_service.query(query)

# ✅ 推荐：通过 Service 获取数据
provider = sources.get("tushare")
df = provider.fetch_stock_daily("2024-01-02")

# ❌ 禁止：直接访问 Reader/Writer（即使技术上可行）
from ditto_data.storage.metadata import InstrumentReader  # ❌
reader = InstrumentReader(...)  # ❌
```

**原则**：
- Sources 层（数据获取）可由 Interfaces 层直接访问
- Reader/Writer 层（数据存储）必须通过 Service 间接访问

## 数据质量（DQ）规范

| 类别 | 检测内容 | 执行时机 | 失败处理 |
|------|----------|----------|----------|
| 技术类 | 非空、唯一、外键 | 写入时 | 阻断写入 |
| 业务类 | OHLC、涨跌幅 | 写入时 | 警告记录 |
| 统计类 | Z-score、完整性 | 定时批量 | 告警通知 |

| 配置文件位置 | 修改后必更新 |
|-------------|-------------|
| `config/default/dq_rules/*.yaml` | `docs/design/09_data_quality_design.md` |

## 数据摄入 T0/T1/T2/T3

| 层级 | 职责 | 调度时机 |
|------|------|----------|
| T0 | 元数据（calendar, basic） | 每日 8:00-9:00 |
| T1 | 增量数据（daily bars） | 交易日 18:00 |
| T2 | 空洞扫描 + 回填 | 每日凌晨 2:00 |
| T3 | 质量检查 | T1 完成后 |

## 游标管理

| 操作 | 说明 |
|------|------|
| 检查 last_attempted | 失败重试前 |
| 更新 last_success | 成功写入后 |

## 安全机制

| 禁止 | 替代 |
|------|------|
| Reader/Writer 直接写 Parquet | 通过对应的 Service |
| 绕过 DQ 检查写入 | Service.write() 自动触发 |
| 硬编码数据路径 | 使用 get_paths() |
| Parquet 写入不加锁 | FileLock (超时 30s) |
| 冻结数据无保护 | FreezeManager.acquirefreeze() |
| Interfaces 层直接访问 Reader/Writer | 通过 Service 间接访问 |

## 数据集成熟度

| 数据集族 | 成熟度 | 说明 |
|----------|--------|------|
| A-share ETF/指数 行情 | initial-focus | 当前生产范围核心 |
| A-share ETF 元数据 | initial-focus | Universe/Instrument 基础设施 |
| A-share 股票 行情/元数据 | experimental | 存储和适配器存在，但不属于 initial-focus |
| 基本面（PIT） | experimental | PIT schema 和 API 存在，生产就绪待验证 |
| 资金数据 | experimental | 估值/融资融券/质押/指数成分 |
| 宏观指标 | experimental | FRED/Tushare 适配器存在，非当前生产范围 |
| FX 外汇 | experimental | Tushare FX 适配器存在，非当前生产范围 |
| 商品（WTI/Brent/Gold/Silver） | experimental | FRED/Tushare 适配器存在，非当前生产范围 |
| DataCatalog runtime | experimental | Protocol contracts 存在，无具体实现 |
| Lineage | reserved | contracts 仅占位 |

成熟度定义见 `docs/architecture/capability-maturity.md`。API/CLI/文档不得将 experimental 数据集描述为生产就绪。
