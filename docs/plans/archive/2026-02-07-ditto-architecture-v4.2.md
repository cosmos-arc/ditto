# Ditto 量化系统架构设计 v4.2

> **核心理念**：简洁的层次、清晰的职责、符合量化业务逻辑
>
> **基于业界最佳实践**：WorldQuant、Two Sigma、Citadel、九坤等领先量化机构的架构模式
>
> **设计日期**: 2026-02-07
>
> **v4.2 更新**：
> - Stores 命名（不用 Repository，更符合现有风格）
> - 无 Facade（Port 直接注入 Stores）
> - data_store.env/data_source.env 配置整合
> - DataStoreSettings/DataSourceSettings
> - CQRS 模式（读写分离）
> - 复权计算在 Domain Layer

---

## 一、核心架构决策

### 1.1 命名：Stores 而非 Repository

**理由**：
- ✅ 更符合 ditto 现有命名习惯（已有 stores/ 目录）
- ✅ 避免引入新概念，学习成本更低
- ✅ stores/reader, stores/writer 命名更直观

```python
# ❌ Repository 命名
IBarsRepository
StockBarsRepository

# ✅ Stores 命名
IBarsReader / IBarsWriter
StockBarsReader / StockBarsWriter
```

### 1.2 无 Facade 设计

**理由**：
- ✅ Port 直接注入需要的 Reader/Writer
- ✅ 减少中间层，依赖关系更清晰
- ✅ 不同应用可按需组合

```python
# ❌ v4.1: DataHub Facade
class DataHub:
    def __init__(self, ...):
        self.stock_bars_repo = ...
        self.instrument_repo = ...

# ✅ v4.2: Port 直接注入
class DataQueryService:
    def __init__(
        self,
        stock_bars_reader: StockBarsReader,  # 直接注入
        etf_bars_reader: EtfBarsReader,
        instrument_reader: InstrumentReader,
        adjustment_engine: AdjustmentEngine,
    ):
        ...
```

### 1.3 配置整合

**两个配置文件**：

| 配置文件 | 用途 | Settings 类 |
|---------|------|------------|
| `data_store.env` | Stores 配置（路径、分区、缓存） | `DataStoreSettings` |
| `data_source.env` | Sources 配置（API、重试、限流） | `DataSourceSettings` |

---

## 二、配置设计

### 2.1 data_store.env

```bash
# config/development/data_store.env

# ========== 基础路径 ==========
DATA_ROOT=data
DATA_LOGS_ROOT=data/logs
DATA_BACKUP_ROOT=data/backups
DATA_TEMP_ROOT=data/temp
DATA_DB_ROOT=data/db

# ========== 元数据配置 ==========
METADATA_DB_ENABLED=true
METADATA_DB_PATH=data/db/metadata.sqlite

# ========== Parquet 存储配置 ==========
PARQUET_COMPRESSION=snappy
PARQUET_STATISTICS=true
PARQUET_ROW_GROUP_SIZE=100000

# ========== 分区配置 ==========
PARTITION_STRATEGY=yearly
PARTITION_YEARLY_ENABLED=true

# ========== 缓存配置 ==========
CALENDAR_CACHE_ENABLED=true
CALENDAR_CACHE_TTL=3600
INSTRUMENT_CACHE_ENABLED=true
INSTRUMENT_CACHE_TTL=1800

# ========== PIT 配置 ==========
PIT_ENABLED=true
PIT_DEFAULT_KNOWLEDGE_DELAY=1
```

### 2.2 data_source.env

```bash
# config/development/data_source.env

# ========== Tushare 配置 ==========
TUSHARE_TOKEN=your_token_here
TUSHARE_BASE_URL=http://api.tushare.pro
TUSHARE_TIMEOUT=30.0

# ========== HTTP 配置 ==========
HTTP_TIMEOUT=30.0
HTTP_MAX_CONNECTIONS=100
HTTP_MAX_KEEPALIVE_CONNECTIONS=20

# ========== 重试配置 ==========
RETRY_MAX_ATTEMPTS=3
RETRY_MULTIPLIER=1.0
RETRY_MIN_WAIT=1.0
RETRY_MAX_WAIT=10.0
RETRY_JITTER_MAX=2.0

# ========== 限流配置 ==========
RATE_LIMIT_PROFILE=free
RATE_LIMIT_GLOBAL_RATE=1000
RATE_LIMIT_DAILY_RATE=5000

# ========== 通达信配置 ==========
TDX_ENABLED=false
TDX_PATH=D:\new_tdx\vipdoc
```

### 2.3 DataStoreSettings

```python
# packages/data/src/ditto_data/config/data_store.py

from pathlib import Path
from pydantic_settings import BaseSettings


class DataStoreSettings(BaseSettings):
    """Stores 配置（从 data_store.env 读取）"""

    model_config = {
        "env_prefix": "DATA_",
        "env_file": "config/development/data_store.env",
        "extra": "ignore",
    }

    # 基础路径
    root: Path = Path("data")
    logs_root: Path = Path("data/logs")
    backup_root: Path = Path("data/backups")
    temp_root: Path = Path("data/temp")
    db_root: Path = Path("data/db")

    # Parquet 配置
    parquet_compression: str = "snappy"
    parquet_statistics: bool = True
    parquet_row_group_size: int = 100000

    # 分区配置
    partition_strategy: str = "yearly"

    # 缓存配置
    calendar_cache_enabled: bool = True
    calendar_cache_ttl: int = 3600
    instrument_cache_enabled: bool = True
    instrument_cache_ttl: int = 1800

    # PIT 配置
    pit_enabled: bool = True
    pit_default_knowledge_delay: int = 1

    # ========== 派生路径 ==========

    @property
    def market_stock_bars_path(self) -> Path:
        return self.root / "market" / "stock" / "bars" / "daily"

    @property
    def market_etf_bars_path(self) -> Path:
        return self.root / "market" / "etf" / "bars" / "daily"

    @property
    def market_index_bars_path(self) -> Path:
        return self.root / "market" / "index" / "bars" / "daily"

    @property
    def metadata_db_path(self) -> Path:
        return self.db_root / "metadata.sqlite"


__all__ = ["DataStoreSettings"]
```

### 2.4 DataSourceSettings

```python
# packages/data/src/ditto_data/config/data_source.py

from pydantic_settings import BaseSettings


class DataSourceSettings(BaseSettings):
    """Sources 配置（从 data_source.env 读取）"""

    model_config = {
        "env_prefix": "",
        "env_file": "config/development/data_source.env",
        "extra": "ignore",
    }

    # Tushare
    tushare_token: str = ""
    tushare_base_url: str = "http://api.tushare.pro"
    tushare_timeout: float = 30.0

    # HTTP
    http_timeout: float = 30.0
    http_max_connections: int = 100
    http_max_keepalive_connections: int = 20

    # 重试
    retry_max_attempts: int = 3
    retry_multiplier: float = 1.0
    retry_min_wait: float = 1.0
    retry_max_wait: float = 10.0
    retry_jitter_max: float = 2.0

    # 限流
    rate_limit_profile: str = "free"
    rate_limit_global_rate: int | None = None
    rate_limit_daily_rate: int | None = None

    # 通达信
    tdx_enabled: bool = False
    tdx_path: str = "D:\\new_tdx\\vipdoc"


__all__ = ["DataSourceSettings"]
```

---

## 三、CQRS 模式（读写分离）

### 3.1 接口定义

```python
# packages/data/src/ditto_data/stores/market/bars.py
# 或独立 contracts 包

from abc import ABC, abstractmethod
import polars as pl


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

### 3.2 Reader 实现

```python
# packages/data/src/ditto_data/stores/market/stock/bars_reader.py

from pathlib import Path
import polars as pl

from ditto_data.config import DataStoreSettings
from ditto_data.stores.base import ParquetStore, YearlyPartition
from ditto_data.stores.market.bars import IBarsReader


class StockBarsReader(IBarsReader):
    """股票 K线读取器（只读）"""

    def __init__(self, config: DataStoreSettings):  # ✅ 注入 Config
        self._config = config
        self._store = ParquetStore(config.root, YearlyPartition())
        self._dataset = "market/stock/bars"

    def get_bars(self, query: "BarsQuery") -> pl.DataFrame:
        """读取 K线数据（只读操作）"""
        return self._store.read(
            self._dataset,
            sids=query.sids,
            start_date=query.start_date,
            end_date=query.end_date,
        )

    def get_latest_date(self, sid: int) -> str | None:
        """获取最新数据日期"""
        df = self._store.read(self._dataset, sids=[sid])
        if df.is_empty():
            return None
        return df["trade_date"].max()

    def get_date_range(self) -> tuple[str | None, str | None]:
        """获取数据日期范围"""
        return self._store.get_date_range(self._dataset)
```

### 3.3 Writer 实现

```python
# packages/data/src/ditto_data/stores/market/stock/bars_writer.py

from pathlib import Path
import polars as pl

from ditto_data.config import DataStoreSettings
from ditto_data.stores.base import ParquetStore, YearlyPartition
from ditto_data.stores.market.bars import IBarsWriter


class StockBarsWriter(IBarsWriter):
    """股票 K线写入器（只写）"""

    def __init__(self, config: DataStoreSettings):  # ✅ 注入 Config
        self._config = config
        self._store = ParquetStore(config.root, YearlyPartition())
        self._dataset = "market/stock/bars"

    def write_bars(
        self,
        data: list["BarsData"],
        dataset: str,
    ) -> "BarsWriteResult":
        """写入 K线数据"""
        df = pl.DataFrame([d.model_dump() for d in data])
        year = df["trade_date"][0].year
        return self._store.write(self._dataset, df, year=year)

    def delete_bars(
        self,
        sids: list[int],
        start_date: str,
        end_date: str,
    ) -> int:
        """删除 K线数据"""
        return self._store.delete(
            self._dataset,
            sids=sids,
            start_date=start_date,
            end_date=end_date,
        )

    def begin_transaction(self) -> "ITransaction":
        """开始事务"""
        return BarsTransaction(self._store, self._dataset)
```

---

## 四、DataQueryService（Port 侧）

### 4.1 设计

```python
# apps/port/src/ditto_port/services/data/data_query_service.py

from datetime import date
from typing import Literal
import polars as pl

from ditto_data.config import DataStoreSettings
from ditto_data.stores.market.stock import StockBarsReader
from ditto_data.stores.market.etf import EtfBarsReader
from ditto_data.stores.market.index import IndexBarsReader
from ditto_data.stores.metadata import InstrumentReader, StatusReader
from ditto_core.market.adjustment import AdjustmentEngine  # Domain!


class DataQueryService:
    """数据查询服务（Port 侧 - 只读）

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
        # Stores (Reader)
        stock_bars_reader: StockBarsReader,
        etf_bars_reader: EtfBarsReader,
        index_bars_reader: IndexBarsReader,
        instrument_reader: InstrumentReader,
        status_reader: StatusReader,
        # Domain Engine
        adjustment_engine: AdjustmentEngine,
    ):
        self._stock_bars = stock_bars_reader
        self._etf_bars = etf_bars_reader
        self._index_bars = index_bars_reader
        self._instrument = instrument_reader
        self._status = status_reader
        self._adjustment = adjustment_engine

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
        """获取 K线数据（便捷 API）"""

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
            df = self._adjustment.apply_qfq(df, adj_factors, as_of)

        # 5. 数据增强（Port 逻辑）
        df = self._enrich_data(df, sids, enrich_with_status)

        return df

    def _resolve_sids(
        self,
        symbols: list[str],
        asset_class: Literal["stock", "etf", "index"] | None,
    ) -> list[int]:
        """解析 symbols → SIDs"""
        # 检查是否已经是 SIDs
        if all(s.isdigit() for s in symbols):
            return [int(s) for s in symbols]

        # 解析 symbol → SID
        sids = []
        for symbol in symbols:
            source = self._extract_source(symbol)
            sid = self._instrument.resolve_sid(symbol, source)
            if sid:
                sids.append(sid)
        return sids

    def _read_bars(
        self,
        sids: list[int],
        start_date: date,
        end_date: date,
        asset_class: Literal["stock", "etf", "index"],
    ) -> pl.DataFrame:
        """读取原始数据"""
        if asset_class == "stock":
            return self._stock_bars.get_bars(
                BarsQuery(sids=sids, start_date=start_date, end_date=end_date)
            )
        elif asset_class == "etf":
            return self._etf_bars.get_bars(
                BarsQuery(sids=sids, start_date=start_date, end_date=end_date)
            )
        elif asset_class == "index":
            return self._index_bars.get_bars(
                BarsQuery(sids=sids, start_date=start_date, end_date=end_date)
            )
        raise ValueError(f"Unknown asset class: {asset_class}")
```

---

## 五、DataWriteService（Port 侧）

### 5.1 设计

```python
# apps/port/src/ditto_port/services/data/data_write_service.py

from datetime import date
from typing import Literal
import polars as pl

from ditto_data.config import DataStoreSettings
from ditto_data.stores.market.stock import StockBarsWriter
from ditto_data.stores.market.etf import EtfBarsWriter
from ditto_data.stores.metadata import InstrumentWriter
from ditto_core.quality import QualityEngine


class DataWriteService:
    """数据写入服务（Port 侧 - 只写）

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
        # Stores (Writer)
        stock_bars_writer: StockBarsWriter,
        etf_bars_writer: EtfBarsWriter,
        instrument_writer: InstrumentWriter,
        adj_factor_writer: AdjFactorWriter,
        status_writer: StatusWriter,
        # DQ
        quality_engine: QualityEngine,
    ):
        self._stock_bars = stock_bars_writer
        self._etf_bars = etf_bars_writer
        self._instrument = instrument_writer
        self._adj_factor = adj_factor_writer
        self._status = status_writer
        self._quality = quality_engine

    def write_bars(
        self,
        df: pl.DataFrame,
        dataset: Literal["stock", "etf", "index"],
        trade_date: date,
        source: str = "tushare",
        validate: bool = True,
    ) -> "WriteResult":
        """写入 K线数据（便捷 API）"""

        # 1. 解析和分配 SIDs
        sids, symbol_map = self._process_sids(df, dataset, trade_date, source)

        # 2. 替换 symbol 为 SID
        df = df.with_columns(
            pl.col("symbol").map_dict(symbol_map).alias("sid")
        )

        # 3. DQ 检查
        if validate:
            dq_result = self._quality.check(df, dataset=dataset)
            if not dq_result.is_valid:
                return self._handle_dq_failure(dq_result)

        # 4. 转换为 BarsData
        bars_data = self._convert_to_bars_data(df)

        # 5. 写入数据
        if dataset == "stock":
            result = self._stock_bars.write_bars(bars_data, "stock_bars")
        elif dataset == "etf":
            result = self._etf_bars.write_bars(bars_data, "etf_bars")

        return result
```

---

## 六、复权计算（Domain Layer）

### 6.1 AdjustmentEngine

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
```

---

## 七、依赖注入（Port 侧）

### 7.1 容器配置

```python
# apps/port/src/ditto_port/container.py

from dishka import Container, make_container, Provider, from_provider
from ditto_data.config import DataStoreSettings, DataSourceSettings
from ditto_data.stores.market.stock import StockBarsReader, StockBarsWriter
from ditto_data.stores.market.etf import EtfBarsReader, EtfBarsWriter
from ditto_data.stores.metadata import InstrumentReader, InstrumentWriter
from ditto_core.market.adjustment import AdjustmentEngine
from ditto_port.services.data import DataQueryService, DataWriteService


def create_container() -> Container:
    """创建 Port 侧容器"""

    return make_container(Provider(
        # Config
        DataStoreSettings=DataStoreSettings,
        DataSourceSettings=DataSourceSettings,

        # Stores - Reader
        StockBarsReader: from_provider(),
        EtfBarsReader: from_provider(),
        InstrumentReader: from_provider(),

        # Stores - Writer
        StockBarsWriter: from_provider(),
        EtfBarsWriter: from_provider(),
        InstrumentWriter: from_provider(),

        # Domain
        AdjustmentEngine: lambda cfg: AdjustmentEngine(),

        # Port Services
        DataQueryService: from_provider(),
        DataWriteService: from_provider(),
    ))
```

### 7.2 API 路由使用

```python
# apps/port/src/ditto_port/api/routes.py

from fastapi import APIRouter, Depends
from ditto_port.services.data import DataQueryService
from ditto_port.container import get_data_query_service


router = APIRouter(prefix="/api/v1")


@router.get("/bars")
async def get_bars(
    symbols: list[str],
    start_date: date,
    end_date: date,
    adj: AdjType = AdjType.NONE,
    service: DataQueryService = Depends(get_data_query_service),
) -> pl.DataFrame:
    """获取 K线数据"""
    return service.get_bars(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        adj=adj,
    )
```

---

## 八、目录结构（v4.2）

```
ditto/
├── packages/
│   ├── contracts/                      # 数据契约（可选独立包）
│   │   └── src/ditto_contracts/
│   │       ├── bars/
│   │       │   ├── schema.py
│   │       │   ├── query.py            # BarsQuery
│   │       │   ├── models.py           # BarsData
│   │       │   └── interfaces.py       # IBarsReader/Writer
│   │       └── metadata/
│   │
│   ├── core/                           # Domain Layer
│   │   └── src/ditto_core/
│   │       ├── quality/                # QualityEngine
│   │       └── market/
│   │           └── adjustment.py       # AdjustmentEngine ✅
│   │
│   ├── datahub/                        # DataHub Layer（无 Facade）
│   │   └── src/ditto_data/
│   │       ├── config/                 # 配置
│   │       │   ├── __init__.py
│   │       │   ├── data_store.py       # DataStoreSettings ✅
│   │       │   └── data_source.py      # DataSourceSettings ✅
│   │       │
│   │       ├── stores/                 # ✅ Stores（按业务域组织）
│   │       │   ├── parquet_store.py    # 基础存储（从 base/ 移出）
│   │       │   ├── sqlite_store.py     # 基础存储
│   │       │   │
│   │       │   ├── market/             # 市场数据
│   │       │   │   ├── stock/
│   │       │   │   │   ├── bars_reader.py   # ✅
│   │       │   │   │   ├── bars_writer.py   # ✅
│   │       │   │   │   ├── adj_reader.py
│   │       │   │   │   └── status_reader.py
│   │       │   │   ├── etf/
│   │       │   │   └── index/
│   │       │   │
│   │       │   ├── metadata/           # 元数据
│   │       │   │   ├── instrument_reader.py
│   │       │   │   ├── instrument_writer.py
│   │       │   │   └── calendar_reader.py
│   │       │   │
│   │       │   ├── fundamental/
│   │       │   ├── capital/
│   │       │   └── macro/
│   │       │
│   │       ├── sources/                # ✅ Sources（与 stores 平级）
│   │       │   ├── tushare_source.py   # 依赖 DataSourceSettings
│   │       │   └── akshare_source.py
│   │       │
│   │       ├── models/                 # 数据模型
│   │       │   ├── common.py
│   │       │   └── ...
│   │       │
│   │       └── __init__.py             # 导出 Reader/Writer
│   │
│   └── foundation/                     # Foundation Layer
│       └── src/ditto_foundation/
│           ├── config/
│           ├── logger/
│           └── cache/
│
├── apps/
│   └── port/                          # Application Layer（无 Facade 依赖）
│       └── src/ditto_port/
│           ├── services/               # ✅ 应用服务（直接依赖 Stores）
│           │   ├── data/
│           │   │   ├── data_query_service.py    # ✅ 只读服务
│           │   │   └── data_write_service.py    # ✅ 只写服务
│           │   ├── ingestion/
│           │   │   └── coordinator.py
│           │   └── backtest/
│           │
│           ├── api/                    # FastAPI 路由
│           │   └── routes.py
│           │
│           ├── container.py            # ✅ 依赖注入容器
│           └── main.py
│
└── config/
    ├── development/
    │   ├── data_store.env              # ✅ Stores 配置
    │   └── data_source.env             # ✅ Sources 配置
    ├── testing/
    └── production/
```

---

## 九、依赖关系图

```
┌─────────────────────────────────────────────────────────────┐
│                        Port Layer                           │
│  ┌──────────────────┐        ┌──────────────────┐          │
│  │ DataQueryService │◄──────┤ DataWriteService │          │
│  │  (read-only)     │        │   (write-only)   │          │
│  └────────┬─────────┘        └────────┬─────────┘          │
│           │                           │                      │
└───────────┼───────────────────────────┼──────────────────────┘
            │                           │
            ▼                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      DataHub Layer                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────┐   │
│  │   *Reader       │  │   *Writer       │  │  *Source  │   │
│  │   (read)        │  │   (write)       │  │  (fetch)  │   │
│  └─────────────────┘  └─────────────────┘  └───────────┘   │
│         ▲                                                    │
│         │ DataStoreSettings                                 │
└─────────┼────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                       Core Layer                            │
│  ┌─────────────────────────────────────────────────┐        │
│  │           AdjustmentEngine                       │        │
│  │  (复权计算 - Domain 业务逻辑)                     │        │
│  └─────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

---

## 十、关键改进总结

| 改进项 | v4.1 | v4.2 | 理由 |
|--------|------|------|------|
| **命名** | Repository | **Stores** | 符合现有风格 |
| **Facade** | DataHub Facade | **无 Facade** | Port 直接注入 |
| **配置** | 分散 | **data_store/data_source** | 配置整合 |
| **注入方式** | 直接注入 data_root | **注入 Config 对象** | 更规范 |
| **复权计算** | Domain Layer | **保持 Domain Layer** | 业务逻辑 |
| **读写分离** | CQRS | **保持 CQRS** | 安全性 |

---

## 十一、CQRS 优势

### 11.1 安全性

| 问题 | 单一 Store | CQRS 分离 |
|------|-----------|------------|
| **误操作风险** | Reader/Writer 混用 | Reader 只读，Writer 需要事务 |
| **权限控制** | 需要细粒度权限 | Reader 只读权限，Writer 写权限 |
| **审计追踪** | 混合读写 | 写入操作完全隔离 |

### 11.2 命名清晰度

| v4.1 (Repository) | v4.2 (Stores) | 评价 |
|-------------------|---------------|------|
| `IBarsRepository` | `IBarsReader / IBarsWriter` | ✅ 更清晰 |
| `StockBarsRepository` | `StockBarsReader / StockBarsWriter` | ✅ 职责明确 |

---

**文档版本**: 4.2
**最后更新**: 2026-02-07
