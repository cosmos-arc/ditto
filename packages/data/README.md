# ditto-data

**版本**: v0.19.0 | **日期**: 2026-04-27 | **状态**: 稳定

## 概要

Ditto 量化系统的数据访问层，统一管理数据获取、存储、查询和 PIT（Point-in-Time）安全。

## 架构

Data 采用分层架构，storage 层实现 CQRS 模式（Reader/Writer 分离）：

```
┌─────────────────────────────────────────────────────────┐
│                  Apps 边界层 (packages/apps)              │
│                  通过 DI 容器注入 Domain Services         │
└─────────────────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┬───────────────┐
        ▼           ▼           ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Runtime层    │ │  Storage层   │ │  Service层   │ │  Sources层   │
│              │ │  (CQRS)      │ │              │ │              │
│ FreezeMgr    │ │ Reader/      │ │ MarketSvc    │ │ Tushare      │
│ SqlEngine    │ │ Writer       │ │ MetadataSvc  │ │ FRED         │
│ IdAllocator  │ │ Parquet/     │ │ CapitalSvc   │ │ TDX          │
│              │ │ SQLite       │ │ MacroSvc     │ │              │
└──────────────┘ │              │ │ Fundamental  │ └──────────────┘
                  └──────────────┘ │ Services...  │
                                    └──────────────┘
```

## 模块结构

```
ditto_data/
├── config/              # 数据层配置（数据源/存储/存储路径）
│   ├── data_source.py
│   ├── data_source_validation.py
│   ├── data_store.py             # all_directories() 目录唯一真源
│   ├── dataset_checksum.py
│   └── storage.py
├── di/                  # DI 注册（data 域 Provider；trade/strategy/execution/features/analysis DI 已迁移至各能力包）
├── errors.py            # DataError 异常层级
├── events.py            # 数据事件定义
├── helpers/             # 辅助工具（复权调整 / PIT 策略）
│   ├── adjustment.py    # 复权调整辅助
│   └── pit/             # PIT（Point-in-Time）辅助
├── ingestion/           # 摄入服务（游标/日志/冻结/晚到数据/质量记录）
│   ├── freeze_service.py
│   ├── ingestion_cursor_service.py
│   ├── ingestion_log_service.py
│   ├── late_arrival.py
│   └── quality_record_service.py
├── models/              # 数据模型（市场/元数据/宏观/摄入/存储等；策略/交易/衍生/发布安全模型已迁移至各能力包或 kernel）
│   ├── common.py / market.py / metadata.py / macro.py
│   ├── ingestion.py / storage.py / source_codes.py
├── provider.py          # DataProvider Protocol 定义
├── providers/           # DataProvider 实现
│   └── provider.py      # ServiceBackedDataProvider 实现
├── quality/             # 数据质量引擎（L1-L4 检查器）
│   ├── checkers/        # 技术/业务/统计/跨源检查器
│   ├── config.py / engine.py / golden.py / protocols.py
│   ├── report.py / severity.py / spec.py
├── runtime/             # 运行时基础设施
│   ├── freeze_manager.py
│   ├── instrument_id_allocator.py
│   └── sql_engine.py
├── scripts/             # 工具脚本
├── services/            # 域服务（market/metadata/fundamental/macro/capital/source + metadata 子目录）
│   ├── deps.py          # 服务依赖聚合（DI 参数分组）
│   ├── _enrichment.py   # 数据富化辅助
│   ├── market_service.py / market_write_service.py
│   ├── metadata_service.py / fundamental_service.py
│   ├── macro_service.py / capital_service.py
│   ├── source_service.py
│   └── metadata/        # 日历/工具/Universe
│       ├── calendar.py
│       ├── instrument.py
│       └── universe.py
├── sources/             # 外部数据源
│   ├── base.py / source.py / source_schema.py
│   ├── exchange_transformers.py / normalization.py
│   ├── fred/            # FRED 数据源（宏观/商品适配器）
│   ├── schemas/         # 数据源 Schema（capital/commodity/fx/macro/market/metadata）
│   ├── tdx/             # 通达信数据源
│   └── tushare/         # Tushare 数据源（适配器/处理器/映射）
├── storage/             # 存储引擎（Reader/Writer CQRS）
│   ├── base/            # 存储基类（Parquet/SQLite/分区策略）
│   ├── capital/         # 估值/融资融券/质押/指数成分
│   ├── fundamental/     # 财报/预测/公司行为
│   ├── macro/           # 宏观指标
│   ├── market/          # ETF/股票/指数/商品/外汇
│   ├── metadata/        # 日历/工具/行业/Universe
│   ├── runtime/         # 摄入游标/日志/质量
│   └── schemas/         # 存储层 Schema（market/metadata/store）
└── utils/               # 工具函数（时区等）
```

## 分层职责

| 层级 | 职责 | 禁止 |
|------|------|------|
| storage (Reader/Writer) | 数据读写操作（CQRS 分离） | 包含业务逻辑 |
| services | 域服务（market/metadata/fundamental/macro/capital/source + metadata 子目录） | 直接访问文件系统 |
| sources | 外部数据源接入 | 包含业务逻辑 |
| providers | ServiceBackedDataProvider 实现 | 包含业务逻辑 |
| ingestion | 数据摄入编排 | 绕过质量检查 |
| quality | 数据质量引擎（L1-L4） | 包含业务逻辑 |
| runtime | 运行时基础设施（SQL/Freeze/ID） | 包含业务逻辑 |
| models | 数据模型定义 | 包含行为方法 |
| di | DI 注册 | 包含业务逻辑 |

## CQRS 模式

`storage/` 层采用 CQRS 模式，将读写操作分离：

- `*_reader.py`：查询操作（read/count/get_*），无副作用，可并发执行
- `*_writer.py`：写入/删除操作（write/delete），有副作用，需并发控制

## 数据源

| 数据源 | 说明 | 路径 |
|--------|------|------|
| Tushare | A 股行情/基本面/资金 | `sources/tushare/` |
| FRED | 宏观/商品数据 | `sources/fred/` |
| TDX | 通达信本地数据 | `sources/tdx/` |

## 数据域

Data 采用域驱动设计（DDD），按业务域组织：

| 域 | 子域 | 存储 | PIT |
|---|------|------|-----|
| Metadata | instrument / identity / calendar / industry / universe | SQLite | 部分 |
| Market | stock / etf / index / commodity / fx | Parquet + SQLite | 部分 |
| Capital | valuation / margin / pledge / index_composition | SQLite | 是 |
| Fundamental | financial / forecast / corporate | SQLite | 部分 |
| Macro | indicator | SQLite | 是 |

## 数据质量

| 类别 | 检测内容 | 执行时机 | 失败处理 |
|------|----------|----------|----------|
| 技术类 | 非空、唯一、外键 | 写入时 | 阻断写入 |
| 业务类 | OHLC、涨跌幅 | 写入时 | 警告记录 |
| 统计类 | Z-score、完整性 | 定时批量 | 告警通知 |

## 数据摄入

| 层级 | 职责 | 调度时机 |
|------|------|----------|
| T0 | 元数据（calendar, basic） | 每日 8:00-9:00 |
| T1 | 增量数据（daily bars） | 交易日 18:00 |
| T2 | 空洞扫描 + 回填 | 每日凌晨 2:00 |
| T3 | 质量检查 | T1 完成后 |

## 层级访问规则

| 访问类型 | 允许 | 禁止 |
|---------|------|------|
| 通过 Domain Service | `MetadataService`, `MarketService` 等 | - |
| 通过 Query Provider | `QueryProvider` | - |
| 直接导入 | `from ditto_data.sources.*` | `from ditto_data.storage.*` |
| Reader/Writer | - | 直接实例化 |

## 使用示例

```python
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.market_service import MarketService

# Domain Services 由 DI 容器注入
metadata_service: MetadataService = container.get(MetadataService)
market_service: MarketService = container.get(MarketService)

# 查询交易日历
trading_days = metadata_service.get_trading_days("2024-01-01", "2024-01-31")

# 查询行情数据
bars = market_service.query(query)
```

## 测试

```bash
pixi run -e dev pytest packages/data/tests/
```

## 相关文档

- [Data 层规范](CLAUDE.md)
- [PIT 安全指南](../../.claude/rules/pit.md)
- [数据设计文档](../../docs/design/02_data_design.md)

## 变更记录

### v0.19.0 (2026-04-27)
- 文档同步更新：大幅精简 README，移除过时引用
- 添加 FRED / TDX 数据源、ingestion/ 详细结构、storage 子域隔离
- 移除已迁移服务的引用（trade/audit/derived/hot_layer/strategy/derived_catalog/research_catalog/research_artifact）
- 同步 storage/base/ 结构（ParquetStore/PartitionStrategy 已迁移至 platform）

### v0.18.0 (2026-03-24)
- Strategy 运行与审计支持（StrategyRunService / ExecutionAuditService）
- StrategyRunRecord / AuditRecordType 模型

### v0.15.0 (2026-02-10)
- 移除 Data Facade：Interfaces 层直接注入 Domain Services
- CQRS 架构：Store 层拆分为 Reader/Writer 模式
