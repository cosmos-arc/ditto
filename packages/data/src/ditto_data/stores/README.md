# stores

**版本**: v0.5.0
**最后更新**: 2026-02-06
**状态**: ✅ 稳定

## 概要

数据存储层 - SQLite 与 Parquet 双存储实现，提供统一的数据访问接口。

## 核心功能

提供 SQLite (事务型) 和 Parquet (年分区分析型) 两种存储的统一访问接口。

## 包含文件

| 文件 | 功能 |
|------|------|
| `sqlite_client.py` | SQLite 客户端封装，提供统一的 CRUD 接口 |
| `base/` | 存储抽象基类 |
| `parquet_store_base.py` | Parquet 年分区存储基类 |

## 架构定位

`stores/` 层作为基础设施，提供底层存储能力：

```
┌─────────────────┐
│   Application   │
├─────────────────┤
│   Domains       │  ← 业务域层 (Service + Store)
├─────────────────┤
│  Foundation     │  ← 基础设施 (SQLite, Parquet)
└─────────────────┘
```

### 层级职责

| 层级 | 职责 | 示例 |
|------|------|------|
| Domains | 业务逻辑、领域模型 | MarketService, MetadataService |
| Stores | 基础设施、通用存储 | SQLiteClient, ParquetStoreBase |

## 迁移说明

以下组件已从 `stores/` 迁移到 `domains/` 层：

| 组件 | 迁移目标 | 原因 |
|------|----------|------|
| `UniverseStore` | `domains/metadata/universe/` | 业务域组件 |
| `BarsStore` | `domains/market/bars/` | 业务域组件 |
| `AdjFactorStore` | `domains/market/adj_factor/` | 业务域组件 |

## 使用示例

```python
from pathlib import Path
from ditto_data.stores import SQLiteClient

# SQLite 客户端（基础设施）
client = SQLiteClient(Path("data/ditto.db"))

# Domains 层使用示例
from ditto_data.stores.market import MarketBarsQuery, MarketService
from ditto_data.stores.metadata import MetadataQuery, MetadataService

metadata_service: MetadataService = ...
market_service: MarketService = ...

# 业务操作通过 Domain Service
securities = metadata_service.query(
    MetadataQuery(dataset="instrument", asset_class="stock")
)
bars = market_service.query(
    MarketBarsQuery(instrument_ids=[1000001], start="2024-01-01")
)
```

## 相关文档

- [Helpers 纯函数工具](../helpers/README.md)
- [Metadata 域文档](../domains/metadata/README.md)
- [Market 域文档](../domains/market/README.md)
