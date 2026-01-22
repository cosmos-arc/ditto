# TushareSource 组合模式重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 将 `TushareSource` 重构为组合模式，按数据类型拆分为多个专门的 Source 类，提高可维护性。

**架构:** 使用组合模式（Composition Pattern），将原本的单体 `TushareSource` 拆分为：
- `CalendarTushareAdapter` - 处理交易日历
- `StockTushareAdapter` - 处理股票相关数据
- `ETFTushareAdapter` - 处理 ETF 相关数据
- `TushareSource` - 入口类，组合上述专门类

**技术栈:** Python 3.12+, Polars, Pytest, 项目现有测试框架

---

## 前置检查

### Task 0: 环境验证

**目的:** 确保当前分支和环境正确

**步骤 1: 检查当前分支**

```bash
git branch --show-current
```

期望输出: `feature/dishka-migration`

**步骤 2: 运行基线测试**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_source_unit.py -v
```

期望输出: 所有测试通过

**步骤 3: 检查类型**

```bash
pixi run -e dev type packages/datahub/src/ditto_datahub/sources/tushare/tushare_source.py
```

期望输出: 0 errors

---

## 阶段 1: 创建基础 Source 类

### Task 1: 创建 _BaseTushareSource 抽象基类

**目的:** 提取共享逻辑，为专门 Source 类提供基础

**文件:**
- Create: `packages/datahub/src/ditto_datahub/sources/tushare/_base.py`

**步骤 1: 创建基类文件**

```python
"""Tushare source base class."""

from __future__ import annotations

from ditto_foundation import logger
from ditto_datahub.sources.tushare.client import TushareClient


class _BaseTushareSource:
    """
    Tushare source base class.

    Provides shared client initialization for all specialized Tushare sources.

    Attributes:
        _client: Tushare API client.

    """

    def __init__(self, token: str | None = None) -> None:
        """
        Initialize Tushare source.

        Args:
            token: API token. Reads from keyring or ~/.ditto/secrets.toml if None.

        """
        self._client = TushareClient(token=token)
        logger.debug(
            f"{self.__class__.__name__} initialized",
            event="tushare_source_init",
        )
```

**步骤 2: 验证类型检查**

```bash
pixi run -e dev type packages/datahub/src/ditto_datahub/sources/tushare/_base.py
```

期望输出: 0 errors

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/_base.py
git commit -m "feat(tushare): add _BaseTushareSource base class"
```

---

## 阶段 2: 创建专门 Source 类

### Task 2: 创建 CalendarTushareAdapter

**目的:** 处理交易日历数据

**文件:**
- Create: `packages/datahub/src/ditto_datahub/sources/tushare/calendar_source.py`

**步骤 1: 创建 CalendarTushareAdapter 类**

```python
"""Tushare calendar source."""

from __future__ import annotations

import polars as pl
from ditto_foundation import traced, logger

from ditto_datahub.sources.tushare._base import _BaseTushareSource
from ditto_datahub.sources.tushare.error_handler import tushare_fetch_error_handler
from ditto_datahub.sources.tushare.transformer import (
    CALENDAR_MAPPING,
    TushareDataTransformer,
)


class CalendarTushareAdapter(_BaseTushareSource):
    """
    Tushare trading calendar source.

    Fetches trading calendar data from Tushare API.

    """

    @traced("source.tushare.fetch_calendar")
    def fetch_calendar(
        self,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch trading calendar.

        Args:
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - trade_date: Date
            - is_open: Boolean

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare calendar",
            event="tushare_calendar_fetch_start",
            start_date=start_date,
            end_date=end_date,
        )

        with tushare_fetch_error_handler("calendar", "trade_cal"):
            response = self._client.query(
                api_name="trade_cal",
                exchange="SSE",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                fields="cal_date,is_open",
            )

            return TushareDataTransformer.transform(
                response, "calendar", CALENDAR_MAPPING
            )
```

**步骤 2: 验证类型检查**

```bash
pixi run -e dev type packages/datahub/src/ditto_datahub/sources/tushare/calendar_source.py
```

期望输出: 0 errors

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/calendar_source.py
git commit -m "feat(tushare): add CalendarTushareAdapter for calendar data"
```

---

### Task 3: 创建 StockTushareAdapter

**目的:** 处理股票相关数据

**文件:**
- Create: `packages/datahub/src/ditto_datahub/sources/tushare/stock_source.py`

**步骤 1: 创建 StockTushareAdapter 类**

```python
"""Tushare stock source."""

from __future__ import annotations

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.sources.tushare._base import _BaseTushareSource
from ditto_datahub.sources.tushare.error_handler import tushare_fetch_error_handler
from ditto_datahub.sources.tushare.status_merger import StockStatusMerger
from ditto_datahub.sources.tushare.transformer import (
    ADJ_FACTOR_MAPPING,
    STOCK_BASIC_MAPPING,
    STOCK_LIMIT_MAPPING,
    TushareDataTransformer,
)


def _record_metrics(row_count: int, dataset: str) -> None:
    """
    安全地记录数据指标。

    如果 observability 未初始化，静默跳过。

    Args:
        row_count: 数据行数
        dataset: 数据集名称

    """
    try:
        M.data_records.add(
            row_count,
            {"source": "tushare", "dataset": dataset, "status": "success"},
        )
    except (AttributeError, TypeError):
        # Observability 未初始化，静默跳过
        pass


class StockTushareAdapter(_BaseTushareSource):
    """
    Tushare stock data source.

    Fetches stock-related data from Tushare API including:
    - Basic information
    - Daily OHLCV bars
    - Adjustment factors
    - Limit prices
    - Stock status

    """

    @traced("source.tushare.fetch_stock_basic")
    def fetch_stock_basic(self) -> pl.DataFrame:
        """
        Fetch stock basic information.

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
            - symbol: Display symbol (e.g., "000001")
            - name: Stock name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare stock basic info",
            event="tushare_stock_basic_fetch_start",
        )

        with tushare_fetch_error_handler("stock_basic", "stock_basic"):
            response = self._client.query(
                api_name="stock_basic",
                list_status="L",
                fields="ts_code,symbol,name,exchange,list_date",
            )

            return TushareDataTransformer.transform(
                response, "stock_basic", STOCK_BASIC_MAPPING
            )

    @traced("source.tushare.fetch_stock_daily")
    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock daily OHLCV bars.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns (same as ETF daily schema):
            - src_code: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        logger.info(
            "Fetching Tushare stock daily",
            event="tushare_stock_daily_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("stock_daily", "daily"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="daily",
                trade_date=ts_date,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
            )

            return TushareDataTransformer.transform_daily_ohlcv(
                response,
                "stock_daily",
            )

    @traced("source.tushare.fetch_adj_factor")
    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock adjustment factors.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code
            - trade_date: Date
            - knowledge_date: Date (PIT safety: when this data became known)
            - adj_factor: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare adj factors",
            event="tushare_adj_factor_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("adj_factor", "adj_factor"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="adj_factor",
                fields="ts_code,trade_date,adj_factor",
                trade_date=ts_date,
            )

            return TushareDataTransformer.transform(
                response, "adj_factor", ADJ_FACTOR_MAPPING
            )

    @traced("source.tushare.fetch_stock_limit")
    def fetch_stock_limit(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock limit up/down prices (B.3).

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
            - trade_date: Date
            - up_limit: Float64 (涨停价)
            - down_limit: Float64 (跌停价)

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare stock limit prices",
            event="tushare_stock_limit_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("stock_limit", "stk_limit"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="stk_limit",
                trade_date=ts_date,
                fields="ts_code,trade_date,up_limit,down_limit",
            )

            return TushareDataTransformer.transform(
                response, "stock_limit", STOCK_LIMIT_MAPPING
            )

    @traced("source.tushare.fetch_stock_status")
    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock status information (B.3).

        Combines data from multiple Tushare APIs:
        - suspend_d: 停牌信息
        - stock_st: ST状态
        - stock_basic: list_status

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
            - trade_date: Date
            - is_suspended: Boolean
            - suspend_timing: Utf8 (e.g., "09:30-10:00" or null)
            - is_st: Boolean
            - st_type: Utf8 (e.g., "ST" or null)
            - list_status: Utf8 (L=正常, D=退市, P=暂停)

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare stock status",
            event="tushare_stock_status_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("stock_status", "stock_status"):
            ts_date = trade_date.replace("-", "")

            # 使用 StockStatusMerger 获取并合并状态数据
            merger = StockStatusMerger(self._client)

            # 1. Fetch suspension data from suspend_d API
            suspend_df = merger.fetch_suspend_data(ts_date)

            # 2. Fetch ST status from stock_st API
            st_df = merger.fetch_st_data()

            # 3. Fetch list_status from stock_basic API
            list_status_df = merger.fetch_list_status_data()

            # 4. Merge all data sources
            result = merger.merge_status_data(
                list_status_df, suspend_df, st_df, trade_date
            )

            row_count = len(result)
            logger.info(
                "Tushare stock status fetched",
                event="tushare_stock_status_fetch_complete",
                row_count=row_count,
            )
            _record_metrics(row_count, "stock_status")

            return result
```

**步骤 2: 验证类型检查**

```bash
pixi run -e dev type packages/datahub/src/ditto_datahub/sources/tushare/stock_source.py
```

期望输出: 0 errors

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/stock_source.py
git commit -m "feat(tushare): add StockTushareAdapter for stock data"
```

---

### Task 4: 创建 ETFTushareAdapter

**目的:** 处理 ETF 相关数据

**文件:**
- Create: `packages/datahub/src/ditto_datahub/sources/tushare/etf_source.py`

**步骤 1: 创建 ETFTushareAdapter 类**

```python
"""Tushare ETF source."""

from __future__ import annotations

import polars as pl
from ditto_foundation import traced, logger

from ditto_datahub.sources.tushare._base import _BaseTushareSource
from ditto_datahub.sources.tushare.error_handler import tushare_fetch_error_handler
from ditto_datahub.sources.tushare.transformer import (
    ETF_BASIC_MAPPING,
    FUND_ADJ_MAPPING,
    TushareDataTransformer,
)


class ETFTushareAdapter(_BaseTushareSource):
    """
    Tushare ETF data source.

    Fetches ETF-related data from Tushare API including:
    - Basic information
    - Daily OHLCV bars
    - Adjustment factors

    """

    @traced("source.tushare.fetch_etf_basic")
    def fetch_etf_basic(self) -> pl.DataFrame:
        """
        Fetch ETF basic information.

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "510300.SH")
            - symbol: Display symbol (e.g., "510300")
            - name: ETF name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare ETF basic info",
            event="tushare_etf_basic_fetch_start",
        )

        with tushare_fetch_error_handler("etf_basic", "fund_basic"):
            response = self._client.query(
                api_name="fund_basic",  # ETF basic 使用 fund_basic API
                fields="ts_code,name,list_date",  # fund_basic 可能没有 exchange 字段
            )

            return TushareDataTransformer.transform(
                response, "etf_basic", ETF_BASIC_MAPPING
            )

    @traced("source.tushare.fetch_etf_daily")
    def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch ETF daily OHLCV bars.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns (matching ETF_DAILY_SCHEMA):
            - src_code: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        logger.info(
            "Fetching Tushare ETF daily",
            event="tushare_etf_daily_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("etf_daily", "fund_daily"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="fund_daily",
                ts_code="",
                trade_date=ts_date,
                fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg",
            )

            return TushareDataTransformer.transform_daily_ohlcv(
                response,
                "etf_daily",
            )

    @traced("source.tushare.fetch_fund_adj")
    def fetch_fund_adj(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch ETF/fund adjustment factors.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code
            - trade_date: Date
            - knowledge_date: Date (PIT safety: when this data became known)
            - adj_factor: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        logger.info(
            "Fetching Tushare fund adj factors",
            event="tushare_fund_adj_fetch_start",
            trade_date=trade_date,
        )

        with tushare_fetch_error_handler("fund_adj", "fund_adj"):
            ts_date = trade_date.replace("-", "")
            response = self._client.query(
                api_name="fund_adj",
                fields="ts_code,trade_date,adj_factor",
                trade_date=ts_date,
            )

            return TushareDataTransformer.transform(
                response, "fund_adj", FUND_ADJ_MAPPING
            )
```

**步骤 2: 验证类型检查**

```bash
pixi run -e dev type packages/datahub/src/ditto_datahub/sources/tushare/etf_source.py
```

期望输出: 0 errors

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/etf_source.py
git commit -m "feat(tushare): add ETFTushareAdapter for ETF data"
```

---

## 阶段 3: 更新 TushareSource 使用组合模式

### Task 5: 重构 TushareSource 为组合入口

**目的:** 更新 TushareSource 使用组合模式，保持向后兼容

**文件:**
- Modify: `packages/datahub/src/ditto_datahub/sources/tushare/tushare_source.py`

**步骤 1: 备份并读取当前实现**

```bash
# 查看当前文件行数
wc -l packages/datahub/src/ditto_datahub/sources/tushare/tushare_source.py
```

期望输出: 约 426 行

**步骤 2: 替换为组合模式实现**

删除所有现有内容，替换为：

```python
"""Tushare data source implementation."""

from __future__ import annotations

import polars as pl

from ditto_datahub.sources.base import DataSource
from ditto_datahub.sources.tushare._base import _BaseTushareSource
from ditto_datahub.sources.tushare.calendar_source import CalendarTushareAdapter
from ditto_datahub.sources.tushare.etf_source import ETFTushareAdapter
from ditto_datahub.sources.tushare.stock_source import StockTushareAdapter


class TushareSource(DataSource):
    """
    Tushare Pro data source.

    Fetches market data from Tushare API and transforms to Ditto schema.

    This class uses composition pattern to delegate specialized data fetching
    to dedicated source classes:
    - CalendarTushareAdapter: Trading calendar
    - StockTushareAdapter: Stock-related data
    - ETFTushareAdapter: ETF-related data

    Attributes:
        _calendar: Calendar data source.
        _stock: Stock data source.
        _etf: ETF data source.

    """

    def __init__(self, token: str | None = None) -> None:
        """
        Initialize Tushare source.

        Args:
            token: API token. Reads from keyring or ~/.ditto/secrets.toml if None.

        """
        # 组合专门的 Source 类
        self._calendar = CalendarTushareAdapter(token=token)
        self._stock = StockTushareAdapter(token=token)
        self._etf = ETFTushareAdapter(token=token)

    # Calendar 相关方法 - 委托给 CalendarTushareAdapter

    def fetch_calendar(
        self,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch trading calendar.

        Args:
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - trade_date: Date
            - is_open: Boolean

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._calendar.fetch_calendar(start_date, end_date)

    # Stock 相关方法 - 委托给 StockTushareAdapter

    def fetch_stock_basic(self) -> pl.DataFrame:
        """
        Fetch stock basic information.

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
            - symbol: Display symbol (e.g., "000001")
            - name: Stock name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._stock.fetch_stock_basic()

    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock daily OHLCV bars.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns (same as ETF daily schema):
            - src_code: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        return self._stock.fetch_stock_daily(trade_date)

    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock adjustment factors.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code
            - trade_date: Date
            - knowledge_date: Date (PIT safety: when this data became known)
            - adj_factor: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._stock.fetch_adj_factor(trade_date)

    def fetch_stock_limit(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock limit up/down prices (B.3).

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
            - trade_date: Date
            - up_limit: Float64 (涨停价)
            - down_limit: Float64 (跌停价)

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._stock.fetch_stock_limit(trade_date)

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock status information (B.3).

        Combines data from multiple Tushare APIs:
        - suspend_d: 停牌信息
        - stock_st: ST状态
        - stock_basic: list_status

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
            - trade_date: Date
            - is_suspended: Boolean
            - suspend_timing: Utf8 (e.g., "09:30-10:00" or null)
            - is_st: Boolean
            - st_type: Utf8 (e.g., "ST" or null)
            - list_status: Utf8 (L=正常, D=退市, P=暂停)

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._stock.fetch_stock_status(trade_date)

    # ETF 相关方法 - 委托给 ETFTushareAdapter

    def fetch_etf_basic(self) -> pl.DataFrame:
        """
        Fetch ETF basic information.

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "510300.SH")
            - symbol: Display symbol (e.g., "510300")
            - name: ETF name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._etf.fetch_etf_basic()

    def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch ETF daily OHLCV bars.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns (matching ETF_DAILY_SCHEMA):
            - src_code: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        return self._etf.fetch_etf_daily(trade_date)

    def fetch_fund_adj(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch ETF/fund adjustment factors.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code
            - trade_date: Date
            - knowledge_date: Date (PIT safety: when this data became known)
            - adj_factor: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        return self._etf.fetch_fund_adj(trade_date)
```

**步骤 3: 验证文件行数**

```bash
wc -l packages/datahub/src/ditto_datahub/sources/tushare/tushare_source.py
```

期望输出: < 250 行（从 426 行大幅减少）

**步骤 4: 验证类型检查**

```bash
pixi run -e dev type packages/datahub/src/ditto_datahub/sources/tushare/tushare_source.py
```

期望输出: 0 errors

**步骤 5: 提交**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/tushare_source.py
git commit -m "refactor(tushare): use composition pattern for TushareSource"
```

---

## 阶段 4: 更新模块导出

### Task 6: 更新 __init__.py 导出新类

**目的:** 确保新类可以被正确导入

**文件:**
- Modify: `packages/datahub/src/ditto_datahub/sources/tushare/__init__.py`

**步骤 1: 读取当前导出**

```bash
cat packages/datahub/src/ditto_datahub/sources/tushare/__init__.py
```

**步骤 2: 更新导出（如果需要）**

确保导出以下内容：
- `TushareSource` - 主入口类
- `CalendarTushareAdapter` - 可选：如果需要单独使用
- `StockTushareAdapter` - 可选：如果需要单独使用
- `ETFTushareAdapter` - 可选：如果需要单独使用

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/__init__.py
git commit -m "chore(tushare): update module exports"
```

---

## 阶段 5: 验证和测试

### Task 7: 运行所有单元测试

**目的:** 确保重构后所有测试通过

**步骤 1: 运行 Tushare 单元测试**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_source_unit.py -v
```

期望输出: 所有测试通过（保持向后兼容）

**步骤 2: 运行所有 Tushare 相关测试**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/ -v
```

期望输出: 所有测试通过

**步骤 3: 运行完整类型检查**

```bash
pixi run -e dev type
```

期望输出: 0 errors

**步骤 4: 运行代码质量检查**

```bash
pixi run -e dev lint
pixi run -e dev fmt --check
```

期望输出: All checks passed

**步骤 5: 提交（如果需要修复）**

```bash
git add -A
git commit -m "test(tushare): fix tests after composition pattern refactor"
```

---

## 阶段 6: 最终验证

### Task 8: 完整 CI 检查

**目的:** 确保所有质量标准通过

**步骤 1: 运行完整 CI**

```bash
pixi run -e dev ci
```

期望输出: 所有检查通过

**步骤 2: 检查文件行数**

```bash
# 检查主文件行数
wc -l packages/datahub/src/ditto_datahub/sources/tushare/tushare_source.py

# 检查所有新文件
wc -l packages/datahub/src/ditto_datahub/sources/tushare/_base.py
wc -l packages/datahub/src/ditto_datahub/sources/tushare/calendar_source.py
wc -l packages/datahub/src/ditto_datahub/sources/tushare/stock_source.py
wc -l packages/datahub/src/ditto_datahub/sources/tushare/etf_source.py
```

期望输出:
- `tushare_source.py` < 400 行
- 所有文件类型检查通过

**步骤 3: 验证向后兼容性**

确认以下公共接口保持不变：
- `TushareSource.fetch_calendar(start_date, end_date)`
- `TushareSource.fetch_etf_basic()`
- `TushareSource.fetch_etf_daily(trade_date)`
- `TushareSource.fetch_stock_basic()`
- `TushareSource.fetch_stock_daily(trade_date)`
- `TushareSource.fetch_adj_factor(trade_date)`
- `TushareSource.fetch_fund_adj(trade_date)`
- `TushareSource.fetch_stock_limit(trade_date)`
- `TushareSource.fetch_stock_status(trade_date)`

**步骤 4: 最终提交**

```bash
git status
```

确认所有更改已提交

---

## 验收标准

完成上述所有任务后：

- [x] `tushare_source.py` 文件行数 < 400
- [x] 所有单元测试通过
- [x] 类型检查通过（0 errors）
- [x] 代码质量检查通过（ruff, pyright）
- [x] 保持向后兼容，公共接口不变
- [x] 创建了 `_base.py`, `calendar_source.py`, `stock_source.py`, `etf_source.py`
- [x] 使用组合模式组合专门类

---

## 架构优势

重构后的架构具有以下优势：

1. **单一职责**: 每个类只负责一种数据类型
2. **可扩展性**: 添加新数据类型（如期货、债券）只需创建新的 Source 类
3. **可测试性**: 每个专门类可以独立测试
4. **可维护性**: 代码组织清晰，修改某类数据不影响其他类型
5. **向后兼容**: 公共接口保持不变，现有代码无需修改

---

## 执行说明

**Plan complete and saved to `docs/plans/2026-01-22-tushare-composition-pattern.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
