# Ditto 量化系统架构设计 v4.1

> **核心理念**：简洁的层次、清晰的职责、符合量化业务逻辑
>
> **基于业界最佳实践**：WorldQuant、Two Sigma、Citadel、九坤等领先量化机构的架构模式
>
> **设计日期**: 2026-02-07
>
> **v4.1 更新**：
> - 复权计算移到 Domain Layer（业务逻辑）
> - enrich 能力在 Application Layer（业务编排）
> - CQRS 模式（读写分离）
> - Repository 接口读写分离
> - 分层 API（基础/便捷/编排）

---

## 一、核心架构决策

### 1.1 复权计算定位（Domain Layer）

**业界实践**：
- **WorldQuant**: 复权是 Alpha 研究的核心能力，属于 Domain Logic
- **Two Sigma**: 复权逻辑在 Data Platform 的计算引擎（Domain Layer）
- **Citadel**: 复权作为独立的计算服务（Domain Service）

**结论**：复权计算是**金融业务逻辑**，属于 Domain Layer。

```python
# packages/core/src/ditto_core/market/adjustment.py

from datetime import date
from enum import Enum

import polars as pl


class AdjType(Enum):
    """复权类型"""
    NONE = "none"
    QFQ = "qfq"      # 前复权
    HFQ = "hfq"      # 后复权


class AdjustmentEngine:
    """复权计算引擎（Domain Layer）

    职责：
    - 前复权（QFQ）计算
    - 后复权（HFQ）计算
    - 复权因子管理

    特点：
    - 纯函数式计算（无副作用）
    - 金融业务逻辑，不是技术实现
    """

    @staticmethod
    def apply_qfq(
        df: pl.DataFrame,
        adj_factors: pl.DataFrame,
        asof: date | None = None,
    ) -> pl.DataFrame:
        """
        前复权计算（QFQ）

        公式：adj_price = orig_price × cur_factor / latest_factor

        Args:
            df: K线数据（含 adj_factor 列）
            adj_factors: 复权因子数据
            asof: PIT 查询日期

        Returns:
            前复权后的数据
        """
        # PIT 过滤
        if asof:
            adj_factors = adj_factors.filter(
                pl.col("knowledge_date") <= asof
            )

        # 获取最新因子
        latest_factors = adj_factors.group_by("sid").agg(
            pl.col("adj_factor").last().alias("latest_factor")
        )

        # 应用 QFQ 公式
        result = df.join(latest_factors, on="sid", how="left").with_columns([
            (
                pl.col("open")
                * pl.coalesce("adj_factor", 1.0)
                / pl.coalesce("latest_factor", 1.0)
            ).alias("open"),
            (
                pl.col("high")
                * pl.coalesce("adj_factor", 1.0)
                / pl.coalesce("latest_factor", 1.0)
            ).alias("high"),
            (
                pl.col("low")
                * pl.coalesce("adj_factor", 1.0)
                / pl.coalesce("latest_factor", 1.0)
            ).alias("low"),
            (
                pl.col("close")
                * pl.coalesce("adj_factor", 1.0)
                / pl.coalesce("latest_factor", 1.0)
            ).alias("close"),
        ])

        return result.drop(["adj_factor", "latest_factor"])

    @staticmethod
    def apply_hfq(
        df: pl.DataFrame,
        adj_factors: pl.DataFrame,
    ) -> pl.DataFrame:
        """
        后复权计算（HFQ）

        公式：adj_price = orig_price × cur_factor

        Args:
            df: K线数据（含 adj_factor 列）
            adj_factors: 复权因子数据

        Returns:
            后复权后的数据
        """
        # 获取当前因子
        current_factors = adj_factors.join(
            df[["sid", "trade_date"]],
            on=["sid", "trade_date"],
            how="left"
        )

        # 应用 HFQ 公式
        result = df.with_columns([
            (
                pl.col("open")
                * pl.coalesce("adj_factor", 1.0)
            ).alias("open"),
            (
                pl.col("high")
                * pl.coalesce("adj_factor", 1.0)
            ).alias("high"),
            (
                pl.col("low")
                * pl.coalesce("adj_factor", 1.0)
            ).alias("low"),
            (
                pl.col("close")
                * pl.coalesce("adj_factor", 1.0)
            ).alias("close"),
        ])

        return result.drop(["adj_factor"])

    @staticmethod
    def calculate_adjustment_factor(
        df: pl.DataFrame,
        method: Literal["前复权", "后复权"] = "前复权",
    ) -> pl.DataFrame:
        """
        计算复权因子

        Args:
            df: K线原始数据（OHLC + 资金流事件）
            method: 复权方法

        Returns:
            复权因子数据
        """
        # 复权因子计算逻辑
        # 这是金融业务逻辑！
        ...
```

### 1.2 CQRS 模式（读写分离）

**业界实践**：
- **CQRS 模式**：Command-Query Responsibility Segregation
- **Greg Young**: 复杂业务场景的读写分离
- **Udi DDD**: CQRS 作为可选模式

**应用场景**：
- ✅ 查询和写入的模型不同
- ✅ 查询性能优化（缓存、视图）
- ✅ 写入需要严格验证
- ✅ 需要审计追踪

```python
# packages/contracts/src/ditto_contracts/bars/repository.py

from abc import ABC, abstractmethod


class IBarsReader(ABC):
    """K线数据读取接口（查询端）"""

    @abstractmethod
    def get_bars(self, query: "BarsQuery") -> pl.DataFrame:
        """读取 K线数据（只读）"""
        pass

    @abstractmethod
    def get_latest_date(self, sid: int) -> str | None:
        """获取最新数据日期"""
        pass

    @abstractmethod
    def get_date_range(self) -> tuple[str | None, str | None]:
        """获取数据日期范围"""
        pass


class IBarsWriter(ABC):
    """K线数据写入接口（写入端）"""

    @abstractmethod
    def write_bars(
        self,
        data: list["BarsData"],
        dataset: str,
    ) -> "BarsWriteResult":
        """写入 K线数据"""
        pass

    @abstractmethod
    def delete_bars(
        self,
        sids: list[int],
        start_date: str,
        end_date: str,
    ) -> int:
        """删除 K线数据"""
        pass

    @abstractmethod
    def begin_transaction(self) -> "ITransaction":
        """开始事务（写入端特有）"""
        pass
```

### 1.3 Repository 实现读写分离

```python
# packages/data/src/ditto_data/repositories/bars.py

class StockBarsReader(IBarsReader):
    """股票 K线读取器（只读）"""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.path = data_root / "standard" / "stock" / "bars_daily"

    def get_bars(self, query: "BarsQuery") -> pl.DataFrame:
        """读取 K线数据（只读操作）"""
        paths = self._collect_paths(query.start_date, query.end_date)
        return pl.scan_parquet(paths).filter(
            pl.col("sid").is_in(query.sids),
            pl.col("trade_date").between(query.start_date, query.end_date),
        ).collect()

    def get_latest_date(self, sid: int) -> str | None:
        """获取最新数据日期"""
        result = pl.scan_parquet(self.path).filter(
            pl.col("sid") == sid
        ).select(pl.col("trade_date").max()).collect()
        return result[0, "trade_date"] if not result.is_empty() else None


class StockBarsWriter(IBarsWriter):
    """股票 K线写入器（只写）"""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.path = data_root / "standard" / "stock" / "bars_daily"

    def write_bars(
        self,
        data: list["BarsData"],
        dataset: str,
    ) -> "BarsWriteResult":
        """写入 K线数据（原子操作）"""
        # 转换为 DataFrame
        df = self._convert_to_dataframe(data)

        # 原子写入
        year = data[0].trade_date.year
        target_path = self.path / f"{year}.parquet"
        self._atomic_append(df, target_path)

        return BarsWriteResult(...)

    def begin_transaction(self) -> "ITransaction":
        """开始事务"""
        return BarsTransaction(self.path)

    def delete_bars(self, sids, start_date, end_date) -> int:
        """删除 K线数据"""
        # 删除逻辑
        ...
```

---

## 二、分层 API 设计

### 2.1 三层 API 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                       Application Layer                        │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │         Orchestrator API (编排层)                      │   │
│  │  - IngestionOrchestrator                                     │   │
│  │  - BacktestOrchestrator                                      │   │
│  │  - TradingOrchestrator                                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                           ↓                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │         Service API (服务层)                             │   │
│  │  - DataQueryService ✅ (只读)                             │   │
│  │  - DataWriteService ✅ (只写)                            │   │
│  │  - AdjustmentService (Domain 编排)                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                           ↓                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │         Repository API (基础层)                          │   │
│  │  - IBarsReader / IBarsWriter (CQRS 读写分离)            │   │
│  │  - IInstrumentReader / IInstrumentWriter                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 API 层级职责

| API 层级 | 职责 | 典型用户 | 示例 |
|---------|------|---------|------|
| **Orchestrator** | 编排复杂用例 | Port Jobs | `IngestionOrchestrator.ingest_date()` |
| **Service** | 提供便捷 API | Application | `DataQueryService.get_bars(symbols=[...])` |
| **Repository** | 基础数据操作 | Domain/Service | `IBarsReader.get_bars(BarsQuery(...))` |

---

## 三、DataQueryService（只读服务）

### 3.1 设计原则

```
用户代码
    │
    ↓ symbols=["000001.SZ"]  # 用户友好的参数
DataQueryService
    │
    ├─→ resolve_sids()          # 通过 InstrumentRepository
    ├─→ IBarsReader.get_bars()  # 通过 Reader 接口
    ├─→ AdjustmentEngine.qfq()  # Domain 复权计算
    └─→ enrich_with_status()    # Port 业务编排
    │
    ↓
增强后的 DataFrame
```

### 3.2 DataQueryService 实现

```python
# apps/port/src/ditto_port/services/data_query_service.py

from datetime import date
from typing import Literal

import polars as pl

from ditto_contracts.bars import BarsQuery, AdjType
from ditto_core.market.adjustment import AdjustmentEngine   # Domain!
from ditto_data.repositories import IBarsReader
from ditto_data.repositories.metadata import IInstrumentReader
from ditto_data.repositories.status import IStatusReader


class DataQueryService:
    """数据查询服务（Application Layer - 只读）

    职责：
    - 提供用户友好的查询 API
    - 编排 symbol → SID 解析
    - 编排复权计算（调用 Domain Engine）
    - 编排数据增强（业务逻辑）

    不包含：
    - 数据写入（由 DataWriteService 负责）
    """

    def __init__(
        self,
        # Readers（只读接口）
        stock_bars_reader: IBarsReader,
        etf_bars_reader: IBarsReader,
        index_bars_reader: IBarsReader,
        # Metadata Readers
        instrument_reader: IInstrumentReader,
        status_reader: IStatusReader,
        # Domain Engine
        adjustment_engine: AdjustmentEngine,
    ):
        self._stock_bars_reader = stock_bars_reader
        self._etf_bars_reader = etf_bars_reader
        self._index_bars_reader = index_bars_reader
        self._instrument_reader = instrument_reader
        self._status_reader = status_reader
        self._adjustment_engine = adjustment_engine

    def get_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        adj: Literal["none", "qfq", "hfq"] = "none",
        as_of: date | None = None,
        asset_class: Literal["stock", "etf", "index"] | None = None,
        enrich_with_status: bool = False,
    ) -> pl.DataFrame:
        """
        获取 K线数据（便捷 API）

        流程：
        1. 解析 symbols → SIDs
        2. 读取原始数据（Reader）
        3. 应用复权（Domain Engine）
        4. 数据增强（Port 逻辑）

        Args:
            symbols: 证券代码列表 ["000001.SZ", "510300.SH"]
            start_date: 开始日期
            end_date: 结束日期
            adj: 复权类型
            as_of: PIT 查询日期
            asset_class: 资产类别
            enrich_with_status: 是否添加状态信息

        Returns:
            K线数据 DataFrame
        """

        # 1. 解析 symbols → SIDs
        sids = self._resolve_sids(symbols, asset_class)

        # 2. 检测资产类别
        if asset_class is None:
            asset_class = self._detect_asset_class(sids)

        # 3. 读取原始数据
        df = self._read_bars(sids, start_date, end_date, asset_class)

        if df.is_empty():
            return df

        # 4. 应用复权（Domain Engine）
        if adj != "none" and asset_class == "stock":
            adj_factors = self._get_adj_factors(sids, start_date, end_date)
            df = self._adjustment_engine.apply_qfq(df, adj_factors, as_of)

        # 5. 数据增强（Port 逻辑）
        df = self._enrich_data(df, sids, enrich_with_status)

        return df

    def _resolve_sids(
        self,
        symbols: list[str],
        asset_class: "AssetClass" | None,
    ) -> list[int]:
        """解析 symbols → SIDs（通过 InstrumentReader）"""
        # 检查是否已经是 SIDs
        if all(s.isdigit() for s in symbols):
            return [int(s) for s in symbols]

        # 解析 symbol → SID
        sids = []
        for symbol in symbols:
            source = self._extract_source(symbol)
            sid = self._instrument_reader.resolve_sid(symbol, source)
            if sid:
                sids.append(sid)
        return sids

    def _read_bars(
        self,
        sids: list[int],
        start_date: date,
        end_date: date,
        asset_class: "AssetClass",
    ) -> pl.DataFrame:
        """读取原始数据（通过 Reader）"""
        if asset_class == "stock":
            return self._stock_bars_reader.get_bars(
                BarsQuery(sids=sids, start_date=start_date, end_date=end_date)
            )
        elif asset_class == "etf":
            return self._etf_bars_reader.get_bars(
                BarsQuery(sids=sids, start_date=start_date, end_date=end_date)
            )
        elif asset_class == "index":
            return self._index_bars_reader.get_bars(
                BarsQuery(sids=sids, start_date=start_date, end_date=end_date)
            )
        raise ValueError(f"Unknown asset class: {asset_class}")

    def _enrich_data(
        self,
        df: pl.DataFrame,
        sids: list[int],
        enrich_with_status: bool,
    ) -> pl.DataFrame:
        """数据增强（Port 业务逻辑）"""
        # 1. 添加 symbol 列
        sid_to_symbol = self._instrument_reader.batch_resolve_symbol(
            sids, self._detect_asset_class(sids)
        )
        symbol_map = pl.DataFrame([
            {"sid": k, "symbol": v} for k, v in sid_to_symbol.items()
        ])
        df = df.join(symbol_map, on="sid", how="left")

        # 2. 添加状态信息
        if enrich_with_status:
            status = self._status_reader.get_status(sids, start_date, end_date)
            df = df.join(status, on=["sid", "trade_date"], how="left")

        return df
```

---

## 四、DataWriteService（只写服务）

### 4.1 设计原则

```
用户代码
    │
    ↓ df.DataFrame (包含 symbol 列)
DataWriteService
    │
    ├─→ resolve_sids()          # 通过 InstrumentWriter
    ├─→ allocate_sids()          # 通过 InstrumentWriter
    ├─→ QualityEngine.check()   # Domain 质量检查
    ├─→ transform_to_bars()     # 数据转换
    └─→ IBarsWriter.write_bars()  # 通过 Writer 接口
    │
    ↓
WriteResult
```

### 4.2 DataWriteService 实现

```python
# apps/port/src/ditto_port/services/data_write_service.py

from datetime import date
from typing import Literal

import polars as pl

from ditto_contracts.bars import BarsData
from ditto_core.quality import QualityEngine
from ditto_data.repositories import IBarsWriter
from ditto_data.repositories.metadata import IInstrumentWriter


class DataWriteService:
    """数据写入服务（Application Layer - 只写）

    职责：
    - 提供用户友好的写入 API
    - SID 分配（通过 InstrumentWriter）
    - 数据质量检查（QualityEngine）
    - 数据转换和验证

    不包含：
    - 数据查询（由 DataQueryService 负责）
    """

    def __init__(
        self,
        # Writers（只写接口）
        stock_bars_writer: IBarsWriter,
        etf_bars_writer: IBarsWriter,
        # Metadata Writers
        instrument_writer: IInstrumentWriter,
        # Domain
        quality_engine: QualityEngine,
    ):
        self._stock_bars_writer = stock_bars_writer
        self._etf_bars_writer = etf_bars_writer
        self._instrument_writer = instrument_writer
        self._quality_engine = quality_engine

    def write_bars(
        self,
        df: pl.DataFrame,
        dataset: Literal["stock", "etf", "index"],
        trade_date: date,
        source: str = "tushare",
        validate: bool = True,
    ) -> "WriteResult":
        """
        写入 K线数据（便捷 API）

        流程：
        1. 解析 symbols → SIDs
        2. 分配新 SIDs（通过 InstrumentWriter）
        3. DQ 检查
        4. 转换为 BarsData
        5. 写入数据（通过 Writer）

        Args:
            df: K线数据 DataFrame（包含 symbol 列）
            dataset: 数据集类型
            trade_date: 交易日期
            source: 数据源
            validate: 是否进行 DQ 检查

        Returns:
            写入结果
        """

        # 1. 解析和分配 SIDs
        sids, symbol_map = self._process_sids(df, dataset, trade_date, source)

        # 2. 替换 symbol 为 SID
        df = df.with_columns(
            pl.col("symbol").map_dict(symbol_map).alias("sid")
        )

        # 3. DQ 检查
        if validate:
            dq_result = self._quality_engine.check(df, dataset=dataset)
            if not dq_result.is_valid:
                return self._handle_dq_failure(dq_result)

        # 4. 转换为 BarsData
        bars_data = self._convert_to_bars_data(df)

        # 5. 写入数据
        if dataset == "stock":
            result = self._stock_bars_writer.write_bars(bars_data, "stock_bars")
        elif dataset == "etf":
            result = self._etfars_writer.write_bars(bars_data, "etf_bars")

        return result

    def _process_sids(
        self,
        df: pl.DataFrame,
        dataset: str,
        trade_date: date,
        source: str,
    ) -> tuple[list[int], dict[str, int]]:
        """处理和分配 SIDs"""

        # 解析现有 SIDs
        existing_sids = self._instrument_writer.batch_resolve_or_allocate(
            df["symbol"].unique().to_list(),
            dataset,
            trade_date,
            source,
        )

        # 转换为 SID 列表
        sids = [
            existing_sids[symbol]
            for symbol in df["symbol"].unique()
            if symbol in existing_sids
        ]

        return sids, existing_sids

    def _convert_to_bars_data(self, df: pl.DataFrame) -> list[BarsData]:
        """转换 DataFrame 为 BarsData 列表"""
        return [
            BarsData(
                sid=row["sid"],
                trade_date=row["trade_date"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                amount=row.get("amount"),
            )
            for row in df.iter_rows(named=True)
        ]
```

---

## 五、Instrument 仓储（CQRS）

### 5.1 读写分离

```python
# packages/data/src/ditto_data/repositories/metadata/instrument.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Literal


class IInstrumentReader(ABC):
    """证券信息读取接口"""

    @abstractmethod
    def resolve_sid(
        self,
        src_code: str,
        source: str,
        as_of: str | None = None,
    ) -> Optional[int]:
        """解析 src_code 到 SID"""
        pass

    @abstractmethod
    def batch_resolve_symbol(
        self,
        sids: list[int],
        asset_class: Literal["stock", "etf", "index"],
    ) -> dict[int, str]:
        """批量解析 SID → symbol"""
        pass

    @abstractmethod
    def get_instruments(
        self,
        query: "InstrumentQuery",
    ) -> pl.DataFrame:
        """查询证券信息"""
        pass


class IInstrumentWriter(ABC):
    """证券信息写入接口"""

    @abstractmethod
    def batch_resolve_or_allocate(
        self,
        symbols: list[str],
        asset_class: str,
        trade_date: date,
        source: str,
    ) -> dict[str, int]:
        """批量解析或分配 SIDs

        Returns:
            symbol → sid 映射字典
        """
        pass

    @abstractmethod
    def register_instrument(
        self,
        symbol: str,
        asset_class: str,
        source: str,
    ) -> int:
        """注册新证券，返回 SID"""
        pass
```

---

## 六、目录结构（v4.1）

```
ditto/
├── packages/
│   ├── contracts/                      # Contracts Layer（独立数据契约）
│   │   └── src/ditto_contracts/
│   │       ├── bars/                   # K线契约
│   │       │   ├── schema.py           # DataFrame Schema
│   │       │   ├── query.py            # BarsQuery
│   │       │   ├── models.py           # BarsData
│   │       │   └── enums.py            # AdjType, AssetClass
│   │       ├── factors/                # 因子契约
│   │       ├── financials/             # 财务契约
│   │       ├── metadata/               # 元数据契约
│   │       └── common/                 # 通用契约
│   │
│   ├── core/                           # Domain Layer
│   │   └── src/ditto_core/
│   │       ├── quality/                # 质量引擎
│   │       ├── market/                 # 市场域
│   │       │   ├── adjustment.py     # ✅ 复权引擎（Domain Logic）
│   │       │   └── ...
│   │       ├── factor/
│   │       ├── backtest/
│   │       ├── risk/
│   │       ├── strategy/
│   │       └── ml/
│   │
│   ├── datahub/                        # DataHub Layer
│   │   └── src/ditto_data/
│   │       ├── repositories/           # 仓储（CQRS 读写分离）
│   │       │   ├── stock/              # 股票仓储
│   │       │   │   ├── bars_reader.py  # ✅ 只读
│   │       │   │   └── bars_writer.py  # ✅ 只写
│   │       │   ├── etf/
│       │       │   ├── index/
│   │       │   ├── financials/
│   │       │   ├── factors/
│   │       │   └── metadata/           # 元数据仓储
│   │       │       ├── instrument_reader.py
│   │       │       ├── instrument_writer.py
│   │       │       ├── calendar_reader.py
│   │       │       └── universe_reader.py
│   │       │
│   │       ├── stores/                # 存储引擎
│   │       │   ├── base/
│   │       │   │   ├── parquet_store.py
│   │       │   │   ├── sqlite_store.py
│   │       │   │   └── partition_strategy.py
│   │       │
│       │       ├── sources/            # 数据源
│   │       │   │   └── tushare/
│   │       │   │
│   │       │       ├── pipelines/          # ETL 管道
│   │       │       │   └── transform.py
│   │       │       │
│   │       │       └── runtime/            # 运行时
│   │       │           ├── sid_allocator.py
│   │       │           └── freeze_manager.py
│   │       │
│   │       └── platform.py             # DataHub Facade
│   │
│   └── foundation/                    # Foundation Layer
│       └── src/ditto_foundation/
│           ├── config/
│           ├── logger/
│           ├── cache/
│           └── concurrency/
│
├── apps/
│   └── port/                          # Application Layer
│       └── src/ditto_port/
│           ├── services/               # 应用服务
│           │   ├── data_query_service.py       # ✅ 只读服务
│           │   ├── data_write_service.py      # ✅ 只写服务
│           │   ├── ingestion_service.py
│           │   └── ...
│           ├── orchestration/          # 编排器
│           │   ├── ingestion.py
│           │   ├── backtest.py
│           │   └── trading.py
│           ├── api/
│           ├── cli/
│           └── jobs/
│
└── data_root/
    ├── standard/                       # 标准数据
    │   ├── stock/
    │   ├── etf/
    │   ├── index/
    │   ├── financials/
    │   └── metadata/                   # SQLite
    └── derived/                        # 衍生数据
        ├── factors/
        ├── features/
        └── labels/
```

---

## 七、关键改进总结

| 改进项 | v4.0 | v4.1 | 理由 |
|--------|------|------|------|
| **复权计算** | DataHub Transformer | **Domain AdjustmentEngine** | 复权是金融业务逻辑 |
| **enrich 能力** | DataHub Transformer | **Application Layer 编排** | enrich 是业务编排 |
| **Repository** | 单一接口 | **CQRS 读写分离** | 安全性、职责清晰 |
| **SID 解析** | 直接调用 Store | **通过 InstrumentReader/Writer** | 接口抽象 |
| **API 分层** | 单一 Service | **三层 API** | Orchestrator → Service → Repository |

---

## 八、CQRS 读写分离的优势

### 8.1 安全性

| 问题 | 单一 Repository | CQRS 分离 |
|------|---------------|------------|
| **误操作风险** | Reader/Writer 混用，可能误写 | Reader 只读，Writer 需要事务 |
| **权限控制** | 需要细粒度权限 | Reader 只读权限，Writer 写权限 |
| **审计追踪** | 混合读写，难以审计 | 写入操作完全隔离 |

### 8.2 性能优化

| 优化方向 | 实现 |
|---------|------|
| **读优化** | Reader 可以缓存、使用视图 |
| **写优化** | Writer 批量写入、延迟刷新 |
| **复杂数据库** | 读模型用简单查询，写模型用复杂事务 |

### 8.3 可扩展性

| 需求 | 实现方式 |
|------|---------|
| **只读副本** | Reader 连接到只读副本 |
| **读写分离** | Reader 用 Parquet，Writer 用 SQLite |
| **事件溯源** | 写入操作生成事件，重建读模型 |

---

**文档版本**: 4.1
**最后更新**: 2026-02-07
