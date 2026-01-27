# DataHub 基础层重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 建立统一的数据存储接口（BaseStore）、简化配置系统（单 DATAROOT）、为后续域级重构打下基础

**架构:**
- 新建 `stores/base/` 目录，定义统一的 BaseStore 接口
- 实现 ParquetStore 和 SQLiteStore 两个基类
- 重构 `config/` 目录，从多路径配置简化为单 DATAROOT 配置
- 保持现有 Store 功能不变，通过继承新基类实现

**技术栈:** Python 3.12+, Polars, Pydantic Settings, Pyright Strict

---

## 任务 1: 创建 BaseStore 抽象基类

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/stores/base/base_store.py`
- 新建: `packages/datahub/src/ditto_datahub/stores/base/__init__.py`

**步骤 1: 编写失败测试**

```python
# packages/datahub/tests/unit/stores/base/test_base_store_unit.py
import pytest
from ditto_datahub.stores.base import BaseStore

def test_base_store_cannot_be_instantiated():
    """BaseStore 是抽象类，不能直接实例化."""
    with pytest.raises(TypeError):
        BaseStore()

def test_base_store_requires_abstract_methods():
    """子类必须实现抽象方法."""
    class IncompleteStore(BaseStore):
        pass

    with pytest.raises(TypeError):
        IncompleteStore()
```

**步骤 2: 运行测试确认失败**

```bash
pixi run -e dev pytest tests/unit/stores/base/test_base_store_unit.py::test_base_store_cannot_be_instantiated -v
# 预期: FAIL - "BaseStore not defined"
```

**步骤 3: 实现 BaseStore 抽象基类**

```python
# packages/datahub/src/ditto_datahub/stores/base/base_store.py
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ditto_datahub.models import WriteResult


class BaseStore(ABC):
    """
    数据存储抽象基类.

    定义所有数据存储的统一接口，确保读写行为一致.

    Attributes:
        data_root: 数据存储根目录.

    """

    def __init__(self, data_root: Path) -> None:
        """
        初始化 BaseStore.

        Args:
            data_root: 数据存储根目录.

        """
        self.data_root = data_root

    @abstractmethod
    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> object:
        """
        读取数据.

        Args:
            dataset: 数据集名称.
            sids: 按 SID 列表过滤.
            start_date: 开始日期 (YYYY-MM-DD).
            end_date: 结束日期 (YYYY-MM-DD).
            **kwargs: 其他查询参数.

        Returns:
            查询结果（具体类型由子类决定）.

        """
        ...

    @abstractmethod
    def write(
        self,
        dataset: str,
        data: object,
        on_duplicate: str = "error",
        **kwargs: object,
    ) -> WriteResult:
        """
        写入数据.

        Args:
            dataset: 数据集名称.
            data: 要写入的数据.
            on_duplicate: 重复数据处理策略 (error/keep_first/keep_last).
            **kwargs: 其他写入参数.

        Returns:
            写入结果.

        """
        ...

    @abstractmethod
    def delete(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> int:
        """
        删除数据.

        Args:
            dataset: 数据集名称.
            sids: 按 SID 列表过滤.
            start_date: 开始日期.
            end_date: 结束日期.
            **kwargs: 其他删除参数.

        Returns:
            删除的行数.

        """
        ...
```

**步骤 4: 运行测试确认通过**

```bash
pixi run -e dev pytest tests/unit/stores/base/test_base_store_unit.py -v
# 预期: PASS
```

**步骤 5: 提交**

```bash
git add packages/datahub/src/ditto_datahub/stores/base/
git add packages/datahub/tests/unit/stores/base/
git commit -m "feat(datahub): add BaseStore abstract base class"
```

---

## 任务 2: 实现 ParquetStore 基类

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/stores/base/parquet_store.py`
- 修改: `packages/datahub/src/ditto_datahub/stores/base/__init__.py`
- 新建: `packages/datahub/tests/unit/stores/base/test_parquet_store_unit.py`

**步骤 1: 编写失败测试**

```python
# packages/datahub/tests/unit/stores/base/test_parquet_store_unit.py
import polars as pl
from pathlib import Path
import tempfile
import shutil

def test_parquet_store_write_and_read():
    """测试 ParquetStore 的基本读写功能."""
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    data_root = Path(temp_dir)

    try:
        from ditto_datahub.stores.base import ParquetStore

        # 初始化 store
        store = ParquetStore(data_root)

        # 写入测试数据
        test_df = pl.DataFrame({
            "sid": [1, 1, 2],
            "trade_date": ["2024-01-01", "2024-01-02", "2024-01-01"],
            "close": [10.0, 11.0, 20.0],
        })

        result = store.write(
            dataset="test_dataset",
            data=test_df,
            year=2024,
        )

        assert result.file_path.exists()
        assert result.rows_written == 3

        # 读取数据
        read_df = store.read(
            dataset="test_dataset",
            sids=[1],
            start_date="2024-01-01",
            end_date="2024-01-02",
        )

        assert len(read_df) == 2
        assert read_df["sid"].to_list() == [1, 1]

    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir)
```

**步骤 2: 运行测试确认失败**

```bash
pixi run -e dev pytest tests/unit/stores/base/test_parquet_store_unit.py::test_parquet_store_write_and_read -v
# 预期: FAIL - "ParquetStore not defined"
```

**步骤 3: 实现 ParquetStore**

从现有的 `ParquetStoreBase` 迁移核心功能到新的 `ParquetStore`:

```python
# packages/datahub/src/ditto_datahub/stores/base/parquet_store.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.models import OnDuplicate, WriteResult
from ditto_datahub.stores.base.base_store import BaseStore


class ParquetStore(BaseStore):
    """
    Parquet 文件存储实现.

    支持按年分区存储，适用于时序数据.
    """

    def __init__(self, data_root: Path) -> None:
        """初始化 ParquetStore."""
        super().__init__(data_root)

    def _get_dataset_path(self, dataset: str) -> Path:
        """获取数据集存储路径."""
        return self.data_root / dataset

    def _get_partition_path(self, dataset: str, year: int) -> Path:
        """获取分区文件路径."""
        return self._get_dataset_path(dataset) / f"{year}.parquet"

    def _collect_paths(
        self, dataset: str, start_year: int, end_year: int
    ) -> list[Path]:
        """收集所有相关分区文件路径."""
        dataset_path = self._get_dataset_path(dataset)
        if not dataset_path.exists():
            return []

        paths = []
        for year in range(start_year, end_year + 1):
            path = self._get_partition_path(dataset, year)
            if path.exists():
                paths.append(path)

        return paths

    @traced("data.read")
    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """
        读取 Parquet 数据.

        Args:
            dataset: 数据集名称.
            sids: 按 SID 列表过滤.
            start_date: 开始日期 (YYYY-MM-DD).
            end_date: 结束日期 (YYYY-MM-DD).
            **kwargs: 其他查询参数.

        Returns:
            查询结果 DataFrame.

        """
        # 确定年份范围
        start_year = int(start_date[:4]) if start_date else 1990
        end_year = int(end_date[:4]) if end_date else 2099

        # 收集文件路径
        paths = self._collect_paths(dataset, start_year, end_year)
        if not paths:
            return pl.DataFrame()

        # 扫描并过滤
        lf = pl.scan_parquet([str(p) for p in paths])

        # 应用 SID 过滤
        if sids:
            lf = lf.filter(pl.col("sid").is_in(sids))

        # 应用日期过滤
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") >= start_dt)

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") <= end_dt)

        # 去重并收集
        result = lf.unique(subset=["sid", "trade_date"], keep="last").collect()

        # 记录指标
        M.data_records.add(len(result), {"dataset": dataset, "status": "success"})

        return result

    @traced("data.write")
    def write(
        self,
        dataset: str,
        data: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
        **kwargs: Any,
    ) -> WriteResult:
        """
        写入 Parquet 数据.

        Args:
            dataset: 数据集名称.
            data: 要写入的 DataFrame.
            year: 年份分区.
            on_duplicate: 重复数据处理策略.
            **kwargs: 其他写入参数.

        Returns:
            写入结果.

        """
        # 确保目录存在
        dataset_path = self._get_dataset_path(dataset)
        dataset_path.mkdir(parents=True, exist_ok=True)

        # 排序数据
        df = data.sort(["sid", "trade_date"])

        # 获取目标文件路径
        file_path = self._get_partition_path(dataset, year)

        # 处理重复数据策略
        if file_path.exists():
            existing = pl.read_parquet(file_path)
            combined = pl.concat([existing, df])
            df = combined.unique(subset=["sid", "trade_date"], keep="last")

        # 写入数据
        df.write_parquet(file_path)

        # 计算校验和
        checksum = M.data_checksum.compute(df)

        # 记录指标
        M.data_records.add(len(df), {"dataset": dataset, "operation": "write"})

        logger.info(
            "Parquet data written",
            event="parquet_write_complete",
            dataset=dataset,
            file_path=str(file_path),
            rows_written=len(df),
        )

        return WriteResult(
            file_path=file_path,
            checksum=checksum,
            rows_written=len(df),
            rows_total=len(df),
            blocked=False,
        )

    def delete(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> int:
        """
        删除 Parquet 数据.

        注意: Parquet 文件不支持原地删除，需要重写整个文件.

        Args:
            dataset: 数据集名称.
            sids: 按 SID 列表过滤.
            start_date: 开始日期.
            end_date: 结束日期.

        Returns:
            删除的行数.

        """
        # 读取现有数据
        start_year = int(start_date[:4]) if start_date else 1990
        end_year = int(end_date[:4]) if end_date else 2099

        affected_files = self._collect_paths(dataset, start_year, end_year)
        if not affected_files:
            return 0

        total_deleted = 0

        for file_path in affected_files:
            # 读取文件
            df = pl.read_parquet(file_path)

            # 应用过滤
            if sids:
                df = df.filter(~pl.col("sid").is_in(sids))
            if start_date:
                df = df.filter(pl.col("trade_date") < datetime.strptime(start_date, "%Y-%m-%d").date())
            if end_date:
                df = df.filter(pl.col("trade_date") > datetime.strptime(end_date, "%Y-%m-%d").date())

            deleted_count = len(df) - len(df)
            total_deleted += deleted_count

            # 重写文件
            df.write_parquet(file_path)

        return total_deleted
```

**步骤 4: 更新 __init__.py**

```python
# packages/datahub/src/ditto_datahub/stores/base/__init__.py
from ditto_datahub.stores.base.base_store import BaseStore
from ditto_datahub.stores.base.parquet_store import ParquetStore

__all__ = ["BaseStore", "ParquetStore"]
```

**步骤 5: 运行测试确认通过**

```bash
pixi run -e dev pytest tests/unit/stores/base/test_parquet_store_unit.py -v
# 预期: PASS
```

**步骤 6: 提交**

```bash
git add packages/datahub/src/ditto_datahub/stores/base/parquet_store.py
git add packages/datahub/tests/unit/stores/base/
git commit -m "feat(datahub): implement ParquetStore base class"
```

---

## 任务 3: 实现 SQLiteStore 基类

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/stores/base/sqlite_store.py`
- 修改: `packages/datahub/src/ditto_datahub/stores/base/__init__.py`
- 新建: `packages/datahub/tests/unit/stores/base/test_sqlite_store_unit.py`

**步骤 1: 编写失败测试**

```python
# packages/datahub/tests/unit/stores/base/test_sqlite_store_unit.py
import polars as pl
import tempfile
import shutil
from pathlib import Path

def test_sqlite_store_write_and_read():
    """测试 SQLiteStore 的基本读写功能."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test.sqlite"

    try:
        from ditto_datahub.stores.base import SQLiteStore

        # 初始化 store
        store = SQLiteStore(db_path)

        # 创建测试表
        store.execute("""
            CREATE TABLE IF NOT EXISTS test_table (
                sid INTEGER,
                trade_date TEXT,
                close REAL,
                PRIMARY KEY (sid, trade_date)
            )
        """)

        # 写入测试数据
        test_df = pl.DataFrame({
            "sid": [1, 1, 2],
            "trade_date": ["2024-01-01", "2024-01-02", "2024-01-01"],
            "close": [10.0, 11.0, 20.0],
        })

        store.write_dataframe(
            table="test_table",
            df=test_df,
            on_duplicate="keep_last",
        )

        # 读取数据
        read_df = store.read(
            table="test_table",
            sids=[1],
            start_date="2024-01-01",
            end_date="2024-01-02",
        )

        assert len(read_df) == 2
        assert read_df["sid"].to_list() == [1, 1]

    finally:
        shutil.rmtree(temp_dir)
```

**步骤 2: 运行测试确认失败**

```bash
pixi run -e dev pytest tests/unit/stores/base/test_sqlite_store_unit.py::test_sqlite_store_write_and_read -v
# 预期: FAIL - "SQLiteStore not defined"
```

**步骤 3: 实现 SQLiteStore**

```python
# packages/datahub/src/ditto_datahub/stores/base/sqlite_store.py
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.models import WriteResult
from ditto_datahub.stores.base.base_store import BaseStore


class SQLiteStore(BaseStore):
    """
    SQLite 数据库存储实现.

    支持单库多表，适用于元数据存储.
    """

    def __init__(self, db_path: Path) -> None:
        """
        初始化 SQLiteStore.

        Args:
            db_path: SQLite 数据库文件路径.

        """
        super().__init__(db_path.parent)
        self.db_path = db_path

    def _get_connection(self):
        """获取数据库连接."""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @traced("data.sqlite.read")
    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """
        从 SQLite 读取数据.

        Args:
            dataset: 表名.
            sids: 按 SID 列表过滤.
            start_date: 开始日期 (YYYY-MM-DD).
            end_date: 结束日期 (YYYY-MM-DD).
            **kwargs: 其他查询参数.

        Returns:
            查询结果 DataFrame.

        """
        table = dataset

        # 构建 SQL
        sql = f"SELECT * FROM {table} WHERE 1=1"  # noqa: S608
        params: list[Any] = []

        if sids:
            placeholders = ",".join("?" * len(sids))
            sql += f" AND sid IN ({placeholders})"
            params.extend(sids)

        if start_date:
            sql += " AND trade_date >= ?"
            params.append(start_date)

        if end_date:
            sql += " AND trade_date <= ?"
            params.append(end_date)

        # 执行查询
        with self._get_connection() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

        if not rows:
            return pl.DataFrame()

        # 转换为 DataFrame
        return pl.DataFrame([dict(row) for row in rows])

    @traced("data.sqlite.write")
    def write(
        self,
        dataset: str,
        data: pl.DataFrame,
        on_duplicate: str = "error",
        **kwargs: Any,
    ) -> WriteResult:
        """
        向 SQLite 写入数据.

        Args:
            dataset: 表名.
            data: 要写入的 DataFrame.
            on_duplicate: 重复数据处理策略.
            **kwargs: 其他写入参数.

        Returns:
            写入结果.

        """
        table = dataset

        # 确保数据库目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 准备数据
        rows = data.to_dicts()
        if not rows:
            return WriteResult(
                file_path=self.db_path,
                checksum="",
                rows_written=0,
                rows_total=0,
                blocked=False,
            )

        # 获取列名
        columns = rows[0].keys()
        placeholders = ",".join("?" * len(columns))
        col_names = ",".join(columns)

        # 构建 INSERT 语句
        if on_duplicate == "keep_last":
            sql = f"""
                INSERT OR REPLACE INTO {table} ({col_names})
                VALUES ({placeholders})
            """  # noqa: S608
        elif on_duplicate == "keep_first":
            sql = f"""
                INSERT OR IGNORE INTO {table} ({col_names})
                VALUES ({placeholders})
            """  # noqa: S608
        else:  # error
            sql = f"""
                INSERT INTO {table} ({col_names})
                VALUES ({placeholders})
            """  # noqa: S608

        # 执行插入
        with self._get_connection() as conn:
            for row in rows:
                try:
                    conn.execute(sql, list(row.values()))
                except Exception as e:
                    if on_duplicate == "error":
                        raise
                    logger.warning(
                        "Failed to insert row",
                        event="sqlite_write_failed",
                        table=table,
                        error=str(e),
                    )
            conn.commit()

        # 计算校验和
        checksum = M.data_checksum.compute(data)

        # 记录指标
        M.data_records.add(len(data), {"dataset": table, "operation": "write"})

        logger.info(
            "SQLite data written",
            event="sqlite_write_complete",
            table=table,
            rows_written=len(data),
        )

        return WriteResult(
            file_path=self.db_path,
            checksum=checksum,
            rows_written=len(data),
            rows_total=self._count_rows(table),
            blocked=False,
        )

    def _count_rows(self, table: str) -> int:
        """统计表行数."""
        with self._get_connection() as conn:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
            return cursor.fetchone()[0]

    def execute(self, sql: str, params: list[Any] | None = None) -> None:
        """
        执行 SQL 语句.

        Args:
            sql: SQL 语句.
            params: 参数列表.

        """
        with self._get_connection() as conn:
            conn.execute(sql, params or [])
            conn.commit()

    def fetchone(self, sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
        """
        查询单行数据.

        Args:
            sql: SQL 语句.
            params: 参数列表.

        Returns:
            行数据字典，如果不存在返回 None.

        """
        with self._get_connection() as conn:
            cursor = conn.execute(sql, params or [])
            row = cursor.fetchone()
            return dict(row) if row else None

    def fetchall(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """
        查询多行数据.

        Args:
            sql: SQL 语句.
            params: 参数列表.

        Returns:
            行数据字典列表.

        """
        with self._get_connection() as conn:
            cursor = conn.execute(sql, params or [])
            return [dict(row) for row in cursor.fetchall()]

    def write_dataframe(
        self,
        table: str,
        df: pl.DataFrame,
        on_duplicate: str = "error",
    ) -> None:
        """
        写入 DataFrame 到表.

        Args:
            table: 表名.
            df: 数据 DataFrame.
            on_duplicate: 重复数据处理策略.

        """
        self.write(dataset=table, data=df, on_duplicate=on_duplicate)

    def delete(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> int:
        """
        删除数据.

        Args:
            dataset: 表名.
            sids: 按 SID 列表过滤.
            start_date: 开始日期.
            end_date: 结束日期.

        Returns:
            删除的行数.

        """
        table = dataset

        # 构建 SQL
        sql = f"DELETE FROM {table} WHERE 1=1"  # noqa: S608
        params: list[Any] = []

        if sids:
            placeholders = ",".join("?" * len(sids))
            sql += f" AND sid IN ({placeholders})"
            params.extend(sids)

        if start_date:
            sql += " AND trade_date >= ?"
            params.append(start_date)

        if end_date:
            sql += " AND trade_date <= ?"
            params.append(end_date)

        # 执行删除
        with self._get_connection() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount
```

**步骤 4: 更新 __init__.py**

```python
# packages/datahub/src/ditto_datahub/stores/base/__init__.py
from ditto_datahub.stores.base.base_store import BaseStore
from ditto_datahub.stores.base.parquet_store import ParquetStore
from ditto_datahub.stores.base.sqlite_store import SQLiteStore

__all__ = ["BaseStore", "ParquetStore", "SQLiteStore"]
```

**步骤 5: 运行测试确认通过**

```bash
pixi run -e dev pytest tests/unit/stores/base/test_sqlite_store_unit.py -v
# 预期: PASS
```

**步骤 6: 提交**

```bash
git add packages/datahub/src/ditto_datahub/stores/base/sqlite_store.py
git add packages/datahub/tests/unit/stores/base/
git commit -m "feat(datahub): implement SQLiteStore base class"
```

---

## 任务 4: 重构配置系统 - 单 DATAROOT 配置

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/config/data_root.py`
- 新建: `packages/datahub/src/ditto_datahub/config/__init__.py`
- 修改: `packages/datahub/pixi.toml` (更新环境变量)

**步骤 1: 编写失败测试**

```python
# packages/datahub/tests/unit/config/test_data_root_config_unit.py
from pathlib import Path
import tempfile

def test_data_root_config_generates_all_paths():
    """测试 DataRootConfig 能够生成所有必要的路径."""
    from ditto_datahub.config import DataRootConfig

    with tempfile.TemporaryDirectory() as temp_dir:
        # 使用临时目录作为 DATAROOT
        config = DataRootConfig(data_root=Path(temp_dir))

        # 验证各种路径
        assert config.data_root == Path(temp_dir)
        assert config.market_stock_bars_path == Path(temp_dir) / "market" / "stock" / "bars" / "daily"
        assert config.market_etf_bars_path == Path(temp_dir) / "market" / "etf" / "bars" / "daily"
        assert config.metadata_db_path == Path(temp_dir) / "metadata" / "metadata.sqlite"
        assert config.capital_flow_path == Path(temp_dir) / "capital" / "flow"
```

**步骤 2: 运行测试确认失败**

```bash
pixi run -e dev pytest tests/unit/config/test_data_root_config_unit.py::test_data_root_config_generates_all_paths -v
# 预期: FAIL - "DataRootConfig not defined"
```

**步骤 3: 实现 DataRootConfig**

```python
# packages/datahub/src/ditto_datahub/config/data_root.py
from __future__ import annotations

from pathlib import Path
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DataRootConfig(BaseSettings):
    """
    数据存储根目录配置.

    从单一 DATAROOT 环境变量生成所有必要的路径.

    Attributes:
        data_root: 数据存储根目录 (DATAROOT 环境变量).

    """

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    data_root: Path

    @computed_field
    @property
    def market_stock_bars_path(self) -> Path:
        """股票日线行情数据路径."""
        return self.data_root / "market" / "stock" / "bars" / "daily"

    @computed_field
    @property
    def market_etf_bars_path(self) -> Path:
        """ETF 日线行情数据路径."""
        return self.data_root / "market" / "etf" / "bars" / "daily"

    @computed_field
    @property
    def market_index_bars_path(self) -> Path:
        """指数日线行情数据路径."""
        return self.data_root / "market" / "index" / "bars" / "daily"

    @computed_field
    @property
    def market_stock_status_path(self) -> Path:
        """股票状态数据路径."""
        return self.data_root / "market" / "stock" / "status"

    @computed_field
    @property
    def market_etf_status_path(self) -> Path:
        """ETF 状态数据路径."""
        return self.data_root / "market" / "etf" / "status"

    @computed_field
    @property
    def market_stock_adj_path(self) -> Path:
        """股票复权因子数据路径."""
        return self.data_root / "market" / "stock" / "adj"

    @computed_field
    @property
    def market_etf_adj_path(self) -> Path:
        """ETF 复权因子数据路径."""
        return self.data_root / "market" / "etf" / "adj"

    @computed_field
    @property
    def market_etf_nav_path(self) -> Path:
        """ETF 净值数据路径."""
        return self.data_root / "market" / "etf" / "nav"

    @computed_field
    @property
    def metadata_db_path(self) -> Path:
        """元数据 SQLite 数据库路径."""
        return self.data_root / "metadata" / "metadata.sqlite"

    @computed_field
    @property
    def capital_flow_path(self) -> Path:
        """资金流向数据路径."""
        return self.data_root / "capital" / "flow"

    @computed_field
    @property
    def capital_margin_path(self) -> Path:
        """融资融券数据路径."""
        return self.data_root / "capital" / "margin"

    @computed_field
    @property
    def capital_top_board_path(self) -> Path:
        """龙虎榜数据路径."""
        return self.data_root / "capital" / "top_board"

    @computed_field
    @property
    def capital_limit_board_path(self) -> Path:
        """打板数据路径."""
        return self.data_root / "capital" / "limit_board"

    @computed_field
    @property
    def capital_chip_path(self) -> Path:
        """筹码分布数据路径."""
        return self.data_root / "capital" / "chip"

    @computed_field
    @property
    def fundamental_financial_path(self) -> Path:
        """财务报表数据路径."""
        return self.data_root / "fundamental" / "financial"

    @computed_field
    @property
    def fundamental_indicator_path(self) -> Path:
        """财务指标数据路径."""
        return self.data_root / "fundamental" / "indicator"

    @computed_field
    @property
    def fundamental_forecast_path(self) -> Path:
        """业绩预告数据路径."""
        return self.data_root / "fundamental" / "forecast"

    @computed_field
    @property
    def fundamental_holding_path(self) -> Path:
        """持仓数据路径."""
        return self.data_root / "fundamental" / "holding"

    @computed_field
    @property
    def features_technical_price_path(self) -> Path:
        """价格特征数据路径."""
        return self.data_root / "features" / "technical" / "price"

    @computed_field
    @property
    def factors_narrow_style_path(self) -> Path:
        """风格因子窄表数据路径."""
        return self.data_root / "factors" / "narrow" / "style"

    @computed_field
    @property
    def factors_wide_style_path(self) -> Path:
        """风格因子宽表数据路径."""
        return self.data_root / "factors" / "wide" / "style"

    @computed_field
    @property
    def macro_indicators_path(self) -> Path:
        """宏观指标数据路径."""
        return self.data_root / "macro" / "indicators"
```

**步骤 4: 更新 __init__.py**

```python
# packages/datahub/src/ditto_datahub/config/__init__.py
from ditto_datahub.config.data_root import DataRootConfig

__all__ = ["DataRootConfig"]
```

**步骤 5: 运行测试确认通过**

```bash
pixi run -e dev pytest tests/unit/config/test_data_root_config_unit.py -v
# 预期: PASS
```

**步骤 6: 提交**

```bash
git add packages/datahub/src/ditto_datahub/config/
git add packages/datahub/tests/unit/config/
git commit -m "feat(datahub): add DataRootConfig for simplified path configuration"
```

---

## 任务 5: 迁移 BarsStore 使用新基类

**文件:**
- 修改: `packages/datahub/src/ditto_datahub/stores/bars_store.py`

**步骤 1: 阅读现有实现**

```bash
# 确认现有 BarsStore 的结构
pixi run -e dev python -c "from ditto_datahub.stores.bars_store import BarsStore; print(BarsStore.__mro__)"
```

**步骤 2: 重构 BarsStore 继承 ParquetStore**

```python
# packages/datahub/src/ditto_datahub/stores/bars_store.py
"""
Market bars storage with year partitioning.

Stores market daily data (stock/ETF) in Parquet files with year partitioning.
Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.models import OnDuplicate, WriteResult
from ditto_datahub.stores.base.parquet_store import ParquetStore

# Default year range for date filters
DEFAULT_START_YEAR = 1990
DEFAULT_END_YEAR = 2099


class BarsStore(ParquetStore):
    """
    Market bars data storage with year partitioning.

    Storage structure:
        data_root/
            market/stock/bars/daily/
                2020.parquet
                2021.parquet
                ...
            market/etf/bars/daily/
                2020.parquet
                ...

    继承 ParquetStore 的读写能力，添加行情数据特定的逻辑.
    """

    def __init__(self, data_root: Path) -> None:
        """初始化 BarsStore."""
        super().__init__(data_root)

    def _get_key_columns(self) -> list[str]:
        """返回键列名."""
        return ["sid", "trade_date"]

    def _get_sort_columns(self) -> list[str]:
        """返回排序列名（BarsStore 使用 trade_date, sid 顺序）."""
        return ["trade_date", "sid"]

    def _get_dataset_path(self, dataset: str) -> Path:
        """
        获取数据集存储路径.

        Args:
            dataset: 数据集名称 (stock_daily, etf_daily, index_daily).

        Returns:
            数据集存储路径.

        """
        # 根据 dataset 映射到实际路径
        if dataset == "stock_daily":
            return self.data_root / "market" / "stock" / "bars" / "daily"
        elif dataset == "etf_daily":
            return self.data_root / "market" / "etf" / "bars" / "daily"
        elif dataset == "index_daily":
            return self.data_root / "market" / "index" / "bars" / "daily"
        else:
            return self.data_root / dataset

    def _ensure_date_column(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Ensure trade_date column is Date type for sorting.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with trade_date as Date type.

        """
        dtype = df["trade_date"].dtype

        # If already Date type, return as-is
        if dtype == pl.Date:
            return df

        # If String type, convert to Date
        if dtype == pl.String:
            return df.with_columns(pl.col("trade_date").str.to_date())

        # If Object type (could be date objects or strings), try to convert
        if dtype == pl.Object:
            # Try casting to string first, then to date
            try:
                return df.with_columns(
                    pl.col("trade_date").cast(pl.String).str.to_date()
                )
            except Exception:
                # If that fails, the column might already contain date objects
                # Just return the DataFrame as-is and hope for the best
                return df

        return df

    def _prepare_for_write(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        准备写入：归一化日期列并排序。

        BarsStore 覆盖此方法以使用特殊的日期列处理和排序顺序。

        Args:
            df: 输入 DataFrame。

        Returns:
            准备好的 DataFrame。

        """
        # Ensure trade_date is date type for sorting
        df = self._ensure_date_column(df)
        # Sort for optimal read performance
        return df.sort(self._get_sort_columns())

    # ============ Write operations ============

    @traced("data.write")
    def write(
        self,
        dataset: str,
        data: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
        **kwargs: Any,
    ) -> WriteResult:
        """
        Write bars data.

        覆盖 ParquetStore.write 以添加日期列准备逻辑.

        Args:
            dataset: Dataset name (e.g., "stock_daily", "etf_daily").
            data: Bars data DataFrame.
            year: Year partition for storage.
            on_duplicate: Strategy for handling duplicate data.
            **kwargs: Additional write parameters.

        Returns:
            Write result with file path and checksum.

        """
        # 准备数据
        df = self._prepare_for_write(data)

        # 调用父类写入方法
        return super().write(dataset, df, year, on_duplicate, **kwargs)

    # ============ Read operations ============

    def _build_filter_conditions(
        self,
        lf: pl.LazyFrame,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.LazyFrame:
        """
        Build filter conditions for LazyFrame.

        Args:
            lf: LazyFrame to filter.
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Filtered LazyFrame.

        """
        if sids:
            lf = lf.filter(pl.col("sid").is_in(sids))

        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") >= start_dt)

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            lf = lf.filter(pl.col("trade_date") <= end_dt)

        return lf

    @traced("data.read")
    def read(
        self,
        dataset: str,
        sids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> pl.DataFrame:
        """
        Read market bars data.

        覆盖 ParquetStore.read 以添加专门的过滤逻辑.

        Args:
            dataset: Dataset name (e.g., "stock_daily", "etf_daily").
            sids: Filter by security IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            **kwargs: Additional read parameters.

        Returns:
            DataFrame with matching records.

        """
        start_time = time.time()

        # Determine year range from date filters
        start_year = int(start_date[:4]) if start_date else DEFAULT_START_YEAR
        end_year = int(end_date[:4]) if end_date else DEFAULT_END_YEAR

        paths = self._collect_paths(dataset, start_year, end_year)

        if not paths:
            logger.info(
                "No data found for query",
                event="data_read_complete",
                dataset=dataset,
                start_date=start_date,
                end_date=end_date,
                row_count=0,
                duration_ms=0,
            )
            return pl.DataFrame()

        # Scan and apply filters
        lf = pl.scan_parquet([str(p) for p in paths])
        lf = self._build_filter_conditions(lf, sids, start_date, end_date)
        result = lf.unique(subset=self._get_key_columns(), keep="last").collect()

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Data read completed",
            event="data_read_complete",
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            sids_count=len(sids) if sids else None,
            row_count=len(result),
            duration_ms=round(duration_ms, 2),
        )

        # Record metrics
        M.data_records.add(len(result), {"dataset": dataset, "status": "success"})
        M.data_update_duration.record(duration_ms / 1000, {"dataset": dataset})

        return result
```

**步骤 3: 运行现有测试确保兼容性**

```bash
pixi run -e dev pytest tests/unit/stores/test_bars_store_unit.py -v
# 预期: PASS (现有测试应该仍然通过)
```

**步骤 4: 提交**

```bash
git add packages/datahub/src/ditto_datahub/stores/bars_store.py
git commit -m "refactor(datahub): migrate BarsStore to inherit from ParquetStore"
```

---

## 任务 6: 迁移 SecurityStore 使用新基类

**文件:**
- 修改: `packages/datahub/src/ditto_datahub/stores/security_store.py`

**步骤 1: 重构 SecurityStore 继承 SQLiteStore**

由于 SecurityStore 使用 SQLiteClient 而不是直接操作数据库，需要创建适配器：

```python
# packages/datahub/src/ditto_datahub/stores/security_store.py
"""
SecurityStore for securities master data with PIT support.

This module provides storage and retrieval for securities master data
with Point-in-Time support for identifier resolution.

Following design document at docs/design/02_data_design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import polars as pl
from ditto_foundation import M, logger, traced
from ditto_foundation.cache import DataCache

from ditto_datahub.accessors.internal.enrichment import (
    enrich_with_symbol as enrich_with_symbol_fn,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient


@dataclass(frozen=True)
class SecurityRegistration:
    """
    证券注册信息配置对象。

    用于封装证券注册所需的所有参数，避免函数参数过多。
    """

    src_code: str
    symbol: str
    name: str
    exchange: str
    asset_class: str
    list_date: str
    source: str = "tushare"
    board: str | None = None


def _build_in_clause(
    column: str,
    items: list[Any],
    chunk_size: int = 200,
) -> tuple[str, list[Any]]:
    """
    构建参数化 IN 子句（自动分块）。

    确保 SQL 注入安全，使用参数化查询。
    当列表超过 chunk_size 时，自动分块并用 OR 连接。

    Args:
        column: 列名（如 "s.sid", "m.src_code"）。
        items: 值列表。
        chunk_size: 每块的最大参数数量（默认 200，SQLite 限制）。

    Returns:
        (SQL 片段, 参数列表) 元组。

    Examples:
        >>> _build_in_clause("s.sid", [1, 2, 3])
        ('s.sid IN (?,?,?)', [1, 2, 3])
        >>> _build_in_clause("s.sid", list(range(500)), chunk_size=200)
        ('(s.sid IN (...)) OR (s.sid IN (...))', [...])

    """
    if not items:
        return ("1=0", [])  # 空 IN 返回 False 条件

    if len(items) <= chunk_size:
        placeholders = ",".join("?" * len(items))
        return f"{column} IN ({placeholders})", items

    # 分块处理：用 OR 连接多个 IN 子句
    chunks = [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
    clauses: list[str] = []
    params: list[Any] = []
    for chunk in chunks:
        placeholders = ",".join("?" * len(chunk))
        clauses.append(f"{column} IN ({placeholders})")
        params.extend(chunk)

    return f"({' OR '.join(clauses)})", params


class SecurityStore:
    """
    Securities master data storage with PIT support.

    Core functionality:
    - resolve_sid: (source, src_code, asof) -> sid
    - Through security_mapping with effective_from/to for historical resolution

    Note: SecurityStore 不继承 SQLiteStore，因为它通过 SQLiteClient 访问数据
    以保持向后兼容。未来版本可能重构为直接继承 SQLiteStore.
    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any] | None = None,
    ) -> None:
        """
        Initialize SecurityStore.

        Args:
            sqlite_client: SQLite client for database operations.
            data_cache: Optional DataCache for SID resolution caching.

        """
        self._client = sqlite_client
        self._data_cache = data_cache

    # ... 保持现有方法不变 ...

    # 所有现有方法保持不变，这里省略以节省空间
```

**步骤 2: 运行现有测试确保兼容性**

```bash
pixi run -e dev pytest tests/unit/stores/test_security_store_unit.py -v
# 预期: PASS
```

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/stores/security_store.py
git commit -m "refactor(datahub): update SecurityStore doc for future SQLiteStore migration"
```

---

## 任务 7: 更新依赖注入配置

**文件:**
- 修改: `packages/datahub/src/ditto_datahub/init_providers.py`
- 修改: `packages/datahub/src/ditto_datahub/hub.py`

**步骤 1: 更新 Provider 以使用新配置**

```python
# packages/datahub/src/ditto_datahub/init_providers.py
"""DataHub 依赖注入提供者配置."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from dishka import Provider, provide

from ditto_foundation import SQLitePool
from ditto_foundation.cache import DataCache
from ditto_foundation.concurrency import FileLockManager

from ditto_datahub.config import DataRootConfig
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.index_weight_store import IndexWeightStore
from ditto_datahub.stores.ingestion_log import IngestionLogStore
from ditto_datahub.stores.quarantine_store import QuarantineStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.stock_status_store import StockStatusStore
from ditto_datahub.stores.universe_store import UniverseStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


class DataHubProvider(Provider):
    """DataHub 依赖注入提供者."""

    data_root_config = provide(DataRootConfig)

    @staticmethod
    @provide
    def data_root_path(config: DataRootConfig) -> Path:
        """提供 data_root 路径."""
        return config.data_root

    # SQLite 客户端提供者
    @staticmethod
    @provide
    def sqlite_client(config: DataRootConfig) -> SQLiteClient:
        """提供 SQLite 客户端."""
        return SQLiteClient(config.metadata_db_path)

    @staticmethod
    @provide
    def sqlite_pool() -> SQLitePool:
        """提供 SQLite 连接池."""
        return SQLitePool()

    # Store 提供者
    @staticmethod
    @provide
    def bars_store(config: DataRootConfig) -> BarsStore:
        """提供 BarsStore."""
        return BarsStore(config.data_root)

    @staticmethod
    @provide
    def security_store(sqlite_client: SQLiteClient) -> SecurityStore:
        """提供 SecurityStore."""
        return SecurityStore(sqlite_client)

    @staticmethod
    @provide
    def adj_factor_store(sqlite_client: SQLiteClient) -> AdjFactorStore:
        """提供 AdjFactorStore."""
        return AdjFactorStore(sqlite_client)

    @staticmethod
    @provide
    def calendar_store(sqlite_client: SQLiteClient) -> CalendarStore:
        """提供 CalendarStore."""
        return CalendarStore(sqlite_client)

    @staticmethod
    @provide
    def stock_status_store(sqlite_client: SQLiteClient) -> StockStatusStore:
        """提供 StockStatusStore."""
        return StockStatusStore(sqlite_client)

    @staticmethod
    @provide
    def universe_store(sqlite_client: SQLiteClient) -> UniverseStore:
        """提供 UniverseStore."""
        return UniverseStore(sqlite_client)

    @staticmethod
    @provide
    def index_weight_store(sqlite_client: SQLiteClient) -> IndexWeightStore:
        """提供 IndexWeightStore."""
        return IndexWeightStore(sqlite_client)

    @staticmethod
    @provide
    def ingestion_log_store(sqlite_client: SQLiteClient) -> IngestionLogStore:
        """提供 IngestionLogStore."""
        return IngestionLogStore(sqlite_client)

    @staticmethod
    @provide
    def quarantine_store(sqlite_client: SQLiteClient) -> QuarantineStore:
        """提供 QuarantineStore."""
        return QuarantineStore(sqlite_client)

    # Runtime 提供者
    @staticmethod
    @provide
    def file_lock() -> FileLockManager:
        """提供文件锁管理器."""
        return FileLockManager()

    @staticmethod
    @provide
    def sid_allocator(security_store: SecurityStore) -> SidAllocator:
        """提供 SID 分配器."""
        return SidAllocator(security_store)

    @staticmethod
    @provide
    def freeze_manager(sqlite_client: SQLiteClient) -> FreezeManager:
        """提供冻结管理器."""
        return FreezeManager(sqlite_client)

    @staticmethod
    @provide
    def sql_engine(
        data_root_path: Path,
        sqlite_pool: SQLitePool,
    ) -> SqlEngine:
        """提供 SQL 引擎."""
        return SqlEngine(data_root_path, sqlite_pool)

    # 缓存提供者
    @staticmethod
    @provide
    def data_cache() -> DataCache[Any] | None:
        """提供数据缓存（可选）."""
        # 可以根据环境变量决定是否启用
        return None  # 或 return DataCache(maxsize=10000)
```

**步骤 2: 运行集成测试确保依赖注入正常工作**

```bash
pixi run -e dev pytest tests/integration/ -k "not slow" -v
# 预期: PASS
```

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/init_providers.py
git commit -m "refactor(datahub): update providers to use DataRootConfig"
```

---

## 任务 8: 清理和文档更新

**文件:**
- 修改: `packages/datahub/README.md`
- 修改: `docs/design/02_data_design.md`

**步骤 1: 更新 README**

```markdown
# DataHub Package

数据访问层，提供统一的数据存储和查询接口.

## 架构

### 基础层

- `BaseStore`: 抽象基类，定义统一接口
- `ParquetStore`: Parquet 文件存储实现
- `SQLiteStore`: SQLite 数据库存储实现

### Store 层

- `BarsStore`: K线数据存储
- `SecurityStore`: 证券主数据存储
- `AdjFactorStore`: 复权因子存储
- `CalendarStore`: 交易日历存储
- ...

### 配置

- `DataRootConfig`: 单 DATAROOT 配置，自动生成所有路径

## 使用示例

```python
from ditto_datahub.config import DataRootConfig
from ditto_datahub.stores.bars_store import BarsStore

# 初始化配置
config = DataRootConfig()

# 初始化 Store
store = BarsStore(config.data_root)

# 读取数据
df = store.read(
    dataset="stock_daily",
    sids=[1000001, 1000002],
    start_date="2024-01-01",
    end_date="2024-01-31",
)
```
```

**步骤 2: 更新设计文档**

在 `docs/design/02_data_design.md` 中添加基础层架构说明：

```markdown
## 基础层架构

### BaseStore 抽象基类

定义所有数据存储的统一接口：

- `read()`: 读取数据
- `write()`: 写入数据
- `delete()`: 删除数据

### ParquetStore

Parquet 文件存储实现：

- 支持按年分区
- 自动去重 (keep_first/keep_last)
- 支持日期范围查询

### SQLiteStore

SQLite 数据库存储实现：

- 支持单库多表
- 支持事务
- 支持 PIT 查询

### 配置系统

从多路径配置简化为单 DATAROOT 配置：

- 环境变量: `DATAROOT=/path/to/data`
- 所有路径自动生成: `market/stock/bars/daily/`, `metadata/metadata.sqlite`, 等
```

**步骤 3: 提交**

```bash
git add packages/datahub/README.md
git add docs/design/02_data_design.md
git commit -m "docs(datahub): update documentation for base layer refactoring"
```

---

## 任务 9: 创建迁移前的 Git Tag

**步骤 1: 确保所有测试通过**

```bash
pixi run -e dev ci
# 预期: 所有检查通过
```

**步骤 2: 创建 Git Tag**

```bash
git tag -a datahub-phase0-base-layer-complete -m "完成基础层重构：BaseStore、ParquetStore、SQLiteStore、DataRootConfig"
git push origin datahub-phase0-base-layer-complete
```

---

## 验收标准

### 功能验收

- [ ] BaseStore 抽象基类定义完整
- [ ] ParquetStore 实现通过所有测试
- [ ] SQLiteStore 实现通过所有测试
- [ ] DataRootConfig 能够生成所有必要路径
- [ ] BarsStore 成功迁移到 ParquetStore
- [ ] SecurityStore 保持向后兼容
- [ ] 依赖注入配置更新完成

### 测试验收

- [ ] 新增测试覆盖率 ≥ 80%
- [ ] 所有现有测试通过
- [ ] 集成测试通过

### 文档验收

- [ ] README 更新完成
- [ ] 设计文档更新完成
- [ ] API 文档完整

### 代码质量

- [ ] Pyright 类型检查通过 (strict)
- [ ] Ruff 代码检查通过
- [ ] Pre-commit hooks 通过

---

## 依赖关系

### 前置依赖

无（这是第一个阶段）

### 后续依赖

- Phase 1: Metadata 域重构（依赖 BaseStore 和 DataRootConfig）
- Phase 2: Market 域重构（依赖 BaseStore 和 DataRootConfig）

---

## 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 现有 Store 迁移破坏功能 | 高 | 中 | 充分测试，保持接口兼容 |
| 配置变更导致环境失效 | 高 | 低 | 保留旧配置作为后备 |
| 测试覆盖不足 | 中 | 低 | TDD 开发，覆盖率 ≥ 80% |

---

## 预计时间

- 任务 1-3: 2-3 天（BaseStore、ParquetStore、SQLiteStore）
- 任务 4: 1 天（配置系统重构）
- 任务 5-6: 2 天（迁移现有 Store）
- 任务 7-9: 1 天（依赖注入、文档、验收）

**总计: 约 6-7 个工作日**

---

## 实施记录

### 完成状态

**状态**: ✅ 已完成
**完成日期**: 2026-01-27
**分支**: feature/datahub-phase0-base-layer

### 实施摘要

所有 9 个任务已完成：

1. ✅ BaseStore 抽象基类 - 定义统一的 read/write/delete 接口
2. ✅ ParquetStore 基类 - Parquet 文件存储，支持按年分区、自动去重
3. ✅ SQLiteStore 基类 - SQLite 数据库存储，支持事务、PIT 查询
4. ✅ DataRootConfig - 单 DATA_ROOT 配置，自动生成所有路径
5. ✅ BarsStore 迁移 - 继承 ParquetStore
6. ✅ SecurityStore 更新 - 保持兼容性
7. ✅ 依赖注入配置 - 更新 Provider 使用 DataRootConfig
8. ✅ 清理和文档更新
9. ✅ Git Tag 创建

### Code Review 修复记录

在 PR #41 审查过程中发现并修复了以下问题：

| 问题 | 严重程度 | 修复内容 |
|------|----------|----------|
| TYPE_CHECKING 延迟导入 | P0 (100分) | 移除 `sqlite_store.py` 中对 `collections.abc.Sequence` 的 TYPE_CHECKING 延迟导入，改为直接导入 |
| YearlyPartition 开放式范围数据丢失 | P1 (85分) | 修复开放式日期范围（只有 start 或 end）返回空列表，依赖 Polars 谓词下推过滤，避免遗漏数据 |
| KEEP_FIRST 逻辑错误 | P1 (75分) | 在 `parquet_store.py` 合并路径添加批次去重，防止笛卡尔积 |
| 合并路径批次去重缺失 | P2 (60分) | 同上，确保与非合并路径行为一致 |
| 配置迁移不完整 | P2 (50分) | 将 `FileStorageSettings` 和 `DatabaseSettings` 迁移到 `DataRootConfig`，添加通用路径属性 |

### 测试更新

- 更新 `test_partition_strategy.py` 以匹配新的开放式范围行为
- 所有测试通过（单元测试、集成测试）

### 相关 Commit

- `e6eaafa` feat(datahub): implement PartitionStrategy and predicate pushdown
- `4a25a24` fix(datahub): 修复测试中的 write() 调用
- `e620756` docs(datahub): update documentation for base layer refactoring
- `5c2cc23` refactor(datahub): update providers to use DataRootConfig
- `ae5ec81` refactor(datahub): update SecurityStore doc for future SQLiteStore migration
