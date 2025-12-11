# Phase 0 Data Access Layer Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor data access layer with DataReader/DataWriter architecture, removing DataService and adding proper business semantics interfaces.

**Architecture:** Clear separation between business logic (DataReader/DataWriter) and technical adapters. Maintain backward compatibility with existing validators and collectors.

**Tech Stack:** Python 3.11, Polars, Pydantic, DuckDB, SQLite, pytest

---

## Task 1: Implement DataReader Service

**Files:**
- Create: `packages/core/src/ditto_core/data/services/data_reader.py`
- Test: `packages/core/tests/unit/data/services/test_data_reader.py`

**Step 1: Write failing tests**

```python
def test_data_reader_get_etf_list(mocker):
    """Test getting ETF list from database."""
    # Arrange
    mock_adapter = mocker.Mock()
    mock_adapter.fetch_df.return_value = test_etf_list

    reader = DataReader(mock_adapter)

    # Act
    result = reader.get_etf_list()

    # Assert
    assert len(result) == 3
    assert "510300.SH" in result["symbol"].to_list()

def test_data_reader_get_daily_data(mocker):
    """Test getting daily price data for a symbol."""
    # Arrange
    mock_adapter = mocker.Mock()
    mock_adapter.fetch_df.return_value = test_daily_data

    reader = DataReader(mock_adapter)

    # Act
    result = reader.get_daily_data("510300.SH", "2024-01-01", "2024-01-05")

    # Assert
    assert len(result) == 5
    assert result["date"].min() == "2024-01-02"
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/core/tests/unit/data/services/test_data_reader.py::test_data_reader_get_etf_list -v`
Expected: FAIL with "DataReader not defined"

**Step 3: Implement DataReader class**

```python
# packages/core/src/ditto_core/data/services/data_reader.py
from typing import Optional
import polars as pl
from loguru import logger

class DataReader:
    """数据读取服务 - 提供业务语义的数据访问接口."""

    def __init__(self, adapter) -> None:
        """初始化数据读取器。

        Args:
            adapter: 数据库适配器实例
        """
        self._adapter = adapter

    def get_etf_list(self) -> pl.DataFrame:
        """获取ETF列表。

        Returns:
            DataFrame with columns: [symbol, name, list_date, ...]
        """
        try:
            sql = "SELECT symbol, name, list_date, knowledge_date FROM etf_info ORDER BY symbol"
            return self._adapter.fetch_df(sql)
        except Exception as e:
            logger.error(f"获取ETF列表失败: {e}")
            raise

    def get_daily_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjusted: bool = True
    ) -> pl.DataFrame:
        """获取日线数据。

        Args:
            symbol: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            adjusted: 是否返回复权后数据

        Returns:
            DataFrame with daily OHLCV data
        """
        try:
            if adjusted:
                # 使用复权后数据
                sql = """
                SELECT date, open, high, low, close, volume, knowledge_date
                FROM daily_price_adjusted
                WHERE symbol = ? AND date >= ? AND date <= ?
                ORDER BY date
                """
            else:
                # 使用原始数据
                sql = """
                SELECT date, open, high, low, close, volume, knowledge_date
                FROM daily_price_raw
                WHERE symbol = ? AND date >= ? AND date <= ?
                ORDER BY date
                """

            return self._adapter.fetch_df(
                sql,
                {"symbol": symbol, "start_date": start_date, "end_date": end_date}
            )
        except Exception as e:
            logger.error(f"获取日线数据失败 - {symbol}: {e}")
            raise

    def get_adjustment_factors(self, symbol: str) -> pl.DataFrame:
        """获取复权因子。

        Returns:
            DataFrame with adjustment factors
        """
        try:
            sql = """
            SELECT ex_date, adj_factor, knowledge_date
            FROM adjustment_factors
            WHERE symbol = ?
            ORDER BY ex_date
            """
            return self._adapter.fetch_df(sql, {"symbol": symbol})
        except Exception as e:
            logger.error(f"获取复权因子失败 - {symbol}: {e}")
            raise

    def get_trading_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        """获取交易日历。

        Returns:
            DataFrame with trading days
        """
        try:
            sql = """
            SELECT date, is_trading_day, knowledge_date
            FROM trading_calendar
            WHERE date >= ? AND date <= ?
            ORDER BY date
            """
            return self._adapter.fetch_df(
                sql, {"start_date": start_date, "end_date": end_date}
            )
        except Exception as e:
            logger.error(f"获取交易日历失败: {e}")
            raise
```

**Step 4: Run test to verify it passes**

Run: `pytest packages/core/tests/unit/data/services/test_data_reader.py::test_data_reader_get_etf_list -v`
Expected: PASS

**Step 5: Add more tests and implement**

Add tests for edge cases, error handling, and other methods.

**Step 6: Commit**

```bash
git add packages/core/src/ditto_core/data/services/data_reader.py packages/core/tests/unit/data/services/test_data_reader.py
git commit -m "feat(data): implement DataReader service with business semantic interfaces"
```

---

## Task 2: Implement DataWriter Service

**Files:**
- Create: `packages/core/src/ditto_core/data/services/data_writer.py`
- Test: `packages/core/tests/unit/data/services/test_data_writer.py`

**Step 1: Write failing tests**

```python
def test_data_writer_store_etf_info(mocker):
    """Test storing ETF info to database."""
    # Arrange
    mock_adapter = mocker.Mock()
    mock_adapter.execute.return_value = None

    writer = DataWriter(mock_adapter)
    etf_data = pl.DataFrame({
        "symbol": ["510300.SH"],
        "name": ["沪深300ETF"]
    })

    # Act & Assert
    writer.store_etf_info(etf_data)  # Should not raise

    # Verify SQL was executed
    mock_adapter.execute.assert_called_once()

def test_data_writer_store_daily_data(mocker):
    """Test storing daily price data."""
    # Arrange
    mock_adapter = mocker.Mock()
    mock_adapter.execute.return_value = None

    writer = DataWriter(mock_adapter)
    daily_data = test_daily_data

    # Act & Assert
    writer.store_daily_data(daily_data)  # Should not raise

    # Verify correct SQL pattern
    call_args = mock_adapter.execute.call_args[0][0]
    assert "INSERT INTO daily_price_raw" in call_args[0]
```

**Step 2: Run tests to verify they fail**

**Step 3: Implement DataWriter class**

```python
# packages/core/src/ditto_core/data/services/data_writer.py
from typing import Optional
import polars as pl
from loguru import logger
from datetime import datetime

class DataWriter:
    """数据写入服务 - 提供业务语义的数据存储接口."""

    def __init__(self, adapter) -> None:
        """初始化数据写入器。

        Args:
            adapter: 数据库适配器实例
        """
        self._adapter = adapter

    def store_etf_info(self, etf_data: pl.DataFrame) -> None:
        """存储ETF基础信息。

        Args:
            etf_data: 包含ETF信息的DataFrame
        """
        try:
            # 添加knowledge_date
            if "knowledge_date" not in etf_data.columns:
                etf_data = etf_data.with_columns([
                    pl.lit(datetime.now()).alias("knowledge_date")
                ])

            # 批量插入或更新
            for row in etf_data.to_dicts():
                sql = """
                INSERT OR REPLACE INTO etf_info
                (symbol, name, list_date, knowledge_date)
                VALUES (?, ?, ?, ?)
                """
                self._adapter.execute(sql, row)

            logger.info(f"存储ETF信息: {len(etf_data)} 条记录")
        except Exception as e:
            logger.error(f"存储ETF信息失败: {e}")
            raise

    def store_daily_data(self, daily_data: pl.DataFrame) -> None:
        """存储日线数据（原始价格）。

        Args:
            daily_data: 包含日线数据的DataFrame
        """
        try:
            # 确保数据格式正确
            required_cols = {"symbol", "date", "open", "high", "low", "close", "volume"}
            if not required_cols.issubset(daily_data.columns):
                missing = required_cols - set(daily_data.columns)
                raise ValueError(f"缺少必需列: {missing}")

            # 添加knowledge_date
            if "knowledge_date" not in daily_data.columns:
                daily_data = daily_data.with_columns([
                    pl.lit(datetime.now()).alias("knowledge_date")
                ])

            # 批量存储
            self._batch_insert("daily_price_raw", daily_data)
            logger.info(f"存储日线数据: {len(daily_data)} 条记录")
        except Exception as e:
            logger.error(f"存储日线数据失败: {e}")
            raise

    def store_adjustment_factors(self, adj_data: pl.DataFrame) -> None:
        """存储复权因子。

        Args:
            adj_data: 包含复权因子的DataFrame
        """
        try:
            # 添加knowledge_date
            if "knowledge_date" not in adj_data.columns:
                adj_data = adj_data.with_columns([
                    pl.lit(datetime.now()).alias("knowledge_date")
                ])

            # 批量存储
            self._batch_insert("adjustment_factors", adj_data)
            logger.info(f"存储复权因子: {len(adj_data)} 条记录")
        except Exception as e:
            logger.error(f"存储复权因子失败: {e}")
            raise

    def store_trading_calendar(self, calendar_data: pl.DataFrame) -> None:
        """存储交易日历。

        Args:
            calendar_data: 包含交易日历的DataFrame
        """
        try:
            self._batch_insert("trading_calendar", calendar_data)
            logger.info(f"存储交易日历: {len(calendar_data)} 条记录")
        except Exception as e:
            logger.error(f"存储交易日历失败: {e}")
            raise

    def _batch_insert(self, table_name: str, data: pl.DataFrame) -> None:
        """批量插入数据的内部方法。

        This method handles both INSERT and UPDATE logic for data that
        might already exist in the database.
        """
        # 对于不同的表，使用不同的批量插入策略
        if table_name in ["daily_price_raw", "adjustment_factors"]:
            # 这些表可能需要更新已有记录
            for row in data.to_dicts():
                self._adapter.execute(f"""
                INSERT OR REPLACE INTO {table_name}
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, row)
        else:
            # 其他表直接插入
            self._adapter.execute_many(f"""
                INSERT OR IGNORE INTO {table_name}
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, data.to_dicts())
```

**Step 4: Run tests and implement error handling**

**Step 5: Commit**

```bash
git add packages/core/src/ditto_core/data/services/data_writer.py packages/core/tests/unit/data/services/test_data_writer.py
git commit -m "feat(data): implement DataWriter service with batch storage capabilities"
```

---

## Task 3: Enhance Database Adapters

**Files:**
- Modify: `packages/core/src/ditto_core/data/adapters/duckdb_adapter.py`
- Modify: `packages/core/src/ditto_core/data/adapters/sqlite_adapter.py`
- Test: Update existing tests

**Step 1: Add missing methods to DuckDBAdapter**

```python
# Add to DuckDBAdapter class
def fetch_df(self, sql: str, params: Optional[dict] = None) -> pl.DataFrame:
    """执行SQL查询并返回DataFrame。

    Args:
        sql: SQL查询语句
        params: 查询参数字典

    Returns:
        查询结果的DataFrame
    """
    try:
        if params:
            return self._conn.execute(sql, params).pl()
        else:
            return self._conn.execute(sql).pl()
    except Exception as e:
        logger.error(f"查询失败: {sql}, 错误: {e}")
        raise

def execute_many(self, sql: str, data: list[dict]) -> None:
    """批量执行SQL语句。

    Args:
        sql: SQL语句模板
        data: 参数字典列表
    """
    try:
        self._conn.executemany(sql, data)
    except Exception as e:
        logger.error(f"批量执行失败: {sql}, 错误: {e}")
        raise
```

**Step 2: Add similar methods to SQLiteAdapter**

**Step 3: Update existing tests**

**Step 4: Commit**

```bash
git add packages/core/src/ditto_core/data/adapters/duckdb_adapter.py packages/core/src/ditto_core/data/adapters/sqlite_adapter.py
git commit -m "feat(data): enhance adapters with fetch_df and execute_many methods"
```

---

## Task 4: Update DataCollector to Use DataWriter

**Files:**
- Modify: `packages/core/src/ditto_core/data/collector.py`
- Test: Update existing tests

**Step 1: Refactor DataCollector initialization**

```python
# Change DataCollector to use DataWriter instead of DataService
def __init__(
    self,
    duckdb_adapter: Optional[DuckDBAdapter] = None,
    sqlite_adapter: Optional[SQLiteAdapter] = None,
    data_sources: Optional[dict] = None
) -> None:
    """初始化数据采集器。

    Args:
        duckdb_adapter: DuckDB适配器（用于存储）
        sqlite_adapter: SQLite适配器（用于交易数据）
        data_sources: 数据源配置字典
    """
    # 数据写入器
    self.writer = DataWriter(duckdb_adapter)

    # 数据源
    self._sources = data_sources or {}

    # 初始化数据源
    self._initialize_sources()
```

**Step 2: Update methods to use DataWriter**

```python
# Change store_etf_info method
def update_etf_list(self) -> dict[str, Any]:
    """更新ETF列表，从主数据源获取并存储"""
    logger.info("开始更新ETF列表")

    # 获取主数据源
    primary_source = self._sources.get("tushare")
    if not primary_source:
        raise ValueError("未配置主数据源 Tushare")

    try:
        # 获取ETF列表
        etf_df = primary_source.get_etf_list()
        logger.info(f"获取到 {len(etf_df)} 只ETF")

        # 存储到数据库
        self.writer.store_etf_info(etf_df)

        return {
            "total_updated": len(etf_df),
            "source": "tushare",
            "status": "success"
        }
    except Exception as e:
        logger.error(f"更新ETF列表失败: {e}")
        raise

# Similar changes for update_daily_data method
```

**Step 3: Update tests**

**Step 4: Commit**

```bash
git add packages/core/src/ditto_core/data/collector.py
git commit -m "refactor(data): update DataCollector to use DataWriter service"
```

---

## Task 5: Create Configuration Management

**Files:**
- Create: `packages/core/src/ditto_core/config/sources.yaml`
- Modify: `packages/core/src/ditto_core/data/collector.py`
- Test: `packages/core/tests/unit/data/config/test_sources_config.py`

**Step 1: Create sources configuration file**

```yaml
# packages/core/src/ditto_core/config/sources.yaml
# 数据源配置文件

sources:
  tushare:
    token: "${TUSHARE_TOKEN}"
    rate_limit: 0.2  # 秒
    timeout: 30  # 秒
    retry_count: 3
    retry_delay: 1  # 秒

  akshare:
    rate_limit: 0.5  # 秒
    timeout: 30  # 秒
    retry_count: 2
    retry_delay: 2  # 秒

# CSV数据源（用于测试）
csv_sources:
  etf_list:
    path: "data/test/etf_list.csv"
  daily_data:
    path: "data/test/daily_data/{symbol}.csv"
```

**Step 2: Implement configuration loading**

```python
# Add to DataCollector
def _initialize_sources(self) -> None:
    """从配置文件初始化数据源"""
    import yaml
    from pathlib import Path

    # 加载配置
    config_path = Path(__file__).parent.parent.parent / "config" / "sources.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    else:
        logger.warning("数据源配置文件不存在，使用默认配置")
        config = {"sources": {}}

    # 初始化数据源
    for name, source_config in config.get("sources", {}).items():
        try:
            if name == "tushare":
                from .datasources.tushare import TushareDataSource
                source = TushareDataSource(source_config)
            elif name == "akshare":
                from .datasources.akshare import AkShareDataSource
                source = AkShareDataSource(source_config)
            else:
                logger.warning(f"未知数据源: {name}")
                continue

            self._sources[name] = source
            logger.info(f"数据源 {name} 初始化成功")
        except Exception as e:
            logger.error(f"数据源 {name} 初始化失败: {e}")
```

**Step 3: Create test configuration**

**Step 4: Commit**

```bash
git add packages/core/src/ditto_core/config/sources.yaml packages/core/src/ditto_core/data/collector.py
git commit -m "feat(config): add data sources configuration management"
```

---

## Task 6: Create CSV Data Source for Testing

**Files:**
- Create: `packages/core/src/ditto_core/data/datasources/csv_source.py`
- Test: `packages/core/tests/unit/data/datasources/test_csv_source.py`
- Create: `data/test/etf_list.csv` sample file

**Step 1: Write failing tests**

**Step 2: Implement CSV data source**

```python
# packages/core/src/ditto_core/data/datasources/csv_source.py
from typing import Dict, Any, Optional
import polars as pl
from pathlib import Path
from loguru import logger
from .base import DataSource

class CSVDataSource(DataSource):
    """CSV数据源 - 用于测试和演示。"""

    def __init__(self, config: Dict[str, Any]) -> None:
        """初始化CSV数据源。

        Args:
            config: 配置字典，包含path等参数
        """
        self.base_path = Path(config.get("path", "data/test"))
        self.supported_symbols = [
            "510300.SH", "516010.SH", "513100.SH", "000300.SH"
        ]

    def connect(self) -> bool:
        """连接数据源（CSV始终可用）。"""
        return True

    def disconnect(self) -> None:
        """断开连接（CSV无需操作）。"""
        pass

    def get_etf_list(self) -> pl.DataFrame:
        """获取ETF列表。

        Returns:
            模拟的ETF列表DataFrame
        """
        data = {
            "symbol": self.supported_symbols,
            "name": [
                "沪深300ETF",
                "游戏ETF",
                "纳指ETF",
                "沪深300指数"
            ],
            "list_date": ["2022-01-01"] * 4,
            "type": ["ETF", "ETF", "ETF", "INDEX"]
        }
        return pl.DataFrame(data)

    def get_daily_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> pl.DataFrame:
        """获取日线数据。

        生成模拟的日线数据，包含一些价格变化。
        """
        import numpy as np
        from datetime import datetime, timedelta

        if symbol not in self.supported_symbols:
            logger.warning(f"不支持的标的: {symbol}")
            return pl.DataFrame()

        # 生成日期范围
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        dates = []
        current = start
        while current <= end:
            # 跳过周末
            if current.weekday() < 5:
                dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        # 生成随机价格数据
        np.random.seed(42)  # 固定种子确保可复现
        n = len(dates)

        # 不同标的有不同的价格特征
        base_prices = {
            "510300.SH": 3.5,
            "516010.SH": 1.2,
            "513100.SH": 2.8,
            "000300.SH": 4000
        }

        base_price = base_prices[symbol]
        returns = np.random.normal(0.001, 0.02, n)  # 日收益率
        prices = [base_price]

        for i in range(1, n):
            price = prices[-1] * (1 + returns[i-1])
            prices.append(round(price, 3))

        # 生成OHLC数据
        data = []
        for i, date in enumerate(dates):
            if i == 0:
                # 第一天使用前一日收盘价作为开盘价
                open_price = base_price
                close_price = prices[i]
            else:
                open_price = prices[i-1]
                close_price = prices[i]

            high = max(open_price, close_price) * np.random.uniform(1.0, 1.03)
            low = min(open_price, close_price) * np.random.uniform(0.97, 1.0)
            volume = int(np.random.uniform(1000000, 50000000))

            data.append({
                "symbol": symbol,
                "date": date,
                "open": round(open_price, 3),
                "high": round(high, 3),
                "low": round(low, 3),
                "close": round(close_price, 3),
                "volume": volume
            })

        return pl.DataFrame(data)

    @property
    def source_type(self) -> str:
        """返回数据源类型。"""
        return "csv"
```

**Step 3: Create sample CSV files**

**Step 4: Commit**

```bash
git add packages/core/src/ditto_core/data/datasources/csv_source.py
git add packages/core/tests/unit/data/datasources/test_csv_source.py
git add -A data/test/
git commit -m "feat(data): implement CSV data source for testing and demo"
```

---

## Task 7: Update Scripts to Use New Architecture

**Files:**
- Modify: `scripts/update_data.py`
- Modify: `scripts/init_golden_dataset.py`
- Create: `scripts/test_data_flow.py`

**Step 1: Update update_data.py**

```python
#!/usr/bin/env python3
"""
数据更新脚本 - 使用新架构的版本
"""

from pathlib import Path
from ditto_foundation.config import get_settings
from ditto_core.data.services.data_reader import DataReader
from ditto_core.data.services.data_writer import DataWriter
from ditto_core.data.collector import DataCollector

def update_market_data():
    """更新市场数据"""
    print("开始更新市场数据...")

    settings = get_settings()

    # 初始化数据写入器和读取器
    with DataWriter(settings.analytics_adapter) as writer, \
         DataReader(settings.analytics_adapter) as reader:

        # 初始化数据采集器
        collector = DataCollector(
            duckdb_adapter=settings.analytics_adapter,
            data_sources=load_sources_config()
        )

        # 1. 更新ETF列表
        print("1. 更新ETF列表...")
        etf_result = collector.update_etf_list()
        print(f"   ✅ ETF列表更新完成: {etf_result['total_updated']} 只")

        # 2. 获取所有ETF代码
        etf_list = reader.get_etf_list()
        if len(etf_list) == 0:
            print("   ❌ 没有ETF数据，请先运行初始化")
            return

        symbols = etf_list["symbol"].to_list()[:5]  # 限制数量用于测试

        # 3. 更新日线数据（最近5个交易日）
        from datetime import datetime, timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        print(f"2. 更新日线数据: {len(symbols)} 只ETF...")
        daily_result = collector.update_daily_data(
            symbols=symbols,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            validate=True
        )

        print(f"   ✅ 日线数据更新完成:")
        print(f"     - 总记录数: {daily_result['total_records']}")
        print(f"     - 更新成功: {len(daily_result['symbols_updated'])} 只")
        if daily_result['validation_errors']:
            print(f"     - 验证错误: {len(daily_result['validation_errors'])} 个")

def load_sources_config():
    """加载数据源配置"""
    import yaml
    from pathlib import Path

    # 尝试多个配置位置
    config_paths = [
        Path("sources.yaml"),
        Path("config/sources.yaml"),
        Path(__file__).parent.parent / "config" / "sources.yaml"
    ]

    for config_path in config_paths:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("sources", {})

    # 返回空配置
    return {}

if __name__ == "__main__":
    update_market_data()
```

**Step 2: Update other scripts**

**Step 3: Commit**

```bash
git add scripts/update_data.py scripts/init_golden_dataset.py
git add scripts/test_data_flow.py
git commit -m "feat(scripts): update scripts to use new DataReader/DataWriter architecture"
```

---

## Task 8: Cleanup and Deprecate DataService

**Files:**
- Modify: All files that import DataService
- Add deprecation notice to DataService
- Run full test suite

**Step 1: Update imports**

**Step 2: Add deprecation notice**

**Step 3: Run tests and fix issues**

```bash
pytest --tb=short
```

**Step 4: Final commit**

```bash
git add .
git commit -m "refactor: complete DataReader/DataWriter architecture migration

- Implement DataReader and DataWriter services
- Enhance database adapters with new methods
- Add CSV data source for testing
- Update all scripts to use new architecture
- Deprecate DataService in favor of separated services
- All tests passing"
```

---

## Execution Complete!

This plan implements the complete DataReader/DataWriter architecture as designed, maintaining compatibility with existing components while providing clearer separation of concerns. The CSV data source enables testing without requiring real API tokens.

**Plan complete and saved to `docs/plans/2025-12-11-phase0-data-access-layer-refactoring.md`. Two execution options:**

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
