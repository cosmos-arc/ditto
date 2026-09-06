# ditto-data

> 包级约束见 [AGENTS.md](AGENTS.md)；全局边界见 [架构快速参考](../../docs/architecture/agent-context-pack.md)。

**版本**: v0.19.0 | **日期**: 2026-04-27 | **状态**: 稳定

## 概要

Ditto 量化系统的数据访问层，统一管理数据获取、存储、查询和 PIT（Point-in-Time）安全。

## 架构

Data 采用分层架构，storage 层实现 CQRS 模式（Reader/Writer 分离）：

```
┌─────────────────────────────────────────────────────────┐
│                  Apps 边界层 (apps/backend)              │
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

目录结构详见 [AGENTS.md](AGENTS.md)

分层职责详见 [AGENTS.md](AGENTS.md)

CQRS 模式详见 [AGENTS.md](AGENTS.md)

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

数据质量等级详见 [AGENTS.md](AGENTS.md)

数据摄入流程详见 [AGENTS.md](AGENTS.md)

层级访问规则详见 [AGENTS.md](AGENTS.md)

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
uv run --no-sync pytest packages/data/tests/
```

## 相关文档

- [Data 层规范](AGENTS.md)
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
