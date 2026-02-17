# DataHub Store 层存储结构设计

> 创建日期: 2026-01-24
> 版本: v1.0
> 状态: 设计草案

> **目的**: 设计 DataHub Store 层的统一存储架构，支持 Parquet 和 SQLite 两种存储格式，提供高效的数据访问能力。

---

## 一、设计背景

### 1.1 Store 层职责

| 职责 | 说明 | 示例 |
|------|------|------|
| **纯数据访问** | 文件读写，无业务逻辑 | Parquet 读取、SQLite 查询 |
| **格式适配** | 统一接口，适配不同存储 | ParquetStore、SQLiteStore |
| **性能优化** | 分区、索引、压缩 | 年度分区、谓词下推 |
| **数据一致性** | 事务、原子写入 | SQLite 事务、Parquet 原子替换 |

### 1.2 存储格式选择

| 数据类型 | 存储格式 | 原因 |
|---------|---------|------|
| **时序数据** | Parquet | 列式存储、压缩率高、支持谓词下推 |
| **元数据** | SQLite | 事务支持、索引、复杂查询 |
| **配置数据** | SQLite | 结构化查询、关系型约束 |
| **特征/因子** | Parquet | 列式存储、版本管理友好 |

### 1.3 设计目标

| 目标 | 说明 |
|------|------|
| **统一接口** | 所有 Store 实现相同的基础接口 |
| **类型安全** | 明确的 Schema 定义和类型约束 |
| **高性能** | 分区策略、索引优化、并行读取 |
| **可扩展** | 易于添加新的存储格式 |
| **可测试** | 接口抽象，易于 Mock |

---

## 二、Store 层架构

### 2.1 架构层次

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         QueryService 层                                  │
│                    （业务编排、能力组合）                                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Store 层                                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    BaseStore（基类）                               │  │
│  │                                                                  │  │
│  │  - get_data(): 读取数据                                           │  │
│  │  - write_data(): 写入数据                                          │  │
│  │  - query(): 通用查询接口                                           │  │
│  │  - count(): 统计行数                                               │  │
│  │  - exists(): 检查存在性                                            │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│           ┌──────────────────┼──────────────────┐                      │
│           ▼                  ▼                  ▼                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │ ParquetStore │  │ SQLiteStore  │  │  MemoryStore │  (可选)          │
│  │              │  │              │  │              │                  │
│  │ - 分区管理    │  │ - 连接池     │  │ - 缓存       │                  │
│  │ - 压缩       │  │ - 事务       │  │ - 测试支持   │                  │
│  │ - 谓词下推   │  │ - 索引       │  │              │                  │
│  └──────────────┘  └──────────────┘  └──────────────┘                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          物理存储层                                       │
├─────────────────────────────────────────────────────────────────────────┤
│  data_root/                                                             │
│  ├── market/stock/bars/daily/{year}.parquet                            │
│  ├── metadata/security/securities.sqlite                               │
│  └── ...                                                                │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
packages/datahub/src/ditto_datahub/
├── stores/
│   ├── __init__.py
│   ├── base_store.py                    # Store 基类
│   │
│   ├── parquet/                         # Parquet 存储
│   │   ├── __init__.py
│   │   ├── parquet_store.py             # Parquet Store 基类
│   │   ├── partition_strategy.py        # 分区策略
│   │   ├── compression.py               # 压缩策略
│   │   └── schema.py                    # Schema 定义
│   │
│   ├── sqlite/                          # SQLite 存储
│   │   ├── __init__.py
│   │   ├── sqlite_store.py              # SQLite Store 基类
│   │   ├── connection_pool.py           # 连接池
│   │   ├── transaction.py               # 事务管理
│   │   └── schema.py                    # 表结构定义
│   │
│   └── utils/                           # 工具类
│       ├── path_resolver.py             # 路径解析
│       ├── file_lock.py                 # 文件锁
│       └── io_utils.py                  # IO 工具
│
└── domains/
    └── {domain}/
        └── {subdomain}/
            └── {name}_store.py          # 具体实现
```

---

## 三、基类设计

### 3.1 BaseStore 接口

```python
# stores/base_store.py
"""
Store 层基类

职责：
- 定义统一的存储接口
- 提供通用的数据访问能力
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypeVar
import polars as pl

T = TypeVar("T", bound=pl.DataFrame)


class BaseStore(ABC):
    """
    Store 基类

    所有 Store 必须实现的接口：
    - get_data(): 读取数据
    - write_data(): 写入数据
    - query(): 通用查询
    - count(): 统计行数
    - exists(): 检查存在性
    """

    def __init__(self, base_path: Path):
        """
        初始化 Store

        Args:
            base_path: 数据存储的基础路径
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    # ============ 必须实现的抽象方法 ============

    @abstractmethod
    async def get_data(
        self,
        filters: dict[str, Any] | None = None,
        columns: list[str] | None = None,
        **kwargs,
    ) -> pl.DataFrame:
        """
        获取数据

        Args:
            filters: 过滤条件
            columns: 需要的列（列剪裁）
            **kwargs: 其他参数

        Returns:
            DataFrame
        """
        pass

    @abstractmethod
    async def write_data(
        self,
        data: pl.DataFrame,
        mode: str = "append",  # append | overwrite | replace
        **kwargs,
    ) -> None:
        """
        写入数据

        Args:
            data: 要写入的数据
            mode: 写入模式
                - append: 追加数据
                - overwrite: 覆盖整个数据集
                - replace: 替换匹配的数据
            **kwargs: 其他参数
        """
        pass

    # ============ 可选实现的通用方法 ============

    async def query(
        self,
        filters: dict[str, Any] | None = None,
        columns: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        **kwargs,
    ) -> pl.DataFrame:
        """
        通用查询接口

        Args:
            filters: 过滤条件
            columns: 需要的列
            limit: 返回行数限制
            offset: 偏移量

        Returns:
            DataFrame
        """
        df = await self.get_data(filters=filters, columns=columns, **kwargs)

        if limit is not None:
            df = df.slice(offset, limit)

        return df

    async def count(
        self,
        filters: dict[str, Any] | None = None,
        **kwargs,
    ) -> int:
        """
        统计行数

        Args:
            filters: 过滤条件

        Returns:
            行数
        """
        df = await self.get_data(filters=filters, **kwargs)
        return df.height

    async def exists(
        self,
        filters: dict[str, Any],
        **kwargs,
    ) -> bool:
        """
        检查数据是否存在

        Args:
            filters: 过滤条件

        Returns:
            是否存在
        """
        count = await self.count(filters=filters, **kwargs)
        return count > 0

    async def get_distinct(
        self,
        column: str,
        filters: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[Any]:
        """
        获取列的唯一值

        Args:
            column: 列名
            filters: 过滤条件

        Returns:
            唯一值列表
        """
        df = await self.get_data(filters=filters, columns=[column], **kwargs)
        return df[column].unique().to_list()

    async def get_schema(self) -> dict[str, str]:
        """
        获取数据 Schema

        Returns:
            字典：{列名: 数据类型}
        """
        # 默认实现：读取少量数据推断 Schema
        df = await self.get_data(limit=1)
        return {col: str(df[col].dtype) for col in df.columns}
```

---

## 四、Parquet Store 设计

### 4.1 ParquetStore 基类

```python
# stores/parquet/parquet_store.py
"""
Parquet Store 实现

职责：
- Parquet 文件读写
- 分区管理
- 谓词下推优化
- 压缩策略
"""

from pathlib import Path
from typing import Any
import polars as pl
from pydantic import BaseModel

from ditto_datahub.stores.base_store import BaseStore
from ditto_datahub.stores.parquet.partition_strategy import PartitionStrategy
from ditto_datahub.stores.parquet.compression import CompressionStrategy


class ParquetStoreConfig(BaseModel):
    """Parquet Store 配置"""
    base_path: Path
    partition_strategy: str = "year"  # year | month | day | none
    compression: str = "snappy"       # snappy | gzip | brotli | lz4
    row_group_size: int = 64 * 1024   # 64KB (Parquet 默认)
    data_pagesize: int = 1024 * 1024  # 1MB


class ParquetStore(BaseStore):
    """
    Parquet Store 实现

    特点：
    - 支持分区策略（按年/月/日）
    - 支持多种压缩算法
    - 自动谓词下推优化
    - 并行读取优化
    """

    def __init__(
        self,
        base_path: Path,
        partition_strategy: PartitionStrategy,
        compression: CompressionStrategy,
    ):
        super().__init__(base_path)
        self.partition_strategy = partition_strategy
        self.compression = compression

    async def get_data(
        self,
        filters: dict[str, Any] | None = None,
        columns: list[str] | None = None,
        **kwargs,
    ) -> pl.DataFrame:
        """
        获取 Parquet 数据

        优化：
        - 分区剪裁（只读取相关分区文件）
        - 谓词下推（Parquet 层过滤）
        - 列剪裁（只读取需要的列）
        """
        # 1. 确定需要读取的分区文件
        file_paths = self._get_partition_files(filters)

        if not file_paths:
            return pl.DataFrame()

        # 2. 构建 Polars 读取参数
        read_kwargs = {
            "columns": columns,
            "use_pyarrow": True,  # 使用 PyArrow 引擎（更好的谓词下推）
        }

        # 3. 添加谓词下推过滤器
        parquet_filters = self._build_parquet_filters(filters)
        if parquet_filters:
            read_kwargs["pyarrow_filters"] = parquet_filters

        # 4. 并行读取多个文件
        dfs = []
        for file_path in file_paths:
            df = pl.read_parquet(file_path, **read_kwargs)
            dfs.append(df)

        # 5. 合并数据
        if dfs:
            result = pl.concat(dfs)
        else:
            result = pl.DataFrame()

        # 6. 应用剩余过滤条件（无法下推的部分）
        if filters:
            result = self._apply_filters(result, filters)

        return result

    async def write_data(
        self,
        data: pl.DataFrame,
        mode: str = "append",
        **kwargs,
    ) -> None:
        """
        写入 Parquet 数据

        特点：
        - 按分区写入
        - 原子性保证（先写临时文件，再重命名）
        - 压缩优化
        """
        if mode not in ["append", "overwrite", "replace"]:
            raise ValueError(f"Unsupported mode: {mode}")

        # 1. 按分区分组
        partition_groups = self.partition_strategy.group_by_partition(data)

        # 2. 写入每个分区
        for partition_key, partition_data in partition_groups.items():
            file_path = self._get_partition_path(partition_key)

            if mode == "append":
                # 追加模式：读取现有数据，合并后写入
                existing_data = await self._read_partition(file_path)
                if not existing_data.is_empty():
                    partition_data = pl.concat([existing_data, partition_data])

            # 3. 原子写入（临时文件 + 重命名）
            temp_path = file_path.with_suffix(".tmp")
            partition_data.write_parquet(
                temp_path,
                compression=self.compression.compression_level,
                pyarrow_options={
                    "compression_level": self.compression.compression_level,
                },
            )
            temp_path.rename(file_path)

    def _get_partition_files(
        self,
        filters: dict[str, Any] | None,
    ) -> list[Path]:
        """
        获取需要读取的分区文件

        优化：分区剪裁
        """
        # 根据过滤条件确定需要读取的分区
        partition_keys = self.partition_strategy.get_partitions_from_filters(filters)

        file_paths = []
        for key in partition_keys:
            file_path = self._get_partition_path(key)
            if file_path.exists():
                file_paths.append(file_path)

        return file_paths

    def _build_parquet_filters(
        self,
        filters: dict[str, Any] | None,
    ) -> list[tuple] | None:
        """
        构建 Parquet 谓词下推过滤器

        Returns:
            Parquet 过滤器列表或 None

        Examples:
            [("sid", "==", 1000001), ("trade_date", ">=", "2024-01-01")]
        """
        if not filters:
            return None

        parquet_filters = []
        for column, condition in filters.items():
            # 转换为 Parquet 过滤器格式
            # 实现略...
            pass

        return parquet_filters

    def _get_partition_path(self, partition_key: Any) -> Path:
        """获取分区文件路径"""
        filename = self.partition_strategy.get_filename(partition_key)
        return self.base_path / filename

    async def _read_partition(self, file_path: Path) -> pl.DataFrame:
        """读取单个分区文件"""
        if not file_path.exists():
            return pl.DataFrame()

        return pl.read_parquet(file_path)

    def _apply_filters(
        self,
        df: pl.DataFrame,
        filters: dict[str, Any],
    ) -> pl.DataFrame:
        """应用过滤条件（无法下推的部分）"""
        for column, condition in filters.items():
            if column not in df.columns:
                continue

            # 应用过滤
            df = df.filter(pl.col(column) == condition)

        return df
```

### 4.2 分区策略

```python
# stores/parquet/partition_strategy.py
"""
Parquet 分区策略

职责：
- 定义分区规则
- 计算分区键
- 分区文件路径管理
"""

from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Any
import polars as pl


class PartitionStrategy(ABC):
    """分区策略基类"""

    @abstractmethod
    def get_partition_key(self, row: dict[str, Any]) -> Any:
        """计算单行数据的分区键"""
        pass

    @abstractmethod
    def get_partitions_from_filters(
        self,
        filters: dict[str, Any] | None,
    ) -> list[Any]:
        """根据过滤条件获取需要读取的分区"""
        pass

    @abstractmethod
    def get_filename(self, partition_key: Any) -> str:
        """获取分区文件名"""
        pass

    def group_by_partition(
        self,
        df: pl.DataFrame,
    ) -> dict[Any, pl.DataFrame]:
        """按分区分组数据"""
        if df.is_empty():
            return {}

        # 添加分区键列
        df_with_key = df.with_columns(
            pl.struct(df.columns).map_elements(self._get_partition_key_from_row).alias("_partition_key")
        )

        # 按分区键分组
        result = {}
        for key, group_df in df_with_key.groupby("_partition_key"):
            # 移除分区键列
            result[key] = group_df.drop("_partition_key")

        return result

    def _get_partition_key_from_row(self, row: dict) -> Any:
        """从行数据获取分区键"""
        return self.get_partition_key(row)


class YearlyPartition(PartitionStrategy):
    """
    按年分区

    适用场景：
    - 日线数据
    - 数据量中等
    - 查询通常按年份范围
    """

    def __init__(self, date_column: str = "trade_date"):
        self.date_column = date_column

    def get_partition_key(self, row: dict[str, Any]) -> int:
        """获取年份作为分区键"""
        trade_date = row.get(self.date_column)
        if isinstance(trade_date, date):
            return trade_date.year
        elif isinstance(trade_date, str):
            return int(trade_date[:4])
        else:
            raise ValueError(f"Invalid date type: {type(trade_date)}")

    def get_partitions_from_filters(
        self,
        filters: dict[str, Any] | None,
    ) -> list[int]:
        """根据日期过滤条件确定需要读取的年份"""
        if not filters or self.date_column not in filters:
            # 无过滤条件，返回所有可能的分区
            return self._get_all_partitions()

        # 从过滤条件提取年份范围
        filter_value = filters[self.date_column]
        # 实现略...
        return [2024]  # 示例

    def get_filename(self, partition_key: int) -> str:
        """获取分区文件名"""
        return f"{partition_key}.parquet"

    def _get_all_partitions(self) -> list[int]:
        """获取所有可用的分区"""
        # 扫描目录，返回所有年份
        # 实现略...
        return list(range(2020, 2025))


class MonthlyPartition(PartitionStrategy):
    """
    按月分区

    适用场景：
    - 高频数据（分钟级）
    - 数据量较大
    - 需要更细粒度的分区
    """

    def __init__(self, date_column: str = "trade_date"):
        self.date_column = date_column

    def get_partition_key(self, row: dict[str, Any]) -> str:
        """获取年月作为分区键"""
        trade_date = row.get(self.date_column)
        if isinstance(trade_date, date):
            return f"{trade_date.year}-{trade_date.month:02d}"
        elif isinstance(trade_date, str):
            return trade_date[:7]  # "2024-01"
        else:
            raise ValueError(f"Invalid date type: {type(trade_date)}")

    def get_partitions_from_filters(
        self,
        filters: dict[str, Any] | None,
    ) -> list[str]:
        """根据日期过滤条件确定需要读取的月份"""
        # 实现略...
        return ["2024-01", "2024-02"]

    def get_filename(self, partition_key: str) -> str:
        """获取分区文件名"""
        return f"{partition_key}.parquet"


class NoPartition(PartitionStrategy):
    """
    不分区

    适用场景：
    - 数据量小
    - 查询通常需要全表扫描
    """

    def get_partition_key(self, row: dict[str, Any]) -> str:
        """固定分区键"""
        return "all"

    def get_partitions_from_filters(
        self,
        filters: dict[str, Any] | None,
    ) -> list[str]:
        """返回唯一分区"""
        return ["all"]

    def get_filename(self, partition_key: str) -> str:
        """获取文件名"""
        return "data.parquet"
```

### 4.3 压缩策略

```python
# stores/parquet/compression.py
"""
Parquet 压缩策略

职责：
- 定义压缩算法
- 平衡压缩比和性能
"""

from enum import Enum


class CompressionType(str, Enum):
    """压缩类型"""
    SNAPPY = "snappy"
    GZIP = "gzip"
    BROTLI = "brotli"
    LZ4 = "lz4"
    ZSTD = "zstd"


class CompressionStrategy:
    """
    压缩策略

    压缩算法对比：
    - Snappy: 压缩比低，速度快（默认推荐）
    - Gzip: 压缩比中等，速度中等
    - Brotli: 压缩比高，速度慢
    - LZ4: 压缩比低，速度最快
    - ZSTD: 压缩比高，速度快（推荐）
    """

    def __init__(
        self,
        compression_type: CompressionType = CompressionType.SNAPPY,
        compression_level: int | None = None,
    ):
        self.compression_type = compression_type
        self.compression_level = compression_level or self._default_level()

    def _default_level(self) -> int:
        """获取默认压缩级别"""
        level_map = {
            CompressionType.SNAPPY: None,  # Snappy 无级别
            CompressionType.GZIP: 6,
            CompressionType.BROTLI: 4,     # 0-11，4 是平衡点
            CompressionType.LZ4: None,     # LZ4 无级别
            CompressionType.ZSTD: 3,       # 1-22，3 是平衡点
        }
        return level_map[self.compression_type]

    @property
    def compression_level(self) -> int | None:
        """获取压缩级别"""
        return self.compression_level
```

---

## 五、SQLite Store 设计

### 5.1 SQLiteStore 基类

```python
# stores/sqlite/sqlite_store.py
"""
SQLite Store 实现

职责：
- SQLite 数据库读写
- 连接池管理
- 事务支持
- 索引优化
"""

from pathlib import Path
from typing import Any
import polars as pl
import sqlite3
from contextlib import asynccontextmanager

from ditto_datahub.stores.base_store import BaseStore
from ditto_datahub.stores.sqlite.connection_pool import ConnectionPool
from ditto_datahub.stores.sqlite.schema import TableSchema


class SQLiteStoreConfig(BaseModel):
    """SQLite Store 配置"""
    base_path: Path
    table_name: str
    pool_size: int = 5
    enable_wal: bool = True          # WAL 模式（提高并发）
    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"


class SQLiteStore(BaseStore):
    """
    SQLite Store 实现

    特点：
    - 连接池管理
    - 事务支持
    - 索引优化
    - 类型转换（Polars ↔ SQLite）
    """

    def __init__(
        self,
        base_path: Path,
        table_name: str,
        schema: TableSchema,
        pool_size: int = 5,
    ):
        # SQLite 文件路径
        db_path = base_path / f"{table_name}.sqlite"
        super().__init__(db_path)

        self.table_name = table_name
        self.schema = schema

        # 初始化连接池
        self.connection_pool = ConnectionPool(
            db_path=db_path,
            pool_size=pool_size,
        )

        # 初始化表结构
        self._init_table()

    async def get_data(
        self,
        filters: dict[str, Any] | None = None,
        columns: list[str] | None = None,
        **kwargs,
    ) -> pl.DataFrame:
        """
        获取 SQLite 数据

        优化：
        - 索引扫描
        - 列剪裁
        - LIMIT 优化
        """
        # 1. 构建 SQL 查询
        column_list = columns or ["*"]
        column_str = ", ".join(column_list)

        sql = f"SELECT {column_str} FROM {self.table_name}"

        # 2. 添加 WHERE 条件
        where_clauses, params = self._build_where_clause(filters)
        if where_clauses:
            sql += f" WHERE {where_clauses}"

        # 3. 执行查询
        async with self.connection_pool.get_connection() as conn:
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            columns_desc = [desc[0] for desc in cursor.description]

        # 4. 转换为 Polars DataFrame
        df = pl.DataFrame(
            data=rows,
            schema=columns_desc,
            orient="row",
        )

        return df

    async def write_data(
        self,
        data: pl.DataFrame,
        mode: str = "append",
        **kwargs,
    ) -> None:
        """
        写入 SQLite 数据

        特点：
        - 批量插入优化
        - 事务支持
        - 冲突处理
        """
        if mode not in ["append", "overwrite", "replace"]:
            raise ValueError(f"Unsupported mode: {mode}")

        if mode == "overwrite":
            # 覆盖模式：清空表
            await self._truncate_table()

        # 批量插入
        async with self.connection_pool.get_connection() as conn:
            # 开始事务
            await conn.execute("BEGIN TRANSACTION")

            try:
                # 构建插入 SQL
                columns = data.columns
                placeholders = ", ".join(["?"] * len(columns))
                column_str = ", ".join(columns)

                sql = f"""
                    INSERT OR REPLACE INTO {self.table_name}
                    ({column_str})
                    VALUES ({placeholders})
                """

                # 转换数据为元组列表
                rows = data.rows()

                # 批量插入
                await conn.executemany(sql, rows)

                # 提交事务
                await conn.commit()

            except Exception as e:
                # 回滚事务
                await conn.rollback()
                raise

    async def count(
        self,
        filters: dict[str, Any] | None = None,
        **kwargs,
    ) -> int:
        """统计行数（优化：使用 COUNT(*)）"""
        sql = f"SELECT COUNT(*) FROM {self.table_name}"

        where_clauses, params = self._build_where_clause(filters)
        if where_clauses:
            sql += f" WHERE {where_clauses}"

        async with self.connection_pool.get_connection() as conn:
            cursor = await conn.execute(sql, params)
            result = await cursor.fetchone()

        return result[0] if result else 0

    def _init_table(self) -> None:
        """初始化表结构"""
        # 创建表 SQL
        create_sql = self.schema.create_table_sql(self.table_name)

        # 创建索引 SQL
        index_sqls = self.schema.create_index_sqls(self.table_name)

        # 执行初始化（同步操作，只需执行一次）
        with sqlite3.connect(self.base_path) as conn:
            conn.execute(create_sql)
            for index_sql in index_sqls:
                try:
                    conn.execute(index_sql)
                except sqlite3.OperationalError:
                    # 索引可能已存在
                    pass

    async def _truncate_table(self) -> None:
        """清空表"""
        sql = f"DELETE FROM {self.table_name}"

        async with self.connection_pool.get_connection() as conn:
            await conn.execute(sql)

    def _build_where_clause(
        self,
        filters: dict[str, Any] | None,
    ) -> tuple[str, list]:
        """
        构建 WHERE 子句

        Returns:
            (where_clause, params)
        """
        if not filters:
            return "", []

        clauses = []
        params = []

        for column, value in filters.items():
            if isinstance(value, (list, tuple)):
                # IN 查询
                placeholders = ", ".join(["?"] * len(value))
                clauses.append(f"{column} IN ({placeholders})")
                params.extend(value)
            else:
                # 等值查询
                clauses.append(f"{column} = ?")
                params.append(value)

        where_clause = " AND ".join(clauses)
        return where_clause, params
```

### 5.2 连接池

```python
# stores/sqlite/connection_pool.py
"""
SQLite 连接池

职责：
- 管理数据库连接
- 提高并发性能
"""

import asyncio
import sqlite3
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncIterator


class ConnectionPool:
    """
    SQLite 连接池

    特点：
    - 异步连接管理
    - 连接复用
    - 自动 WAL 模式
    """

    def __init__(
        self,
        db_path: Path,
        pool_size: int = 5,
    ):
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool: asyncio.Queue[sqlite3.Connection] = asyncio.Queue(maxsize=pool_size)

        # 初始化连接池
        self._init_pool()

    def _init_pool(self) -> None:
        """初始化连接池"""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            self._pool.put_nowait(conn)

    def _create_connection(self) -> sqlite3.Connection:
        """创建新连接"""
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
        )

        # 启用 WAL 模式（提高并发）
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        return conn

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[sqlite3.Connection]:
        """
        获取连接（上下文管理器）

        Usage:
            async with pool.get_connection() as conn:
                cursor = await conn.execute("SELECT ...")
                ...
        """
        # 从池中获取连接
        conn = await self._pool.get()

        try:
            yield conn
        finally:
            # 归还连接到池
            self._pool.put_nowait(conn)

    async def close(self) -> None:
        """关闭所有连接"""
        while not self._pool.empty():
            conn = await self._pool.get()
            conn.close()
```

### 5.3 Schema 定义

```python
# stores/sqlite/schema.py
"""
SQLite 表结构定义

职责：
- 定义表结构
- 生成创建表和索引的 SQL
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from enum import Enum


class ColumnType(str, Enum):
    """SQLite 列类型"""
    INTEGER = "INTEGER"
    REAL = "REAL"
    TEXT = "TEXT"
    BLOB = "BLOB"


@dataclass
class ColumnDef:
    """列定义"""
    name: str
    type: ColumnType
    primary_key: bool = False
    not_null: bool = False
    unique: bool = False
    default: Any = None


@dataclass
class IndexDef:
    """索引定义"""
    columns: list[str]
    unique: bool = False
    name: str | None = None


class TableSchema(ABC):
    """表结构基类"""

    @property
    @abstractmethod
    def table_name(self) -> str:
        """表名"""
        pass

    @property
    @abstractmethod
    def columns(self) -> list[ColumnDef]:
        """列定义"""
        pass

    @property
    def indexes(self) -> list[IndexDef]:
        """索引定义（可选）"""
        return []

    def create_table_sql(self, table_name: str) -> str:
        """生成创建表的 SQL"""
        columns_sql = []

        for col in self.columns:
            col_sql = f"{col.name} {col.type.value}"

            if col.primary_key:
                col_sql += " PRIMARY KEY"
            if col.not_null:
                col_sql += " NOT NULL"
            if col.unique:
                col_sql += " UNIQUE"
            if col.default is not None:
                col_sql += f" DEFAULT {col.default}"

            columns_sql.append(col_sql)

        columns_str = ",\n    ".join(columns_sql)

        sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {columns_str}
            )
        """

        return sql.strip()

    def create_index_sqls(self, table_name: str) -> list[str]:
        """生成创建索引的 SQL"""
        sqls = []

        for index in self.indexes:
            index_name = index.name or f"idx_{table_name}_{'_'.join(index.columns)}"
            unique = "UNIQUE " if index.unique else ""
            columns_str = ", ".join(index.columns)

            sql = f"""
                CREATE {unique}INDEX IF NOT EXISTS {index_name}
                ON {table_name} ({columns_str})
            """

            sqls.append(sql.strip())

        return sqls
```

---

## 六、具体 Store 实现

### 6.1 BarsStore（Parquet）

```python
# domains/market/stock/bars/bars_store.py
"""
股票行情数据 Store（Parquet 实现）

职责：
- 日线行情数据读写
- 年度分区
- Snappy 压缩
"""

from pathlib import Path
from typing import date
import polars as pl

from ditto_datahub.stores.parquet.parquet_store import ParquetStore, ParquetStoreConfig
from ditto_datahub.stores.parquet.partition_strategy import YearlyPartition
from ditto_datahub.stores.parquet.compression import CompressionStrategy, CompressionType


class BarsStore(ParquetStore):
    """
    股票行情数据 Store

    存储路径：data_root/market/stock/bars/daily/{year}.parquet

    Schema:
        sid: Int32              # 标的 ID
        trade_date: Date        # 交易日期
        open: Float64           # 开盘价
        high: Float64           # 最高价
        low: Float64            # 最低价
        close: Float64          # 收盘价
        vol: Int64              # 成交量（股）
        amount: Float64         # 成交额（元）
    """

    def __init__(
        self,
        base_path: Path = Path("data_root/market/stock/bars/daily"),
    ):
        # 初始化分区策略（按年分区）
        partition_strategy = YearlyPartition(date_column="trade_date")

        # 初始化压缩策略（Snappy，平衡性能和压缩比）
        compression = CompressionStrategy(
            compression_type=CompressionType.SNAPPY,
        )

        super().__init__(
            base_path=base_path,
            partition_strategy=partition_strategy,
            compression=compression,
        )

    async def get_bars(
        self,
        sids: list[int] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pl.DataFrame:
        """
        获取行情数据

        Args:
            sids: 标的 ID 列表
            start_date: 起始日期
            end_date: 结束日期

        Returns:
            DataFrame
        """
        # 构建过滤条件
        filters = {}

        if sids:
            filters["sid"] = sids

        if start_date:
            filters["trade_date"] = f">={start_date}"

        if end_date:
            # 处理范围过滤
            if "trade_date" in filters:
                # 已有起始日期，需要改为范围
                filters["trade_date"] = (start_date, end_date)
            else:
                filters["trade_date"] = f"<={end_date}"

        # 调用基类方法
        return await self.get_data(filters=filters)

    async def get_adj_factors(
        self,
        sids: list[int] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pl.DataFrame:
        """
        获取复权因子数据

        存储路径：data_root/market/stock/bars/adj/{year}.parquet

        Schema:
            sid: Int32
            trade_date: Date
            adj_factor: Float64
        """
        adj_path = self.base_path.parent / "adj"
        adj_store = AdjFactorStore(base_path=adj_path)

        return await adj_store.get_data(
            filters={
                "sid": sids,
                "trade_date": self._build_date_filter(start_date, end_date),
            }
        )

    def _build_date_filter(
        self,
        start_date: date | None,
        end_date: date | None,
    ) -> Any:
        """构建日期过滤条件"""
        if start_date and end_date:
            return (start_date, end_date)
        elif start_date:
            return f">={start_date}"
        elif end_date:
            return f"<={end_date}"
        else:
            return None


class AdjFactorStore(ParquetStore):
    """复权因子 Store"""

    def __init__(
        self,
        base_path: Path = Path("data_root/market/stock/bars/adj"),
    ):
        partition_strategy = YearlyPartition(date_column="trade_date")
        compression = CompressionStrategy(CompressionType.SNAPPY)

        super().__init__(
            base_path=base_path,
            partition_strategy=partition_strategy,
            compression=compression,
        )
```

### 6.2 SecurityStore（SQLite）

```python
# domains/metadata/security/security_store.py
"""
证券元数据 Store（SQLite 实现）

职责：
- 证券基本信息读写
- 主键索引
- ts_code 和 symbol 索引
"""

from pathlib import Path
from typing import Any
import polars as pl

from ditto_datahub.stores.sqlite.sqlite_store import SQLiteStore, SQLiteStoreConfig
from ditto_datahub.stores.sqlite.schema import TableSchema, ColumnDef, ColumnType, IndexDef


class SecuritySchema(TableSchema):
    """证券信息表结构"""

    @property
    def table_name(self) -> str:
        return "securities"

    @property
    def columns(self) -> list[ColumnDef]:
        return [
            ColumnDef("sid", ColumnType.INTEGER, primary_key=True),
            ColumnDef("ts_code", ColumnType.TEXT, not_null=True, unique=True),
            ColumnDef("symbol", ColumnType.TEXT, not_null=True),
            ColumnDef("name", ColumnType.TEXT, not_null=True),
            ColumnDef("market", ColumnType.TEXT, not_null=True),  # SH/SZ
            ColumnDef("list_date", ColumnType.TEXT),               # YYYYMMDD
            ColumnDef("delist_date", ColumnType.TEXT),
            ColumnDef("asset_type", ColumnType.TEXT),              # stock/etf/index
        ]

    @property
    def indexes(self) -> list[IndexDef]:
        return [
            IndexDef(["ts_code"], unique=True),
            IndexDef(["symbol"]),
            IndexDef(["asset_type"]),
            IndexDef(["market"]),
        ]


class SecurityStore(SQLiteStore):
    """
    证券元数据 Store

    存储路径：data_root/metadata/security/securities.sqlite

    Schema: 见 SecuritySchema
    """

    def __init__(
        self,
        base_path: Path = Path("data_root/metadata/security"),
    ):
        schema = SecuritySchema()

        super().__init__(
            base_path=base_path,
            table_name=schema.table_name,
            schema=schema,
            pool_size=5,
        )

    async def get_info(self, sids: list[int]) -> pl.DataFrame:
        """
        获取证券信息

        Args:
            sids: 标的 ID 列表

        Returns:
            DataFrame with columns:
            - sid, ts_code, symbol, name, market, list_date, ...
        """
        return await self.get_data(filters={"sid": sids})

    async def get_by_ts_code(self, ts_codes: list[str]) -> pl.DataFrame:
        """根据 ts_code 查询"""
        return await self.get_data(filters={"ts_code": ts_codes})

    async def get_by_symbol(self, symbols: list[str]) -> pl.DataFrame:
        """根据 symbol 查询"""
        return await self.get_data(filters={"symbol": symbols})

    async def get_by_market(self, market: str) -> pl.DataFrame:
        """根据市场查询"""
        return await self.get_data(filters={"market": market})
```

### 6.3 IdentityStore（SQLite）

```python
# domains/metadata/identity/identity_store.py
"""
Identity 映射 Store（SQLite 实现）

职责：
- 多源标识符映射
- ts_code/symbol/sid 互转
"""

from pathlib import Path
from typing import Literal
import polars as pl

from ditto_datahub.stores.sqlite.sqlite_store import SQLiteStore
from ditto_datahub.stores.sqlite.schema import TableSchema, ColumnDef, ColumnType, IndexDef


class IdentitySchema(TableSchema):
    """Identity 映射表结构"""

    @property
    def table_name(self) -> str:
        return "identity_mapping"

    @property
    def columns(self) -> list[ColumnDef]:
        return [
            ColumnDef("sid", ColumnType.INTEGER, primary_key=True),
            ColumnDef("ts_code", ColumnType.TEXT, not_null=True, unique=True),
            ColumnDef("symbol", ColumnType.TEXT, not_null=True),
            ColumnDef("effective_from", ColumnType.TEXT, not_null=True),  # YYYYMMDD
            ColumnDef("effective_to", ColumnType.TEXT),                   # NULL 表示有效
        ]

    @property
    def indexes(self) -> list[IndexDef]:
        return [
            IndexDef(["ts_code"], unique=True),
            IndexDef(["symbol"]),
            IndexDef(["effective_from", "effective_to"]),
        ]


class IdentityStore(SQLiteStore):
    """
    Identity 映射 Store

    存储路径：data_root/metadata/identity/identity_mapping.sqlite

    职责：
    - ts_code ↔ symbol ↔ sid 互转
    - 支持历史版本（effective_from/effective_to）
    """

    def __init__(
        self,
        base_path: Path = Path("data_root/metadata/identity"),
    ):
        schema = IdentitySchema()

        super().__init__(
            base_path=base_path,
            table_name=schema.table_name,
            schema=schema,
            pool_size=5,
        )

    async def resolve(
        self,
        identifiers: list[int] | list[str],
        input_type: Literal["auto", "sid", "ts_code", "symbol"],
        output_type: Literal["sid", "ts_code", "symbol"],
    ) -> list[Any]:
        """
        解析 Identity

        Args:
            identifiers: 标的标识符列表
            input_type: 输入类型（auto 自动识别）
            output_type: 输出类型

        Returns:
            转换后的标识符列表

        Examples:
            >>> store = IdentityStore()
            >>> # ts_code → sid
            >>> sids = await store.resolve(["000001.SZ", "600000.SH"], "ts_code", "sid")
            >>> [1000001, 1000002]
        """
        if not identifiers:
            return []

        # 1. 确定输入列
        input_col = self._determine_input_column(identifiers, input_type)

        # 2. 构建过滤条件
        filters = {input_col: identifiers}

        # 3. 查询数据
        df = await self.get_data(
            filters=filters,
            columns=[input_col, output_type],
        )

        # 4. 提取结果（保持输入顺序）
        result_map = dict(zip(df[input_col].to_list(), df[output_type].to_list()))
        results = [result_map.get(id, None) for id in identifiers]

        return results

    def _determine_input_column(
        self,
        identifiers: list[int] | list[str],
        input_type: Literal["auto", "sid", "ts_code", "symbol"],
    ) -> str:
        """确定输入列"""
        if input_type != "auto":
            return input_type

        # 自动识别
        if all(isinstance(id, int) for id in identifiers):
            return "sid"
        elif all("." in str(id) for id in identifiers):
            return "ts_code"
        else:
            return "symbol"
```

---

## 七、性能优化策略

### 7.1 Parquet 优化

| 优化项 | 策略 | 效果 |
|--------|------|------|
| **分区策略** | 按年/月分区 | 减少扫描文件数 |
| **列剪裁** | 只读取需要的列 | 减少 I/O |
| **谓词下推** | Parquet 层过滤 | 减少数据传输 |
| **压缩** | Snappy/ZSTD | 减少存储空间 |
| **Row Group Size** | 64-128MB | 平衡扫描和并行度 |
| **统计信息** | 写入时收集 | 优化查询计划 |
| **排序** | 按键列排序 | 提高压缩比和查询性能 |

### 7.2 SQLite 优化

| 优化项 | 策略 | 效果 |
|--------|------|------|
| **索引** | 主键、唯一键、查询列 | 快速查找 |
| **WAL 模式** | 并发读写 | 提高并发性能 |
| **连接池** | 复用连接 | 减少连接开销 |
| **批量插入** | 事务 + executemany | 提高写入性能 |
| **PRAGMA 优化** | synchronous=NORMAL | 平衡性能和安全 |
| **预编译语句** | 避免重复解析 | 提高查询性能 |

---

## 八、Schema 定义规范

### 8.1 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| **表名** | 小写，下划线分隔 | `securities`, `identity_mapping` |
| **列名** | 小写，下划线分隔 | `trade_date`, `adj_factor` |
| **索引名** | `idx_{table}_{columns}` | `idx_securities_ts_code` |
| **文件名** | 小写，点分隔 | `{year}.parquet`, `data.sqlite` |

### 8.2 数据类型映射

| Polars 类型 | Parquet 类型 | SQLite 类型 | 说明 |
|-------------|--------------|-------------|------|
| `Int32` | `int32` | `INTEGER` | 32位整数 |
| `Int64` | `int64` | `INTEGER` | 64位整数 |
| `Float32` | `float` | `REAL` | 32位浮点 |
| `Float64` | `double` | `REAL` | 64位浮点 |
| `String` | `utf8` | `TEXT` | 字符串 |
| `Date` | `int32` (日期) | `TEXT` (YYYY-MM-DD) | 日期 |
| `Datetime` | `int64` (时间戳) | `TEXT` (ISO8601) | 日期时间 |
| `Boolean` | `bool` | `INTEGER` (0/1) | 布尔值 |

---

## 九、测试策略

### 9.1 单元测试

```python
# tests/unit/stores/test_bars_store.py
"""
BarsStore 单元测试
"""

import pytest
from pathlib import Path
import polars as pl
from datetime import date

from ditto_datahub.domains.market.stock.bars.bars_store import BarsStore


@pytest.fixture
def temp_store(tmp_path: Path) -> BarsStore:
    """临时 Store"""
    return BarsStore(base_path=tmp_path)


@pytest.mark.asyncio
async def test_write_and_read(temp_store: BarsStore):
    """测试写入和读取"""
    # 准备数据
    data = pl.DataFrame({
        "sid": [1000001, 1000002],
        "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
        "open": [10.0, 11.0],
        "close": [10.5, 11.5],
        "vol": [1000000, 2000000],
        "amount": [10500000.0, 23000000.0],
    })

    # 写入
    await temp_store.write_data(data)

    # 读取
    result = await temp_store.get_bars(
        sids=[1000001],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 1),
    )

    # 验证
    assert result.height == 1
    assert result["sid"][0] == 1000001
    assert result["close"][0] == 10.5


@pytest.mark.asyncio
async def test_partition_pruning(temp_store: BarsStore):
    """测试分区剪裁"""
    # 写入跨年数据
    data_2023 = pl.DataFrame({
        "sid": [1000001],
        "trade_date": [date(2023, 12, 31)],
        "close": [10.0],
    })

    data_2024 = pl.DataFrame({
        "sid": [1000001],
        "trade_date": [date(2024, 1, 1)],
        "close": [11.0],
    })

    await temp_store.write_data(data_2023)
    await temp_store.write_data(data_2024)

    # 查询 2024 年数据（应该只读取 2024.parquet）
    result = await temp_store.get_bars(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    assert result.height == 1
    assert result["close"][0] == 11.0
```

### 9.2 集成测试

```python
# tests/integration/stores/test_market_integration.py
"""
Market Store 集成测试
"""

import pytest
from pathlib import Path
import polars as pl
from datetime import date

from ditto_datahub.domains.market.stock.bars.bars_store import BarsStore
from ditto_datahub.domains.metadata.security.security_store import SecurityStore
from ditto_datahub.domains.metadata.identity.identity_store import IdentityStore


@pytest.mark.asyncio
async def test_cross_domain_query(tmp_path: Path):
    """测试跨域查询"""
    # 1. 初始化 Store
    bars_store = BarsStore(base_path=tmp_path / "bars")
    security_store = SecurityStore(base_path=tmp_path / "security")
    identity_store = IdentityStore(base_path=tmp_path / "identity")

    # 2. 写入测试数据
    # ... 略 ...

    # 3. 跨域查询：通过 ts_code 查询行情
    ts_codes = ["000001.SZ", "600000.SH"]

    # Step 1: ts_code → sid
    sids = await identity_store.resolve(ts_codes, "ts_code", "sid")

    # Step 2: 获取行情
    bars = await bars_store.get_bars(sids=sids)

    # Step 3: 获取证券信息
    securities = await security_store.get_info(sids=sids)

    # 验证
    assert len(bars) > 0
    assert len(securities) > 0
```

---

## 十、实施路线图

| 阶段 | 任务 | 优先级 |
|------|------|--------|
| **阶段 1** | 实现 BaseStore 接口 | P0 |
| **阶段 1** | 实现 ParquetStore 和分区策略 | P0 |
| **阶段 2** | 实现 SQLiteStore 和连接池 | P1 |
| **阶段 2** | 迁移现有 Accessor 到 Store | P1 |
| **阶段 3** | 性能优化和测试 | P2 |

---

## 十一、关键设计决策

| 问题 | 推荐方案 | 原因 |
|------|---------|------|
| **存储格式** | Parquet（时序）+ SQLite（元数据） | 兼顾性能和灵活性 |
| **分区策略** | 年度分区（日线） | 平衡粒度和性能 |
| **压缩算法** | Snappy（默认） | 平衡压缩比和速度 |
| **连接池** | SQLite 连接池 | 提高并发性能 |
| **索引策略** | 主键 + 唯一键 + 查询列 | 覆盖常见查询 |
| **类型转换** | Polars ↔ SQLite 自动转换 | 简化使用 |

---

**文档版本**: v1.0
**创建日期**: 2026-01-24
**状态**: 设计草案

**相关文档**:
- [2026-01-24-datahub-domain-architecture-design.md](./2026-01-24-datahub-domain-architecture-design.md)
- [2026-01-24-datahub-architecture-design.md](./2026-01-24-datahub-architecture-design.md)
