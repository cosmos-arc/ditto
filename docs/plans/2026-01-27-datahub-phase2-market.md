# DataHub Market 域重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**目标:** 将现有的 Market 数据相关 Store 和 Accessor 重构为统一的 Market 域结构，实现 domains/market/ 目录组织

**架构:**
- 创建 `domains/market/` 目录，按资产类型（stock/etf/index）组织
- 实现 MarketQueryService 作为域级统一入口
- 合并 bars、status、adj_factor 等子域
- 移除 BarsAccessor，功能合并到 MarketQueryService

**技术栈:** Python 3.12+, Polars, Pydantic, Pyright Strict

**前置依赖:** Phase 0 - 基础层重构, Phase 1 - Metadata 域重构

---

## 目录结构

```
packages/datahub/src/ditto_datahub/domains/market/
├── __init__.py
├── stock/
│   ├── __init__.py
│   ├── bars/bars_store.py           # 从 stores/ 迁移
│   ├── bars/models.py
│   ├── status/status_store.py       # 从 stores/ 迁移
│   ├── status/models.py
│   └── adj/adj_factor_store.py      # 从 stores/ 迁移
├── etf/
│   ├── __init__.py
│   ├── bars/bars_store.py           # 新增
│   ├── status/status_store.py       # 新增
│   ├── nav/nav_store.py             # 新增
│   └── adj/adj_factor_store.py      # 新增
├── index/
│   ├── __init__.py
│   ├── bars/bars_store.py           # 新增
│   └── constituent/constituent_store.py  # 新增
└── market_query_service.py          # 域级查询服务
```

---

## 任务 1: 创建 Market 域目录结构

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/market/__init__.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/market/stock/__init__.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/market/etf/__init__.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/market/index/__init__.py`

**步骤 1: 创建域级 __init__.py**

```python
# packages/datahub/src/ditto_datahub/domains/market/__init__.py
"""Market 域 - 市场数据访问."""

from ditto_datahub.domains.market.market_query_service import MarketQueryService

__all__ = ["MarketQueryService"]
```

**步骤 2: 创建子域 __init__.py**

```python
# packages/datahub/src/ditto_datahub/domains/market/stock/__init__.py
"""Stock 子域 - 股票市场数据."""

# packages/datahub/src/ditto_datahub/domains/market/etf/__init__.py
"""ETF 子域 - ETF 市场数据."""

# packages/datahub/src/ditto_datahub/domains/market/index/__init__.py
"""Index 子域 - 指数市场数据."""
```

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/market/
git commit -m "feat(datahub): create Market domain directory structure"
```

---

## 任务 2: 迁移 Stock Bars 到 Market 域

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/market/stock/bars/bars_store.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/market/stock/bars/models.py`
- 修改: `packages/datahub/src/ditto_datahub/stores/bars_store.py` (添加弃用警告)

**步骤 1: 定义数据模型**

```python
# packages/datahub/src/ditto_datahub/domains/market/stock/bars/models.py
"""Stock bars 数据模型."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AdjType(Enum):
    """复权类型."""

    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


@dataclass(frozen=True)
class StockBarsQuery:
    """股票 K线查询参数."""

    sids: list[int]
    start: str | None = None
    end: str | None = None
    adj: AdjType = AdjType.NONE
    asof: str | None = None
    with_symbol: bool = False
    with_status: bool = False
    raw: bool = False
```

**步骤 2: 迁移 StockBarsStore**

```python
# packages/datahub/src/ditto_datahub/domains/market/stock/bars/bars_store.py
"""
StockBarsStore for stock OHLCV data.

从 stores/bars_store.py 迁移而来，专门处理股票数据。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.domains.market.stock.bars.models import AdjType, StockBarsQuery
from ditto_datahub.stores.base.parquet_store import ParquetStore


class StockBarsStore(ParquetStore):
    """
    股票 K线数据存储。

    迁移路径: stores/bars_store.py -> domains/market/stock/bars/bars_store.py

    专门处理 stock_daily 数据集。
    """

    def __init__(self, data_root: Path) -> None:
        """初始化 StockBarsStore."""
        super().__init__(data_root)

    def _get_dataset_path(self, dataset: str) -> Path:
        """获取数据集存储路径."""
        if dataset == "stock_daily":
            return self.data_root / "market" / "stock" / "bars" / "daily"
        return self.data_root / dataset

    @traced("data.stock_bars.read")
    def read(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """
        读取股票 K线数据。

        Args:
            sids: SID 列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            K线数据 DataFrame

        """
        return super().read(
            dataset="stock_daily",
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            **kwargs,
        )

    @traced("data.stock_bars.write")
    def write(
        self,
        data: pl.DataFrame,
        year: int,
        **kwargs: Any,
    ) -> Any:
        """
        写入股票 K线数据.

        Args:
            data: K线数据 DataFrame
            year: 年份分区

        Returns:
            写入结果

        """
        return super().write(
            dataset="stock_daily",
            data=data,
            year=year,
            **kwargs,
        )
```

**步骤 3: 在旧位置添加弃用警告**

```python
# packages/datahub/src/ditto_datahub/stores/bars_store.py
"""
BarsStore for market bars data.

⚠️ DEPRECATED: 此模块已迁移到 domains/market/ 下的子域

请使用新的导入路径：
    from ditto_datahub.domains.market.stock.bars import StockBarsStore
    from ditto_datahub.domains.market.etf.bars import EtfBarsStore
    from ditto_datahub.domains.market.index.bars import IndexBarsStore
"""

import warnings

warnings.warn(
    "BarsStore 已迁移到 ditto_datahub.domains.market.*.bars",
    DeprecationWarning,
    stacklevel=2,
)

from ditto_datahub.domains.market.stock.bars.bars_store import StockBarsStore
from ditto_datahub.domains.market.etf.bars.bars_store import EtfBarsStore
from ditto_datahub.domains.market.index.bars.bars_store import IndexBarsStore

__all__ = ["StockBarsStore", "EtfBarsStore", "IndexBarsStore"]
```

**步骤 4: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/market/stock/bars/
git add packages/datahub/src/ditto_datahub/stores/bars_store.py
git commit -m "refactor(datahub): migrate StockBars to domains/market/stock/bars/"
```

---

## 任务 3: 迁移 Stock Status 到 Market 域

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/market/stock/status/status_store.py`
- 修改: `packages/datahub/src/ditto_datahub/stores/stock_status_store.py`

**步骤 1: 迁移 StockStatusStore**

```python
# packages/datahub/src/ditto_datahub/domains/market/stock/status/status_store.py
"""
StockStatusStore for stock status data.

从 stores/stock_status_store.py 迁移而来。
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.base.parquet_store import ParquetStore


class StockStatusStore(ParquetStore):
    """
    股票状态数据存储。

    迁移路径: stores/stock_status_store.py -> domains/market/stock/status/status_store.py

    存储股票的停牌、ST、涨跌停等状态信息。
    """

    def __init__(self, data_root: Path) -> None:
        """初始化 StockStatusStore."""
        super().__init__(data_root)

    def _get_dataset_path(self, dataset: str) -> Path:
        """获取数据集存储路径."""
        if dataset == "stock_status":
            return self.data_root / "market" / "stock" / "status"
        return self.data_root / dataset

    # ... 复制现有 StockStatusStore 的所有方法 ...
```

**步骤 2: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/market/stock/status/
git add packages/datahub/src/ditto_datahub/stores/stock_status_store.py
git commit -m "refactor(datahub): migrate StockStatus to domains/market/stock/status/"
```

---

## 任务 4: 迁移 Stock AdjFactor 到 Market 域

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/market/stock/adj/adj_factor_store.py`
- 修改: `packages/datahub/src/ditto_datahub/stores/adj_factor_store.py`

**步骤 1: 迁移 AdjFactorStore**

```python
# packages/datahub/src/ditto_datahub/domains/market/stock/adj/adj_factor_store.py
"""
StockAdjFactorStore for stock adjustment factors.

从 stores/adj_factor_store.py 迁移而来。
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.base.parquet_store import ParquetStore


class StockAdjFactorStore(ParquetStore):
    """
    股票复权因子存储。

    迁移路径: stores/adj_factor_store.py -> domains/market/stock/adj/adj_factor_store.py

    支持前复权和后复权因子查询。
    """

    def __init__(self, data_root: Path) -> None:
        """初始化 StockAdjFactorStore."""
        super().__init__(data_root)

    def _get_dataset_path(self, dataset: str) -> Path:
        """获取数据集存储路径."""
        if dataset == "stock_adj_factor":
            return self.data_root / "market" / "stock" / "adj"
        return self.data_root / dataset

    # ... 复制现有 AdjFactorStore 的所有方法 ...
```

**步骤 2: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/market/stock/adj/
git add packages/datahub/src/ditto_datahub/stores/adj_factor_store.py
git commit -m "refactor(datahub): migrate StockAdjFactor to domains/market/stock/adj/"
```

---

## 任务 5: 实现 ETF 相关 Store

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/market/etf/bars/bars_store.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/market/etf/status/status_store.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/market/etf/nav/nav_store.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/market/etf/adj/adj_factor_store.py`

**步骤 1: 实现 EtfBarsStore**

```python
# packages/datahub/src/ditto_datahub/domains/market/etf/bars/bars_store.py
"""
EtfBarsStore for ETF OHLCV data.

与 StockBarsStore 结构一致，但处理 etf_daily 数据集。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import traced

from ditto_datahub.stores.base.parquet_store import ParquetStore


class EtfBarsStore(ParquetStore):
    """ETF K线数据存储."""

    def __init__(self, data_root: Path) -> None:
        """初始化 EtfBarsStore."""
        super().__init__(data_root)

    def _get_dataset_path(self, dataset: str) -> Path:
        """获取数据集存储路径."""
        if dataset == "etf_daily":
            return self.data_root / "market" / "etf" / "bars" / "daily"
        return self.data_root / dataset

    @traced("data.etf_bars.read")
    def read(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """读取 ETF K线数据."""
        return super().read(
            dataset="etf_daily",
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            **kwargs,
        )

    @traced("data.etf_bars.write")
    def write(
        self,
        data: pl.DataFrame,
        year: int,
        **kwargs: Any,
    ) -> Any:
        """写入 ETF K线数据."""
        return super().write(
            dataset="etf_daily",
            data=data,
            year=year,
            **kwargs,
        )
```

**步骤 2: 实现 EtfStatusStore**

```python
# packages/datahub/src/ditto_datahub/domains/market/etf/status/status_store.py
"""
EtfStatusStore for ETF status data.

与 StockStatusStore 结构一致，但包含 ETF 特有字段。
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_foundation import traced

from ditto_datahub.stores.base.parquet_store import ParquetStore


class EtfStatusStore(ParquetStore):
    """ETF 状态数据存储."""

    def __init__(self, data_root: Path) -> None:
        """初始化 EtfStatusStore."""
        super().__init__(data_root)

    def _get_dataset_path(self, dataset: str) -> Path:
        """获取数据集存储路径."""
        if dataset == "etf_status":
            return self.data_root / "market" / "etf" / "status"
        return self.data_root / dataset
```

**步骤 3: 实现 EtfNavStore**

```python
# packages/datahub/src/ditto_datahub/domains/market/etf/nav/nav_store.py
"""
EtfNavStore for ETF net asset value data.

存储 ETF 的净值数据。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import traced

from ditto_datahub.stores.base.parquet_store import ParquetStore


class EtfNavStore(ParquetStore):
    """ETF 净值数据存储."""

    def __init__(self, data_root: Path) -> None:
        """初始化 EtfNavStore."""
        super().__init__(data_root)

    def _get_dataset_path(self, dataset: str) -> Path:
        """获取数据集存储路径."""
        if dataset == "etf_nav":
            return self.data_root / "market" / "etf" / "nav"
        return self.data_root / dataset

    @traced("data.etf_nav.read")
    def read(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """读取 ETF 净值数据."""
        return super().read(
            dataset="etf_nav",
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            **kwargs,
        )

    @traced("data.etf_nav.write")
    def write(
        self,
        data: pl.DataFrame,
        year: int,
        **kwargs: Any,
    ) -> Any:
        """写入 ETF 净值数据."""
        return super().write(
            dataset="etf_nav",
            data=data,
            year=year,
            **kwargs,
        )
```

**步骤 4: 实现 EtfAdjFactorStore**

```python
# packages/datahub/src/ditto_datahub/domains/market/etf/adj/adj_factor_store.py
"""
EtfAdjFactorStore for ETF adjustment factors.

与 StockAdjFactorStore 结构一致，但计算逻辑不同。
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_foundation import traced

from ditto_datahub.stores.base.parquet_store import ParquetStore


class EtfAdjFactorStore(ParquetStore):
    """ETF 复权因子存储."""

    def __init__(self, data_root: Path) -> None:
        """初始化 EtfAdjFactorStore."""
        super().__init__(data_root)

    def _get_dataset_path(self, dataset: str) -> Path:
        """获取数据集存储路径."""
        if dataset == "etf_adj_factor":
            return self.data_root / "market" / "etf" / "adj"
        return self.data_root / dataset
```

**步骤 5: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/market/etf/
git commit -m "feat(datahub): implement ETF domain stores (Bars, Status, Nav, AdjFactor)"
```

---

## 任务 6: 实现 Index 相关 Store

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/market/index/bars/bars_store.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/market/index/constituent/constituent_store.py`

**步骤 1: 实现 IndexBarsStore**

```python
# packages/datahub/src/ditto_datahub/domains/market/index/bars/bars_store.py
"""
IndexBarsStore for index OHLCV data.

与 StockBarsStore 结构一致，但处理 index_daily 数据集。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import traced

from ditto_datahub.stores.base.parquet_store import ParquetStore


class IndexBarsStore(ParquetStore):
    """指数 K线数据存储."""

    def __init__(self, data_root: Path) -> None:
        """初始化 IndexBarsStore."""
        super().__init__(data_root)

    def _get_dataset_path(self, dataset: str) -> Path:
        """获取数据集存储路径."""
        if dataset == "index_daily":
            return self.data_root / "market" / "index" / "bars" / "daily"
        return self.data_root / dataset

    @traced("data.index_bars.read")
    def read(
        self,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """读取指数 K线数据."""
        return super().read(
            dataset="index_daily",
            sids=sids,
            start_date=start_date,
            end_date=end_date,
            **kwargs,
        )

    @traced("data.index_bars.write")
    def write(
        self,
        data: pl.DataFrame,
        year: int,
        **kwargs: Any,
    ) -> Any:
        """写入指数 K线数据."""
        return super().write(
            dataset="index_daily",
            data=data,
            year=year,
            **kwargs,
        )
```

**步骤 2: 实现 IndexConstituentStore**

```python
# packages/datahub/src/ditto_datahub/domains/market/index/constituent/constituent_store.py
"""
IndexConstituentStore for index constituent data.

存储指数成分股，支持 PIT 查询。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import traced

from ditto_datahub.stores.base.sqlite_store import SQLiteStore


class IndexConstituentStore(SQLiteStore):
    """指数成分股存储."""

    def __init__(self, db_path: Path) -> None:
        """初始化 IndexConstituentStore."""
        super().__init__(db_path)

    @traced("data.index_constituent.get")
    def get(
        self,
        index_sid: int,
        asof: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        获取指数成分股。

        Args:
            index_sid: 指数 SID
            asof: Point-in-time 查询日期

        Returns:
            成分股列表

        """
        if asof:
            return self.fetchall(
                """SELECT * FROM index_constituent
                WHERE index_sid = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY weight DESC""",
                [index_sid, asof, asof],
            )
        else:
            return self.fetchall(
                """SELECT * FROM index_constituent
                WHERE index_sid = ? AND effective_to IS NULL
                ORDER BY weight DESC""",
                [index_sid],
            )
```

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/market/index/
git commit -m "feat(datahub): implement Index domain stores (Bars, Constituent)"
```

---

## 任务 7: 实现 MarketQueryService

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/market/market_query_service.py`

**步骤 1: 实现 MarketQueryService**

```python
# packages/datahub/src/ditto_datahub/domains/market/market_query_service.py
"""
MarketQueryService - Market 域统一查询入口。

合并 BarsAccessor 的功能。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Literal

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.domains.market.stock.bars.bars_store import StockBarsStore
from ditto_datahub.domains.market.stock.status.status_store import StockStatusStore
from ditto_datahub.domains.market.stock.adj.adj_factor_store import StockAdjFactorStore
from ditto_datahub.domains.market.etf.bars.bars_store import EtfBarsStore
from ditto_datahub.domains.market.etf.status.status_store import EtfStatusStore
from ditto_datahub.domains.market.etf.nav.nav_store import EtfNavStore
from ditto_datahub.domains.market.etf.adj.adj_factor_store import EtfAdjFactorStore
from ditto_datahub.domains.market.index.bars.bars_store import IndexBarsStore
from ditto_datahub.domains.market.index.constituent.constituent_store import IndexConstituentStore


class AdjType(Enum):
    """复权类型."""

    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


@dataclass(frozen=True)
class MarketBarsQuery:
    """Market K线查询参数."""

    sids: list[int]
    start: str | None = None
    end: str | None = None
    adj: AdjType = AdjType.NONE
    asof: str | None = None
    asset_class: Literal["stock", "etf", "index"] | None = None
    with_symbol: bool = False
    with_status: bool = False
    raw: bool = False


class MarketQueryService:
    """
    Market 域统一查询服务。

    整合 Market 域所有 Store 的查询功能。

    替代: BarsAccessor
    """

    def __init__(  # noqa: PLR0913
        self,
        stock_bars_store: StockBarsStore,
        stock_status_store: StockStatusStore,
        stock_adj_store: StockAdjFactorStore,
        etf_bars_store: EtfBarsStore,
        etf_status_store: EtfStatusStore,
        etf_nav_store: EtfNavStore | None = None,
        etf_adj_store: EtfAdjFactorStore | None = None,
        index_bars_store: IndexBarsStore | None = None,
        index_constituent_store: IndexConstituentStore | None = None,
    ) -> None:
        """
        初始化 MarketQueryService.

        Args:
            stock_bars_store: 股票 K线存储.
            stock_status_store: 股票状态存储.
            stock_adj_store: 股票复权因子存储.
            etf_bars_store: ETF K线存储.
            etf_status_store: ETF 状态存储.
            etf_nav_store: ETF 净值存储（可选）.
            etf_adj_store: ETF 复权因子存储（可选）.
            index_bars_store: 指数 K线存储（可选）.
            index_constituent_store: 指数成分股存储（可选）.

        """
        self._stock_bars_store = stock_bars_store
        self._stock_status_store = stock_status_store
        self._stock_adj_store = stock_adj_store
        self._etf_bars_store = etf_bars_store
        self._etf_status_store = etf_status_store
        self._etf_nav_store = etf_nav_store
        self._etf_adj_store = etf_adj_store
        self._index_bars_store = index_bars_store
        self._index_constituent_store = index_constituent_store

    @traced("market.get_bars")
    def get_bars(self, query: MarketBarsQuery) -> pl.DataFrame:
        """
        获取 K线数据。

        替代 BarsAccessor.get()

        """
        # 根据 asset_class 选择对应的 Store
        if query.asset_class == "stock" or not query.asset_class:
            return self._get_stock_bars(query)
        elif query.asset_class == "etf":
            return self._get_etf_bars(query)
        elif query.asset_class == "index":
            return self._get_index_bars(query)
        else:
            return pl.DataFrame()

    def _get_stock_bars(self, query: MarketBarsQuery) -> pl.DataFrame:
        """获取股票 K线."""
        df = self._stock_bars_store.read(
            sids=query.sids,
            start_date=query.start,
            end_date=query.end,
        )

        if df.is_empty():
            return df

        # 应用复权
        if not query.raw and query.adj != AdjType.NONE:
            df = self._apply_stock_adj(df, query)

        # 添加状态
        if query.with_status and not query.raw:
            df = self._enrich_stock_status(df, query)

        return df

    def _get_etf_bars(self, query: MarketBarsQuery) -> pl.DataFrame:
        """获取 ETF K线."""
        return self._etf_bars_store.read(
            sids=query.sids,
            start_date=query.start,
            end_date=query.end,
        )

    def _get_index_bars(self, query: MarketBarsQuery) -> pl.DataFrame:
        """获取指数 K线."""
        return self._index_bars_store.read(
            sids=query.sids,
            start_date=query.start,
            end_date=query.end,
        )

    def _apply_stock_adj(
        self,
        df: pl.DataFrame,
        query: MarketBarsQuery,
    ) -> pl.DataFrame:
        """应用股票复权."""
        # 读取复权因子
        adj_df = self._stock_adj_store.read(
            sids=query.sids,
            start_date=query.start,
            end_date=query.end,
        )

        if adj_df.is_empty():
            return df

        # 应用复权逻辑 (简化示例)
        if query.adj == AdjType.QFQ:
            # 前复权逻辑
            ...
        elif query.adj == AdjType.HFQ:
            # 后复权逻辑
            ...

        return df

    def _enrich_stock_status(
        self,
        df: pl.DataFrame,
        query: MarketBarsQuery,
    ) -> pl.DataFrame:
        """添加股票状态信息."""
        # 读取状态数据
        status_df = self._stock_status_store.read(
            sids=query.sids,
            start_date=query.start,
            end_date=query.end,
        )

        if status_df.is_empty():
            return df

        # 关联状态信息
        return df.join(
            status_df,
            on=["sid", "trade_date"],
            how="left",
        )
```

**步骤 2: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/market/market_query_service.py
git commit -m "feat(datahub): implement MarketQueryService"
```

---

## 任务 8: 更新 DataHub 集成

**文件:**
- 修改: `packages/datahub/src/ditto_datahub/hub.py`
- 修改: `packages/datahub/src/ditto_datahub/init_providers.py`

**步骤 1: 更新 DataHub**

```python
# packages/datahub/src/ditto_datahub/hub.py

from ditto_datahub.domains.market import MarketQueryService

class DataHub:
    def __init__(
        self,
        # ... 其他依赖 ...
        market_query_service: MarketQueryService,  # 替换 bars
        # ... 其他依赖 ...
    ) -> None:
        # ... 其他初始化 ...

        self.market = market_query_service

        # 保留向后兼容的别名
        self.bars = market_query_service
```

**步骤 2: 更新 Provider**

```python
# packages/datahub/src/ditto_datahub/init_providers.py

from ditto_datahub.domains.market import MarketQueryService
from ditto_datahub.domains.market.stock.bars.bars_store import StockBarsStore
# ... 导入其他 Market Store ...

class DataHubProvider(Provider):
    # ... 其他提供者 ...

    @staticmethod
    @provide
    def stock_bars_store(config: DataRootConfig) -> StockBarsStore:
        """提供 StockBarsStore."""
        return StockBarsStore(config.data_root)

    # ... 提供其他 Market Store ...

    @staticmethod
    @provide
    def market_query_service(
        stock_bars_store: StockBarsStore,
        # ... 其他 Market Store ...
    ) -> MarketQueryService:
        """提供 MarketQueryService."""
        return MarketQueryService(
            stock_bars_store=stock_bars_store,
            # ... 其他参数 ...
        )
```

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/hub.py
git add packages/datahub/src/ditto_datahub/init_providers.py
git commit -m "refactor(datahub): integrate MarketQueryService into DataHub"
```

---

## 任务 9: 清理和文档更新

**文件:**
- 删除: `packages/datahub/src/ditto_datahub/accessors/bars_accessor.py`
- 修改: `packages/datahub/README.md`

**步骤 1: 删除旧 Accessor**

```bash
git rm packages/datahub/src/ditto_datahub/accessors/bars_accessor.py
```

**步骤 2: 提交**

```bash
git add packages/datahub/src/ditto_datahub/accessors/
git add packages/datahub/README.md
git commit -m "refactor(datahub): remove BarsAccessor and update documentation"
```

---

## 任务 10: 创建 Git Tag

**步骤 1: 确保所有测试通过**

```bash
pixi run -e dev ci
```

**步骤 2: 创建 Tag**

```bash
git tag -a datahub-phase2-market-complete -m "完成 Market 域重构：domains/market/ 结构完整"
git push origin datahub-phase2-market-complete
```

---

## 验收标准

### 功能验收

- [ ] domains/market/ 目录结构完整
- [ ] Stock 相关 Store 成功迁移
- [ ] ETF 相关 Store 实现完整
- [ ] Index 相关 Store 实现完整
- [ ] MarketQueryService 实现所有查询接口
- [ ] DataHub 集成 MarketQueryService 完成
- [ ] 旧的 BarsAccessor 成功删除

### 测试验收

- [ ] 新增测试覆盖率 ≥ 80%
- [ ] 所有现有测试通过

### 代码质量

- [ ] Pyright 类型检查通过 (strict)
- [ ] Ruff 代码检查通过

---

## 依赖关系

### 前置依赖

- Phase 0: 基础层重构
- Phase 1: Metadata 域重构

### 后续依赖

- Phase 3: Capital 域重构

---

## 预计时间

- 任务 1: 0.5 天
- 任务 2-4: 2 天 (Stock 迁移)
- 任务 5: 1.5 天 (ETF 实现)
- 任务 6: 1 天 (Index 实现)
- 任务 7-8: 2 天 (QueryService + 集成)
- 任务 9-10: 1 天

**总计: 约 8 个工作日**
