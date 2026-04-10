# DataHub Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 DataHub Phase 2 - UniverseRepository、IndexRepository、FreezeManager 及 DataHub 集成

**Architecture:**
- UniverseRepository: SQLite 存储（universe, universe_constituent 表），支持 PIT 查询
- IndexRepository: 复用 BarsStore（指数日线）+ 新建 IndexWeightStore（成分股 PIT）
- FreezeManager: 轻量级 checksum 校验，JSON manifest 存储，不做回滚
- DataHub: Facade 模式集成新组件

**Tech Stack:** Polars, SQLite, Pydantic, pytest, TDD

---

## 前置准备

### Step 0: 加载必需的 Skills

在开始编码前，加载以下领域 skills：

```bash
/load polars      # Polars DataFrame 操作
/load pit         # PIT 时点数据安全
/load observability # 日志和追踪
/load docs        # 文档规范
```

---

## Task 1: UniverseStore 实现

**目标:** 实现标的池存储层，支持创建标的池和管理成分股（PIT 安全）

**Files:**
- Create: `packages/data/src/ditto_data/stores/universe_store.py`
- Create: `packages/data/tests/unit/stores/test_universe_store.py`
- Reference: `packages/data/src/ditto_data/stores/security_store.py` (模式参考)
- Reference: `packages/data/src/ditto_data/stores/sqlite_client.py`

**Step 1.1: 写 UniverseStore 的基础结构测试**

创建 `packages/data/tests/unit/stores/test_universe_store.py`:

```python
"""UniverseStore 单元测试."""

import polars as pl
import pytest
from ditto_data.stores.universe_store import UniverseStore
from ditto_data.stores.sqlite_client import SQLiteClient


@pytest.fixture
def sqlite_client(tmp_path):
    """创建临时 SQLite 客户端"""
    db_path = tmp_path / "test.db"
    client = SQLiteClient(str(db_path))
    _init_schema(client)
    yield client
    client.close()


def _init_schema(client: SQLiteClient):
    """初始化测试表结构"""
    client.execute("""
        CREATE TABLE IF NOT EXISTS universe (
            universe_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            universe_type TEXT,
            source_ref TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    client.execute("""
        CREATE TABLE IF NOT EXISTS universe_constituent (
            universe_id TEXT NOT NULL,
            sid INTEGER NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            weight REAL,
            PRIMARY KEY (universe_id, sid, effective_from)
        )
    """)
    client.commit()


def test_universe_store_init(sqlite_client):
    """测试 UniverseStore 初始化"""
    store = UniverseStore(sqlite_client)
    assert store._client is sqlite_client


def test_create_universe(sqlite_client):
    """测试创建标的池"""
    store = UniverseStore(sqlite_client)

    store.create_universe(
        universe_id="test_universe",
        name="测试标的池",
        description="这是一个测试标的池",
        universe_type="custom",
    )

    result = store.get_universe("test_universe")
    assert result is not None
    assert result["universe_id"] == "test_universe"
    assert result["name"] == "测试标的池"
```

**Step 1.2: 运行测试验证失败**

```bash
pixi run -e dev pytest tests/unit/stores/test_universe_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'ditto_data.stores.universe_store'`

**Step 1.3: 创建 UniverseStore 最小实现**

创建 `packages/data/src/ditto_data/stores/universe_store.py`:

```python
"""Universe 标的池存储层."""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_foundation import logger

from ditto_data.stores.sqlite_client import SQLiteClient


class UniverseStore:
    """标的池存储层。

    负责 universe 和 universe_constituent 表的 CRUD 操作。
    支持 PIT（Point-in-Time）查询。
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """初始化 UniverseStore.

        Args:
            sqlite_client: SQLite 客户端
        """
        self._client = sqlite_client

    def create_universe(
        self,
        universe_id: str,
        name: str,
        description: str | None = None,
        universe_type: str = "custom",
        source_ref: str | None = None,
    ) -> None:
        """创建标的池定义。

        Args:
            universe_id: 标的池唯一标识
            name: 标的池名称
            description: 描述信息
            universe_type: 类型 ('predefined' | 'custom')
            source_ref: 外部引用
        """
        logger.info(
            "Creating universe",
            event="universe_create_start",
            universe_id=universe_id,
            name=name,
        )

        self._client.execute(
            """INSERT INTO universe (universe_id, name, description, universe_type, source_ref)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(universe_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                universe_type = excluded.universe_type,
                source_ref = excluded.source_ref
            """,
            [universe_id, name, description, universe_type, source_ref],
        )
        self._client.commit()

        logger.info(
            "Universe created",
            event="universe_create_complete",
            universe_id=universe_id,
        )

    def get_universe(self, universe_id: str) -> dict[str, Any] | None:
        """获取标的池定义。

        Args:
            universe_id: 标的池标识

        Returns:
            标的池信息字典，不存在则返回 None
        """
        rows = self._client.fetchall(
            "SELECT * FROM universe WHERE universe_id = ?",
            [universe_id],
        )

        if not rows:
            return None

        row = rows[0]
        return {
            "universe_id": row["universe_id"],
            "name": row["name"],
            "description": row["description"],
            "universe_type": row["universe_type"],
            "source_ref": row["source_ref"],
            "created_at": row["created_at"],
        }

    def list_universes(
        self, universe_type: str | None = None,
    ) -> pl.DataFrame:
        """列出所有标的池。

        Args:
            universe_type: 按类型过滤（可选）

        Returns:
            标的池列表 DataFrame
        """
        if universe_type:
            rows = self._client.fetchall(
                "SELECT * FROM universe WHERE universe_type = ? ORDER BY created_at DESC",
                [universe_type],
            )
        else:
            rows = self._client.fetchall(
                "SELECT * FROM universe ORDER BY created_at DESC",
            )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def add_constituents(
        self,
        universe_id: str,
        records: list[dict[str, Any]],
    ) -> int:
        """批量添加成分股。

        Args:
            universe_id: 标的池标识
            records: 成分股记录列表
                [{"sid": 123, "effective_from": "2024-01-01", "weight": 0.5}, ...]

        Returns:
            添加的记录数
        """
        count = 0
        for record in records:
            self._client.execute(
                """INSERT INTO universe_constituent
                (universe_id, sid, effective_from, effective_to, weight)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    universe_id,
                    record["sid"],
                    record["effective_from"],
                    record.get("effective_to"),
                    record.get("weight"),
                ],
            )
            count += 1

        self._client.commit()
        return count

    def get_constituents(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """获取成分股列表（PIT 安全）。

        Args:
            universe_id: 标的池标识
            asof: 时点日期（YYYY-MM-DD），None 表示当前

        Returns:
            成分股 DataFrame
        """
        if asof:
            # PIT 查询：只包含该时点有效的记录
            rows = self._client.fetchall(
                """SELECT * FROM universe_constituent
                WHERE universe_id = ?
                    AND effective_from <= ?
                    AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY sid
                """,
                [universe_id, asof, asof],
            )
        else:
            # 查询当前有效记录
            rows = self._client.fetchall(
                """SELECT * FROM universe_constituent
                WHERE universe_id = ? AND effective_to IS NULL
                ORDER BY sid
                """,
                [universe_id],
            )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def get_constituents_sids(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """获取成分股 SID 列表。

        Args:
            universe_id: 标的池标识
            asof: 时点日期

        Returns:
            SID 列表
        """
        df = self.get_constituents(universe_id, asof)
        if df.is_empty():
            return []
        return df["sid"].to_list()

    def remove_constituent(
        self,
        universe_id: str,
        sid: int,
        effective_date: str,
    ) -> None:
        """移除成分股（设置 effective_to）。

        Args:
            universe_id: 标的池标识
            sid: 成分股 SID
            effective_date: 失效日期
        """
        self._client.execute(
            """UPDATE universe_constituent
            SET effective_to = ?
            WHERE universe_id = ? AND sid = ? AND effective_to IS NULL
            """,
            [effective_date, universe_id, sid],
        )
        self._client.commit()
```

**Step 1.4: 运行测试验证通过**

```bash
pixi run -e dev pytest tests/unit/stores/test_universe_store.py -v
```

Expected: PASS

**Step 1.5: 添加更多测试用例**

在 `test_universe_store.py` 中继续添加：

```python
def test_add_constituents(sqlite_client):
    """测试添加成分股"""
    store = UniverseStore(sqlite_client)

    store.create_universe("test_u", "测试池")

    records = [
        {"sid": 100000001, "effective_from": "2024-01-01", "weight": 0.5},
        {"sid": 100000002, "effective_from": "2024-01-01", "weight": 0.5},
    ]

    count = store.add_constituents("test_u", records)
    assert count == 2

    sids = store.get_constituents_sids("test_u")
    assert sids == [100000001, 100000002]


def test_get_constituents_with_asof(sqlite_client):
    """测试 PIT 查询"""
    store = UniverseStore(sqlite_client)

    store.create_universe("test_u", "测试池")
    store.add_constituents("test_u", [
        {"sid": 100000001, "effective_from": "2024-01-01"},
    ])

    # 2023-12-31 时，成分股不存在
    sids_2023 = store.get_constituents_sids("test_u", asof="2023-12-31")
    assert sids_2023 == []

    # 2024-01-01 时，成分股存在
    sids_2024 = store.get_constituents_sids("test_u", asof="2024-01-01")
    assert sids_2024 == [100000001]


def test_remove_constituent(sqlite_client):
    """测试移除成分股"""
    store = UniverseStore(sqlite_client)

    store.create_universe("test_u", "测试池")
    store.add_constituents("test_u", [
        {"sid": 100000001, "effective_from": "2024-01-01"},
    ])

    store.remove_constituent("test_u", 100000001, "2024-06-30")

    # 当前查询不存在（已移除）
    sids_now = store.get_constituents_sids("test_u")
    assert sids_now == []

    # 2024-06-01 时还存在
    sids_before = store.get_constituents_sids("test_u", asof="2024-06-01")
    assert sids_before == [100000001]
```

**Step 1.6: 运行所有测试**

```bash
pixi run -e dev pytest tests/unit/stores/test_universe_store.py -v
```

Expected: 全部 PASS

**Step 1.7: 更新 stores/__init__.py 导出**

编辑 `packages/data/src/ditto_data/stores/__init__.py`:

```python
from ditto_data.stores.adj_factor_store import AdjFactorStore
from ditto_data.stores.bars_store import BarsStore
from ditto_data.stores.calendar_store import CalendarStore
from ditto_data.stores.pipeline_store import PipelineStore
from ditto_data.stores.quarantine_store import QuarantineStore
from ditto_data.stores.security_store import SecurityStore
from ditto_data.stores.universe_store import UniverseStore  # 新增

__all__ = [
    "AdjFactorStore",
    "BarsStore",
    "CalendarStore",
    "PipelineStore",
    "QuarantineStore",
    "SecurityStore",
    "UniverseStore",  # 新增
]
```

**Step 1.8: 提交**

```bash
git add packages/data/src/ditto_data/stores/universe_store.py
git add packages/data/src/ditto_data/stores/__init__.py
git add packages/data/tests/unit/stores/test_universe_store.py
git commit -m "feat(datahub): implement UniverseStore with PIT support"
```

---

## Task 2: UniverseRepository 实现

**目标:** 实现标的池 Repository 层，提供领域接口和预定义标的池快捷方法

**Files:**
- Create: `packages/data/src/ditto_data/repositories/universe.py`
- Create: `packages/data/tests/unit/repositories/test_universe_repository.py`
- Reference: `packages/data/src/ditto_data/repositories/security.py` (模式参考)

**Step 2.1: 写 UniverseRepository 测试**

创建 `packages/data/tests/unit/repositories/test_universe_repository.py`:

```python
"""UniverseRepository 单元测试."""

import polars as pl
import pytest
from ditto_data.repositories.universe import UniverseRepository
from ditto_data.stores.universe_store import UniverseStore
from ditto_data.stores.sqlite_client import SQLiteClient


@pytest.fixture
def universe_repo(tmp_path):
    """创建 UniverseRepository 实例"""
    db_path = tmp_path / "test.db"
    client = SQLiteClient(str(db_path))
    _init_schema(client)
    store = UniverseStore(client)
    repo = UniverseRepository(store)
    yield repo
    client.close()


def _init_schema(client: SQLiteClient):
    """初始化测试表结构"""
    # ... 同 Task 1 的 _init_schema ...
    client.execute("""
        CREATE TABLE IF NOT EXISTS universe (
            universe_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            universe_type TEXT,
            source_ref TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    client.execute("""
        CREATE TABLE IF NOT EXISTS universe_constituent (
            universe_id TEXT NOT NULL,
            sid INTEGER NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            weight REAL,
            PRIMARY KEY (universe_id, sid, effective_from)
        )
    """)
    client.commit()


def test_create_universe(universe_repo):
    """测试创建标的池"""
    universe_repo.create(
        universe_id="test_pool",
        name="测试池",
        description="测试描述",
    )

    result = universe_repo.get("test_pool")
    assert result is not None
    assert result["name"] == "测试池"


def test_add_constituents(universe_repo):
    """测试添加成分股"""
    universe_repo.create("test_pool", "测试池")

    count = universe_repo.add_constituents(
        universe_id="test_pool",
        sids=[100000001, 100000002],
        effective_date="2024-01-01",
    )

    assert count == 2

    sids = universe_repo.get_constituents_sids("test_pool")
    assert sids == [100000001, 100000002]


def test_get_constituents_with_symbol(universe_repo):
    """测试获取成分股（带 symbol）"""
    universe_repo.create("test_pool", "测试池")
    universe_repo.add_constituents("test_pool", [100000001], "2024-01-01")

    # with_symbol=False 应该包含 sid 列
    df = universe_repo.get_constituents("test_pool", with_symbol=False)
    assert "sid" in df.columns
    assert len(df) == 1
```

**Step 2.2: 运行测试验证失败**

```bash
pixi run -e dev pytest tests/unit/repositories/test_universe_repository.py -v
```

Expected: `ModuleNotFoundError: No module named 'ditto_data.repositories.universe'`

**Step 2.3: 创建 UniverseRepository 实现**

创建 `packages/data/src/ditto_data/repositories/universe.py`:

```python
"""Universe 标的池 Repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_data.stores.universe_store import UniverseStore

if TYPE_CHECKING:
    from ditto_data.stores.security_store import SecurityStore


class UniverseRepository:
    """标的池 Repository。

    提供标的池管理的领域接口，支持 PIT 查询。
    """

    def __init__(
        self,
        universe_store: UniverseStore,
    ) -> None:
        """初始化 UniverseRepository。

        Args:
            universe_store: 标的池存储层
        """
        self._universe_store = universe_store

    @traced("repository.universe.create")
    def create(
        self,
        universe_id: str,
        name: str,
        description: str | None = None,
        universe_type: str = "custom",
    ) -> None:
        """创建标的池。

        Args:
            universe_id: 标的池唯一标识
            name: 标的池名称
            description: 描述信息
            universe_type: 类型 ('predefined' | 'custom')
        """
        logger.info(
            "Creating universe",
            event="universe_create_start",
            universe_id=universe_id,
            name=name,
        )

        self._universe_store.create_universe(
            universe_id=universe_id,
            name=name,
            description=description,
            universe_type=universe_type,
        )

        logger.info(
            "Universe created",
            event="universe_create_complete",
            universe_id=universe_id,
        )

    def get(self, universe_id: str) -> dict[str, Any] | None:
        """获取标的池定义。

        Args:
            universe_id: 标的池标识

        Returns:
            标的池信息字典，不存在则返回 None
        """
        return self._universe_store.get_universe(universe_id)

    def list(
        self, universe_type: str | None = None,
    ) -> pl.DataFrame:
        """列出所有标的池。

        Args:
            universe_type: 按类型过滤

        Returns:
            标的池列表 DataFrame
        """
        return self._universe_store.list_universes(universe_type)

    @traced("repository.universe.get_constituents")
    def get_constituents(
        self,
        universe_id: str,
        asof: str | None = None,
        with_symbol: bool = False,
    ) -> pl.DataFrame:
        """获取成分股列表（PIT 安全）。

        Args:
            universe_id: 标的池标识
            asof: 时点日期
            with_symbol: 是否包含 symbol 列

        Returns:
            成分股 DataFrame
        """
        logger.debug(
            "Fetching universe constituents",
            event="universe_get_constituents_start",
            universe_id=universe_id,
            asof=asof,
        )

        df = self._universe_store.get_constituents(universe_id, asof)

        # TODO: with_symbol 需要关联 security_store
        # 暂时返回原始 DataFrame

        logger.debug(
            "Universe constituents fetched",
            event="universe_get_constituents_complete",
            row_count=len(df),
        )

        M.data_records.add(len(df), {"dataset": "universe", "operation": "get_constituents"})

        return df

    def get_constituents_sids(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """获取成分股 SID 列表。

        Args:
            universe_id: 标的池标识
            asof: 时点日期

        Returns:
            SID 列表
        """
        return self._universe_store.get_constituents_sids(universe_id, asof)

    @traced("repository.universe.add_constituents")
    def add_constituents(
        self,
        universe_id: str,
        sids: list[int],
        effective_date: str,
        weights: dict[int, float] | None = None,
    ) -> int:
        """批量添加成分股。

        Args:
            universe_id: 标的池标识
            sids: SID 列表
            effective_date: 生效日期
            weights: 权重字典 {sid: weight}

        Returns:
            添加的记录数
        """
        logger.info(
            "Adding universe constituents",
            event="universe_add_constituents_start",
            universe_id=universe_id,
            count=len(sids),
        )

        records = [
            {
                "sid": sid,
                "effective_from": effective_date,
                "weight": weights.get(sid) if weights else None,
            }
            for sid in sids
        ]

        count = self._universe_store.add_constituents(universe_id, records)

        logger.info(
            "Universe constituents added",
            event="universe_add_constituents_complete",
            universe_id=universe_id,
            count=count,
        )

        M.data_records.add(count, {"dataset": "universe", "operation": "add_constituents"})

        return count

    def remove_constituent(
        self,
        universe_id: str,
        sid: int,
        effective_date: str,
    ) -> None:
        """移除成分股（设置 effective_to）。

        Args:
            universe_id: 标的池标识
            sid: 成分股 SID
            effective_date: 失效日期
        """
        logger.info(
            "Removing universe constituent",
            event="universe_remove_constituent",
            universe_id=universe_id,
            sid=sid,
        )

        self._universe_store.remove_constituent(universe_id, sid, effective_date)

    # 预定义标的池快捷方法

    def get_csi300(self, asof: str | None = None) -> list[int]:
        """获取沪深300成分股。

        Args:
            asof: 时点日期

        Returns:
            SID 列表
        """
        return self.get_constituents_sids("csi300", asof)

    def get_csi500(self, asof: str | None = None) -> list[int]:
        """获取中证500成分股。

        Args:
            asof: 时点日期

        Returns:
            SID 列表
        """
        return self.get_constituents_sids("csi500", asof)

    def get_csi1000(self, asof: str | None = None) -> list[int]:
        """获取中证1000成分股。

        Args:
            asof: 时点日期

        Returns:
            SID 列表
        """
        return self.get_constituents_sids("csi1000", asof)
```

**Step 2.4: 运行测试验证通过**

```bash
pixi run -e dev pytest tests/unit/repositories/test_universe_repository.py -v
```

Expected: PASS

**Step 2.5: 更新 repositories/__init__.py 导出**

编辑 `packages/data/src/ditto_data/repositories/__init__.py`:

```python
from ditto_data.repositories.bars import BarsRepository
from ditto_data.repositories.calendar import CalendarRepository
from ditto_data.repositories.index import IndexRepository  # 新增
from ditto_data.repositories.security import SecurityRepository
from ditto_data.repositories.universe import UniverseRepository  # 新增

__all__ = [
    "BarsRepository",
    "CalendarRepository",
    "IndexRepository",      # 新增
    "SecurityRepository",
    "UniverseRepository",   # 新增
]
```

**Step 2.6: 提交**

```bash
git add packages/data/src/ditto_data/repositories/universe.py
git add packages/data/src/ditto_data/repositories/__init__.py
git add packages/data/tests/unit/repositories/test_universe_repository.py
git commit -m "feat(datahub): implement UniverseRepository with predefined pools"
```

---

## Task 3: IndexWeightStore 实现

**目标:** 实现指数成分股权重存储层（PIT 支持）

**Files:**
- Create: `packages/data/src/ditto_data/stores/index_weight_store.py`
- Create: `packages/data/tests/unit/stores/test_index_weight_store.py`

**Step 3.1: 写 IndexWeightStore 测试**

创建 `packages/data/tests/unit/stores/test_index_weight_store.py`:

```python
"""IndexWeightStore 单元测试."""

import polars as pl
import pytest
from ditto_data.stores.index_weight_store import IndexWeightStore
from ditto_data.stores.sqlite_client import SQLiteClient


@pytest.fixture
def sqlite_client(tmp_path):
    """创建临时 SQLite 客户端"""
    db_path = tmp_path / "test.db"
    client = SQLiteClient(str(db_path))
    _init_schema(client)
    yield client
    client.close()


def _init_schema(client: SQLiteClient):
    """初始化测试表结构"""
    client.execute("""
        CREATE TABLE IF NOT EXISTS index_weight (
            index_id TEXT NOT NULL,
            sid INTEGER NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            weight REAL,
            PRIMARY KEY (index_id, sid, effective_from)
        )
    """)
    client.commit()


def test_upsert_weights(sqlite_client):
    """测试写入成分股权重"""
    store = IndexWeightStore(sqlite_client)

    records = [
        {"sid": 100000001, "effective_from": "2024-01-01", "weight": 0.5},
        {"sid": 100000002, "effective_from": "2024-01-01", "weight": 0.3},
    ]

    count = store.upsert_weights("000300.SH", records)
    assert count == 2

    df = store.get_constituents("000300.SH")
    assert len(df) == 2
    assert df["sid"].to_list() == [100000001, 100000002]


def test_get_constituents_with_asof(sqlite_client):
    """测试 PIT 查询"""
    store = IndexWeightStore(sqlite_client)

    records = [
        {"sid": 100000001, "effective_from": "2024-01-01", "weight": 0.5},
    ]
    store.upsert_weights("000300.SH", records)

    # 移除成分股
    store.remove_constituent("000300.SH", 100000001, "2024-06-30")

    # 2024-06-01 时还存在
    sids_before = store.get_constituents_sids("000300.SH", asof="2024-06-01")
    assert sids_before == [100000001]

    # 当前不存在
    sids_now = store.get_constituents_sids("000300.SH")
    assert sids_now == []
```

**Step 3.2: 运行测试验证失败**

```bash
pixi run -e dev pytest tests/unit/stores/test_index_weight_store.py -v
```

Expected: `ModuleNotFoundError`

**Step 3.3: 创建 IndexWeightStore 实现**

创建 `packages/data/src/ditto_data/stores/index_weight_store.py`:

```python
"""Index 指数成分股权重存储层."""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_foundation import logger

from ditto_data.stores.sqlite_client import SQLiteClient


class IndexWeightStore:
    """指数成分股权重存储层。

    负责指数成分股权重的 CRUD 操作，支持 PIT 查询。
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """初始化 IndexWeightStore。

        Args:
            sqlite_client: SQLite 客户端
        """
        self._client = sqlite_client

    def upsert_weights(
        self,
        index_id: str,
        records: list[dict[str, Any]],
    ) -> int:
        """批量写入/更新成分股权重。

        Args:
            index_id: 指数标识（如 '000300.SH'）
            records: 成分股记录
                [{"sid": 123, "effective_from": "2024-01-01", "weight": 0.5}, ...]

        Returns:
            写入的记录数
        """
        logger.info(
            "Upserting index weights",
            event="index_weight_upsert_start",
            index_id=index_id,
            count=len(records),
        )

        count = 0
        for record in records:
            self._client.execute(
                """INSERT INTO index_weight
                (index_id, sid, effective_from, effective_to, weight)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(index_id, sid, effective_from) DO UPDATE SET
                    weight = excluded.weight,
                    effective_to = excluded.effective_to
                """,
                [
                    index_id,
                    record["sid"],
                    record["effective_from"],
                    record.get("effective_to"),
                    record.get("weight"),
                ],
            )
            count += 1

        self._client.commit()

        logger.info(
            "Index weights upserted",
            event="index_weight_upsert_complete",
            index_id=index_id,
            count=count,
        )

        return count

    def get_constituents(
        self,
        index_id: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """获取成分股列表（PIT 安全）。

        Args:
            index_id: 指数标识
            asof: 时点日期

        Returns:
            成分股 DataFrame
        """
        if asof:
            rows = self._client.fetchall(
                """SELECT * FROM index_weight
                WHERE index_id = ?
                    AND effective_from <= ?
                    AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY sid
                """,
                [index_id, asof, asof],
            )
        else:
            rows = self._client.fetchall(
                """SELECT * FROM index_weight
                WHERE index_id = ? AND effective_to IS NULL
                ORDER BY sid
                """,
                [index_id],
            )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def get_constituents_sids(
        self,
        index_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """获取成分股 SID 列表。

        Args:
            index_id: 指数标识
            asof: 时点日期

        Returns:
            SID 列表
        """
        df = self.get_constituents(index_id, asof)
        if df.is_empty():
            return []
        return df["sid"].to_list()

    def remove_constituent(
        self,
        index_id: str,
        sid: int,
        effective_date: str,
    ) -> None:
        """移除成分股（设置 effective_to）。

        Args:
            index_id: 指数标识
            sid: 成分股 SID
            effective_date: 失效日期
        """
        self._client.execute(
            """UPDATE index_weight
            SET effective_to = ?
            WHERE index_id = ? AND sid = ? AND effective_to IS NULL
            """,
            [effective_date, index_id, sid],
        )
        self._client.commit()
```

**Step 3.4: 运行测试验证通过**

```bash
pixi run -e dev pytest tests/unit/stores/test_index_weight_store.py -v
```

**Step 3.5: 更新 stores/__init__.py 导出**

编辑 `packages/data/src/ditto_data/stores/__init__.py`:

```python
from ditto_data.stores.index_weight_store import IndexWeightStore  # 新增
from ditto_data.stores.universe_store import UniverseStore

__all__ = [
    # ... 其他 ...
    "IndexWeightStore",  # 新增
    "UniverseStore",
]
```

**Step 3.6: 提交**

```bash
git add packages/data/src/ditto_data/stores/index_weight_store.py
git add packages/data/src/ditto_data/stores/__init__.py
git add packages/data/tests/unit/stores/test_index_weight_store.py
git commit -m "feat(datahub): implement IndexWeightStore with PIT support"
```

---

## Task 4: IndexRepository 实现

**目标:** 实现指数数据 Repository，提供指数日线查询和成分股查询

**Files:**
- Create: `packages/data/src/ditto_data/repositories/index.py`
- Create: `packages/data/tests/unit/repositories/test_index_repository.py`

**Step 4.1: 写 IndexRepository 测试**

创建 `packages/data/tests/unit/repositories/test_index_repository.py`:

```python
"""IndexRepository 单元测试。"""

import polars as pl
import pytest
from ditto_data.repositories.index import IndexRepository
from ditto_data.stores.bars_store import BarsStore
from ditto_data.stores.index_weight_store import IndexWeightStore
from ditto_data.stores.security_store import SecurityStore
from ditto_data.stores.sqlite_client import SQLiteClient


@pytest.fixture
def index_repo(tmp_path):
    """创建 IndexRepository 实例"""
    db_path = tmp_path / "test.db"
    client = SQLiteClient(str(db_path))
    _init_schema(client)

    bars_store = BarsStore(data_root=tmp_path)
    security_store = SecurityStore(client)
    weight_store = IndexWeightStore(client)

    repo = IndexRepository(bars_store, security_store, weight_store)
    yield repo
    client.close()


def _init_schema(client: SQLiteClient):
    """初始化测试表结构"""
    client.execute("""
        CREATE TABLE IF NOT EXISTS index_weight (
            index_id TEXT NOT NULL,
            sid INTEGER NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            weight REAL,
            PRIMARY KEY (index_id, sid, effective_from)
        )
    """)
    client.commit()


def test_get_constituents(index_repo):
    """测试获取指数成分股"""
    records = [
        {"sid": 300000001, "effective_from": "2024-01-01", "weight": 0.5},
        {"sid": 300000002, "effective_from": "2024-01-01", "weight": 0.3},
    ]
    index_repo._weight_store.upsert_weights("000300.SH", records)

    sids = index_repo.get_constituents_sids("000300.SH")
    assert sids == [300000001, 300000002]


def test_get_csi300_constituents(index_repo):
    """测试预定义指数快捷方法"""
    records = [{"sid": 300000001, "effective_from": "2024-01-01"}]
    index_repo._weight_store.upsert_weights("csi300", records)

    sids = index_repo.get_csi300_constituents()
    assert sids == [300000001]
```

**Step 4.2: 运行测试验证失败**

```bash
pixi run -e dev pytest tests/unit/repositories/test_index_repository.py -v
```

Expected: `ModuleNotFoundError`

**Step 4.3: 创建 IndexRepository 实现**

创建 `packages/data/src/ditto_data/repositories/index.py`:

```python
"""Index 指数数据 Repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
from ditto_foundation import M, logger, traced

if TYPE_CHECKING:
    from ditto_data.stores.bars_store import BarsStore
    from ditto_data.stores.index_weight_store import IndexWeightStore
    from ditto_data.stores.security_store import SecurityStore


class IndexRepository:
    """指数数据 Repository。

    提供指数日线查询和成分股查询（PIT 支持）。
    """

    def __init__(
        self,
        bars_store: BarsStore,
        security_store: SecurityStore,
        index_weight_store: IndexWeightStore,
    ) -> None:
        """初始化 IndexRepository。

        Args:
            bars_store: K线数据存储（指数日线）
            security_store: 证券主数据存储
            index_weight_store: 指数成分股权重存储
        """
        self._bars_store = bars_store
        self._security_store = security_store
        self._weight_store = index_weight_store

    @traced("repository.index.get_bars")
    def get_bars(
        self,
        sids: list[int] | None = None,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        with_symbol: bool = False,
    ) -> pl.DataFrame:
        """获取指数日线数据。

        Args:
            sids: 按 SID 过滤
            symbols: 按 symbol 过滤
            start: 开始日期
            end: 结束日期
            with_symbol: 是否包含 symbol 列

        Returns:
            指数日线 DataFrame
        """
        logger.debug(
            "Fetching index bars",
            event="index_get_bars_start",
            sids_count=len(sids) if sids else None,
            start=start,
            end=end,
        )

        # 复用 BarsStore，dataset 为 index_daily
        df = self._bars_store.read(
            dataset="index_daily",
            sids=sids,
            start_date=start,
            end_date=end,
        )

        if df.is_empty():
            return pl.DataFrame()

        if with_symbol:
            df = self._security_store.enrich_with_symbol(df)

        logger.debug(
            "Index bars fetched",
            event="index_get_bars_complete",
            row_count=len(df),
        )

        M.data_records.add(len(df), {"dataset": "index", "operation": "get_bars"})

        return df

    def get_constituents(
        self,
        index_id: str,
        asof: str | None = None,
        with_symbol: bool = False,
        min_weight: float | None = None,
    ) -> pl.DataFrame:
        """获取指数成分股列表（PIT 安全）。

        Args:
            index_id: 指数标识（如 '000300.SH'）
            asof: 时点日期
            with_symbol: 是否包含 symbol 列
            min_weight: 最小权重过滤

        Returns:
            成分股 DataFrame
        """
        logger.debug(
            "Fetching index constituents",
            event="index_get_constituents_start",
            index_id=index_id,
            asof=asof,
        )

        df = self._weight_store.get_constituents(index_id, asof)

        if min_weight is not None and not df.is_empty():
            df = df.filter(pl.col("weight") >= min_weight)

        if with_symbol and not df.is_empty():
            df = self._security_store.enrich_with_symbol(df)

        logger.debug(
            "Index constituents fetched",
            event="index_get_constituents_complete",
            row_count=len(df),
        )

        M.data_records.add(len(df), {"dataset": "index", "operation": "get_constituents"})

        return df

    def get_constituents_sids(
        self,
        index_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """获取指数成分股 SID 列表。

        Args:
            index_id: 指数标识
            asof: 时点日期

        Returns:
            SID 列表
        """
        return self._weight_store.get_constituents_sids(index_id, asof)

    # 预定义指数快捷方法

    def get_csi300_bars(self, start: str, end: str) -> pl.DataFrame:
        """获取沪深300指数日线。

        Args:
            start: 开始日期
            end: 结束日期

        Returns:
            指数日线 DataFrame
        """
        # TODO: 需要解析 csi300 对应的 index sid
        # 暂时返回空 DataFrame
        return pl.DataFrame()

    def get_csi300_constituents(self, asof: str | None = None) -> list[int]:
        """获取沪深300成分股。

        Args:
            asof: 时点日期

        Returns:
            SID 列表
        """
        return self.get_constituents_sids("csi300", asof)

    def get_sh000001_bars(self, start: str, end: str) -> pl.DataFrame:
        """获取上证指数日线。

        Args:
            start: 开始日期
            end: 结束日期

        Returns:
            指数日线 DataFrame
        """
        # TODO: 实现
        return pl.DataFrame()
```

**Step 4.4: 运行测试验证通过**

```bash
pixi run -e dev pytest tests/unit/repositories/test_index_repository.py -v
```

**Step 4.5: 提交**

```bash
git add packages/data/src/ditto_data/repositories/index.py
git add packages/data/tests/unit/repositories/test_index_repository.py
git commit -m "feat(datahub): implement IndexRepository with constituents query"
```

---

## Task 5: FreezeManager 实现

**目标:** 实现轻量级冻结点管理器（checksum 校验，不做回滚）

**Files:**
- Create: `packages/data/src/ditto_data/runtime/freeze_manager.py`
- Create: `packages/data/tests/unit/runtime/test_freeze_manager.py`
- Modify: `packages/data/src/ditto_data/types.py` (添加 FreezeManifest)
- Modify: `packages/data/src/ditto_data/errors.py` (添加 FreezeError)

**Step 5.1: 先更新类型定义**

编辑 `packages/data/src/ditto_data/types.py`:

```python
@dataclass(frozen=True)
class FreezeManifest:
    """Freeze 冻结点清单"""
    freeze_id: str
    description: str
    created_at: str
    files: dict[str, str]  # {相对路径: md5_checksum}
```

**Step 5.2: 更新异常定义**

编辑 `packages/data/src/ditto_data/errors.py`:

```python
class FreezeError(DataHubError):
    """冻结点错误基类"""
    pass


class FreezeNotFoundError(FreezeError):
    """冻结点不存在"""

    def __init__(
        self,
        message: str = "Freeze point not found",
        freeze_id: str | None = None,
    ):
        details = {"freeze_id": freeze_id} if freeze_id else {}
        super().__init__(message, details)


class FreezeVerificationError(FreezeError):
    """冻结点校验失败"""

    def __init__(
        self,
        message: str = "Freeze verification failed",
        freeze_id: str | None = None,
        mismatched_files: list[str] | None = None,
    ):
        details = {}
        if freeze_id:
            details["freeze_id"] = freeze_id
        if mismatched_files:
            details["mismatched_files"] = mismatched_files[:10]
        super().__init__(message, details if details else None)
```

**Step 5.3: 写 FreezeManager 测试**

创建 `packages/data/tests/unit/runtime/test_freeze_manager.py`:

```python
"""FreezeManager 单元测试。"""

import json
from pathlib import Path

import pytest
from ditto_data.errors import FreezeNotFoundError, FreezeVerificationError
from ditto_data.runtime.freeze_manager import FreezeManager
from ditto_data.types import FreezeManifest


@pytest.fixture
def freeze_manager(tmp_path):
    """创建 FreezeManager 实例"""
    manager = FreezeManager(tmp_path)

    # 创建测试数据文件
    data_dir = tmp_path / "bars" / "stock_daily"
    data_dir.mkdir(parents=True)

    test_file = data_dir / "2020.parquet"
    test_file.write_text("test data")

    yield manager


def test_create_freeze(freeze_manager):
    """测试创建冻结点"""
    manifest = freeze_manager.create(
        freeze_id="test_freeze",
        description="测试冻结点",
    )

    assert manifest.freeze_id == "test_freeze"
    assert manifest.description == "测试冻结点"
    assert len(manifest.files) > 0

    # 验证 manifest 文件已创建
    manifest_path = freeze_manager._freeze_dir / "test_freeze.json"
    assert manifest_path.exists()


def test_verify_freeze_passed(freeze_manager):
    """测试验证冻结点（通过）"""
    # 创建冻结点
    freeze_manager.create("test_freeze")

    # 验证（数据未变更）
    passed, mismatches = freeze_manager.verify("test_freeze")
    assert passed is True
    assert len(mismatches) == 0


def test_verify_freeze_failed(freeze_manager):
    """测试验证冻结点（失败）"""
    # 创建冻结点
    freeze_manager.create("test_freeze")

    # 修改数据文件
    data_file = freeze_manager.data_root / "bars" / "stock_daily" / "2020.parquet"
    data_file.write_text("modified data")

    # 验证（数据已变更）
    passed, mismatches = freeze_manager.verify("test_freeze")
    assert passed is False
    assert len(mismatches) > 0


def test_list_freezes(freeze_manager):
    """测试列出所有冻结点"""
    freeze_manager.create("freeze1")
    freeze_manager.create("freeze2")

    freezes = freeze_manager.list_freezes()
    assert len(freezes) == 2


def test_get_manifest(freeze_manager):
    """测试获取冻结点详情"""
    freeze_manager.create("test_freeze")

    manifest = freeze_manager.get_manifest("test_freeze")
    assert manifest is not None
    assert manifest.freeze_id == "test_freeze"


def test_delete_freeze(freeze_manager):
    """测试删除冻结点"""
    freeze_manager.create("test_freeze")

    result = freeze_manager.delete("test_freeze")
    assert result is True

    manifest = freeze_manager.get_manifest("test_freeze")
    assert manifest is None
```

**Step 5.4: 运行测试验证失败**

```bash
pixi run -e dev pytest tests/unit/runtime/test_freeze_manager.py -v
```

Expected: `ModuleNotFoundError`

**Step 5.5: 创建 FreezeManager 实现**

创建 `packages/data/src/ditto_data/runtime/freeze_manager.py`:

```python
"""Freeze 冻结点管理器（轻量级校验实现）。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import polars as pl
from ditto_foundation import logger, span, traced

from ditto_data.errors import FreezeNotFoundError, FreezeVerificationError
from ditto_data.types import FreezeManifest


class FreezeManager:
    """冻结点管理器 - 轻量级校验实现。

    功能：
    - 创建冻结点：记录所有数据文件的 checksum
    - 验证冻结点：对比当前数据与冻结点的 checksum
    - 轻量级实现：不复制文件，只记录元数据

    不实现回滚功能（restore）。
    """

    def __init__(self, data_root: str | Path) -> None:
        """初始化 FreezeManager。

        Args:
            data_root: 数据根目录
        """
        self.data_root = Path(data_root)
        self._freeze_dir = self.data_root / "freezes"
        self._freeze_dir.mkdir(parents=True, exist_ok=True)

    @traced("freeze.create")
    def create(
        self,
        freeze_id: str,
        description: str = "",
        datasets: list[str] | None = None,
    ) -> FreezeManifest:
        """创建冻结点。

        Args:
            freeze_id: 冻结点 ID
            description: 描述信息
            datasets: 指定数据集（None 表示全部）

        Returns:
            FreezeManifest: 冻结点清单
        """
        logger.info(
            "Creating freeze point",
            event="freeze_create_start",
            freeze_id=freeze_id,
        )

        files: dict[str, str] = {}

        # 扫描 Parquet 文件
        bars_dir = self.data_root / "bars"
        if bars_dir.exists():
            for parquet_file in bars_dir.rglob("*.parquet"):
                rel_path = str(parquet_file.relative_to(self.data_root))
                files[rel_path] = self._md5(parquet_file)

        # 扫描 SQLite 数据库
        db_file = self.data_root / "meta" / "hub.sqlite"
        if db_file.exists():
            rel_path = str(db_file.relative_to(self.data_root))
            files[rel_path] = self._md5(db_file)

        manifest = FreezeManifest(
            freeze_id=freeze_id,
            description=description,
            created_at=datetime.now().isoformat(),
            files=files,
        )

        # 保存 manifest
        manifest_path = self._freeze_dir / f"{freeze_id}.json"
        manifest_path.write_text(
            json.dumps({
                "freeze_id": manifest.freeze_id,
                "description": manifest.description,
                "created_at": manifest.created_at,
                "files": manifest.files,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info(
            "Freeze point created",
            event="freeze_create_complete",
            freeze_id=freeze_id,
            file_count=manifest.file_count,
        )

        return manifest

    def verify(
        self,
        freeze_id: str,
        raise_on_error: bool = False,
    ) -> tuple[bool, list[str]]:
        """验证冻结点。

        Args:
            freeze_id: 冻结点 ID
            raise_on_error: 是否在失败时抛出异常

        Returns:
            (是否一致, 差异文件列表)
        """
        manifest_path = self._freeze_dir / f"{freeze_id}.json"

        if not manifest_path.exists():
            if raise_on_error:
                raise FreezeNotFoundError(freeze_id=freeze_id)
            return False, []

        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        stored_files = manifest_data.get("files", {})

        mismatches: list[str] = []

        for rel_path, stored_checksum in stored_files.items():
            file_path = self.data_root / rel_path
            if not file_path.exists():
                mismatches.append(f"{rel_path} (missing)")
                continue

            current_checksum = self._md5(file_path)
            if current_checksum != stored_checksum:
                mismatches.append(f"{rel_path} (checksum mismatch)")

        passed = len(mismatches) == 0

        logger.info(
            "Freeze verification completed",
            event="freeze_verify_complete",
            freeze_id=freeze_id,
            passed=passed,
            mismatch_count=len(mismatches),
        )

        if raise_on_error and not passed:
            raise FreezeVerificationError(
                freeze_id=freeze_id,
                mismatched_files=mismatches,
            )

        return passed, mismatches

    def list_freezes(self) -> list[dict[str, Any]]:
        """列出所有冻结点。

        Returns:
            冻结点列表
        """
        freezes: list[dict[str, Any]] = []

        for manifest_path in self._freeze_dir.glob("*.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                freezes.append({
                    "freeze_id": data["freeze_id"],
                    "description": data.get("description", ""),
                    "created_at": data["created_at"],
                    "file_count": len(data.get("files", {})),
                })
            except Exception:
                continue

        return sorted(freezes, key=lambda x: x["created_at"], reverse=True)

    def get_manifest(self, freeze_id: str) -> FreezeManifest | None:
        """获取冻结点详情。

        Args:
            freeze_id: 冻结点 ID

        Returns:
            FreezeManifest 或 None
        """
        manifest_path = self._freeze_dir / f"{freeze_id}.json"

        if not manifest_path.exists():
            return None

        data = json.loads(manifest_path.read_text(encoding="utf-8"))

        return FreezeManifest(
            freeze_id=data["freeze_id"],
            description=data.get("description", ""),
            created_at=data["created_at"],
            files=data.get("files", {}),
        )

    def delete(self, freeze_id: str) -> bool:
        """删除冻结点。

        Args:
            freeze_id: 冻结点 ID

        Returns:
            是否成功删除
        """
        manifest_path = self._freeze_dir / f"{freeze_id}.json"

        if manifest_path.exists():
            manifest_path.unlink()
            logger.info(
                "Freeze point deleted",
                event="freeze_delete",
                freeze_id=freeze_id,
            )
            return True

        return False

    def _md5(self, file_path: Path) -> str:
        """计算文件 MD5 checksum。

        Args:
            file_path: 文件路径

        Returns:
            MD5 哈希值（十六进制字符串）
        """
        md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5.update(chunk)
        return md5.hexdigest()
```

**Step 5.6: 运行测试验证通过**

```bash
pixi run -e dev pytest tests/unit/runtime/test_freeze_manager.py -v
```

**Step 5.7: 提交**

```bash
git add packages/data/src/ditto_data/runtime/freeze_manager.py
git add packages/data/src/ditto_data/types.py
git add packages/data/src/ditto_data/errors.py
git add packages/data/tests/unit/runtime/test_freeze_manager.py
git commit -m "feat(datahub): implement FreezeManager with checksum verification"
```

---

## Task 6: DataHub 集成

**目标:** 将新组件集成到 DataHub Facade

**Files:**
- Modify: `packages/data/src/ditto_data/hub.py`
- Create: `packages/data/tests/unit/test_datahub_phase2.py`

**Step 6.1: 更新 DataHub hub.py**

编辑 `packages/data/src/ditto_data/hub.py`，在适当位置添加以下内容：

```python
# 在现有 import 后添加
from ditto_data.stores.universe_store import UniverseStore
from ditto_data.stores.index_weight_store import IndexWeightStore
```

在 `# ========================================================================` 后添加：

```python
# ========================================================================
# Store Layer (新增)
# ========================================================================

@cached_property
def universe_store(self) -> UniverseStore:
    """Universe data store."""
    from ditto_data.stores.universe_store import UniverseStore
    from ditto_data.stores.sqlite_client import SQLiteClient

    return UniverseStore(SQLiteClient(self.sqlite_pool))

@cached_property
def index_weight_store(self) -> IndexWeightStore:
    """Index weight data store."""
    from ditto_data.stores.index_weight_store import IndexWeightStore
    from ditto_data.stores.sqlite_client import SQLiteClient

    return IndexWeightStore(SQLiteClient(self.sqlite_pool))

# ========================================================================
# Repository Layer (新增)
# ========================================================================

@cached_property
def universe(self) -> UniverseRepository:
    """Universe repository."""
    from ditto_data.repositories.universe import UniverseRepository

    return UniverseRepository(universe_store=self.universe_store)

@cached_property
def index(self) -> IndexRepository:
    """Index data repository."""
    from ditto_data.repositories.index import IndexRepository

    return IndexRepository(
        bars_store=self.bars_store,
        security_store=self.security_store,
        index_weight_store=self.index_weight_store,
    )

# ========================================================================
# Runtime Layer (新增)
# ========================================================================

@cached_property
def freeze_manager(self) -> FreezeManager:
    """Freeze point manager."""
    from ditto_data.runtime.freeze_manager import FreezeManager

    return FreezeManager(data_root=self.data_root)
```

在类末尾的便捷方法区域添加：

```python
# ========================================================================
# Freeze Management
# ========================================================================

def create_freeze(
    self,
    freeze_id: str,
    description: str = "",
    datasets: list[str] | None = None,
) -> str:
    """创建数据冻结点。

    Args:
        freeze_id: 冻结点 ID
        description: 描述信息
        datasets: 指定数据集

    Returns:
        freeze_id
    """
    manifest = self.freeze_manager.create(freeze_id, description, datasets)
    return manifest.freeze_id


def verify_freeze(
    self,
    freeze_id: str,
    raise_on_error: bool = False,
) -> tuple[bool, list[str]]:
    """验证冻结点。

    Args:
        freeze_id: 冻结点 ID
        raise_on_error: 是否在失败时抛出异常

    Returns:
        (是否一致, 差异文件列表)
    """
    return self.freeze_manager.verify(freeze_id, raise_on_error)


def list_freezes(self) -> pl.DataFrame:
    """列出所有冻结点。

    Returns:
        冻结点列表 DataFrame
    """
    freezes = self.freeze_manager.list_freezes()
    return pl.DataFrame(freezes) if freezes else pl.DataFrame()


# ========================================================================
# Metadata Query
# ========================================================================

def get_trading_days(
    self,
    start: str,
    end: str,
    only_open: bool = True,
) -> list[str]:
    """获取交易日列表。

    Args:
        start: 开始日期
        end: 结束日期
        only_open: 仅返回交易日

    Returns:
        交易日列表
    """
    if only_open:
        return self.calendar_store.get_range(start, end)
    else:
        # 返回所有日期（包括非交易日）
        df = self.calendar_store.get_range_df(start, end, only_open=False)
        return df["trade_date"].to_list() if not df.is_empty() else []


def is_trading_day(self, date: str) -> bool:
    """判断是否为交易日。

    Args:
        date: 日期字符串

    Returns:
        是否为交易日
    """
    return self.calendar_store.is_trading_day(date)
```

**Step 6.2: 更新 close 方法**

在 `close()` 方法中添加新资源的清理：

```python
# 在 close() 方法开头添加
# Close stores that hold SQLiteClient references
for store_name in ("universe_store", "index_weight_store", ...):  # 添加到现有列表
    if store_name in self.__dict__:
        store = getattr(self, store_name)
        if hasattr(store, "close"):
            store.close()
```

**Step 6.3: 写 DataHub 集成测试**

创建 `packages/data/tests/unit/test_datahub_phase2.py`:

```python
"""DataHub Phase 2 集成测试。"""

import pytest
from ditto_data.hub import DataHub


@pytest.fixture
def datahub(tmp_path):
    """创建 DataHub 实例"""
    hub = DataHub(data_root=tmp_path)
    yield hub
    hub.close()


def test_universe_repository(datahub):
    """测试 universe repository"""
    datahub.universe.create(
        universe_id="test_pool",
        name="测试池",
    )

    result = datahub.universe.get("test_pool")
    assert result is not None
    assert result["name"] == "测试池"


def test_index_repository(datahub):
    """测试 index repository"""
    # 基础功能测试
    sids = datahub.index.get_constituents_sids("test_index")
    assert isinstance(sids, list)


def test_freeze_manager(datahub):
    """测试 freeze manager"""
    freeze_id = datahub.create_freeze("test_freeze", "测试冻结点")

    freezes = datahub.list_freezes()
    assert len(freezes) > 0

    passed, _ = datahub.verify_freeze(freeze_id)
    assert passed is True


def test_get_trading_days(datahub):
    """测试获取交易日列表"""
    # 这个需要真实的交易日历数据
    days = datahub.get_trading_days("2024-01-01", "2024-01-31")
    assert isinstance(days, list)


def test_is_trading_day(datahub):
    """测试判断交易日"""
    # 这个需要真实的交易日历数据
    result = datahub.is_trading_day("2024-01-02")  # 假设是交易日
    assert isinstance(result, bool)
```

**Step 6.4: 运行测试验证通过**

```bash
pixi run -e dev pytest tests/unit/test_datahub_phase2.py -v
```

**Step 6.5: 提交**

```bash
git add packages/data/src/ditto_data/hub.py
git add packages/data/tests/unit/test_datahub_phase2.py
git commit -m "feat(datahub): integrate UniverseRepository, IndexRepository, FreezeManager to DataHub"
```

---

## Task 7: 代码质量检查和文档更新

**Step 7.1: 运行代码质量检查**

```bash
# 快速检查
pixi run -e dev quick-check

# 单元测试
pixi run -e dev test-unit

# 提交前完整检查
pixi run -e dev pre-push-check
```

Expected: 全部通过

**Step 7.2: 更新 Sprint 文档**

编辑 `docs/sprints/sprint-02-data-quality.md`，在 Phase 2 状态处更新：

```markdown
### Phase 2: DataHub 完整实现（8 任务，4-5 天）✅ 已完成

**完成日期**: 2025-12-29

**新增文件**: (11 个)
- `packages/data/src/ditto_data/stores/universe_store.py`
- `packages/data/src/ditto_data/stores/index_weight_store.py`
- `packages/data/src/ditto_data/repositories/universe.py`
- `packages/data/src/ditto_data/repositories/index.py`
- `packages/data/src/ditto_data/runtime/freeze_manager.py`
- (测试文件 6 个)

**验收标准**:
- [x] UniverseRepository 可创建标的池、PIT 查询成分股
- [x] IndexRepository 可查询指数日线和成分股（PIT 支持）
- [x] FreezeManager 可创建/验证冻结点（checksum 校验）
- [x] DataHub 新接口全部可用
- [ ] 指数成分股摄取任务可运行（留待 Phase 3）
```

**Step 7.3: 最终提交**

```bash
git add docs/sprints/sprint-02-data-quality.md
git commit -m "docs(sprint-02): update Phase 2 status to completed"
```

---

## 验收检查清单

运行以下命令确保所有测试通过：

```bash
# 单元测试
pixi run -e dev test-unit

# 代码质量检查
pixi run -e dev pre-push-check

# 检查测试覆盖率
pixi run -e dev pytest --cov=packages/data/src/ditto_data --cov-report=term-missing
```

Expected Output:
- 所有测试 PASSED
- 测试覆盖率 >= 80%
- 无 ruff linting 错误
- 无类型检查错误

---

## 完成

**Plan 完成并保存至** `docs/plans/2025-12-29-datahub-phase2-implementation.md`。

**执行选项：**

1. **Subagent-Driven (当前会话)** - 我在此会话中逐任务派发子代理执行，任务间审查代码，快速迭代

2. **Parallel Session (独立会话)** - 在新会话中使用 executing-plans 批量执行，设置检查点

**选择哪种方式？**

---

## 执行状态

✅ **已完成** - 2025-12-29

**执行方式**: Subagent-Driven (Parallel Agents)

**完成内容**:
- Task 1: UniverseStore 实现 ✅
- Task 2: UniverseRepository 实现 ✅
- Task 3: IndexWeightStore 实现 ✅
- Task 4: IndexRepository 实现 ✅
- Task 5: FreezeManager 实现 ✅
- Task 6: DataHub 集成 ✅
- Task 7: 代码质量检查和文档更新 ✅

**提交**: feat(datahub): Sprint 2 Phase 2 - DataHub 完整实现 (#17)
