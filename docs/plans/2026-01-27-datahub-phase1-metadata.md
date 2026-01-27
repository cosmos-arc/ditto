# DataHub Metadata 域重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**目标:** 将现有的元数据相关 Store 和 Accessor 重构为统一的 Metadata 域结构，实现 domains/metadata/ 目录组织

**架构:**
- 创建 `domains/metadata/` 目录，按子域组织
- 实现 MetadataQueryService 作为域级统一入口
- 合并 security、industry、identity、calendar、universe 等子域
- 移除 Accessor 层，功能合并到 QueryService

**技术栈:** Python 3.12+, Polars, Pydantic, Pyright Strict

**前置依赖:** Phase 0 - 基础层重构

---

## 目录结构

```
packages/datahub/src/ditto_datahub/domains/metadata/
├── __init__.py
├── security/
│   ├── __init__.py
│   ├── security_store.py          # 从 stores/ 迁移
│   └── models.py                  # 数据模型
├── industry/
│   ├── __init__.py
│   ├── industry_basic_store.py    # 新增
│   ├── industry_mapping_store.py  # 新增
│   └── models.py
├── identity/
│   ├── __init__.py
│   ├── identity_store.py          # 从 SecurityStore 拆分
│   └── models.py
├── calendar/
│   ├── __init__.py
│   ├── calendar_store.py          # 从 stores/ 迁移
│   └── models.py
├── universe/
│   ├── __init__.py
│   ├── universe_store.py          # 从 stores/ 迁移
│   └── models.py
├── index/
│   ├── __init__.py
│   ├── index_basic_store.py       # 新增
│   ├── index_constituent_store.py # 新增
│   └── models.py
├── etf/
│   ├── __init__.py
│   ├── etf_basic_store.py         # 新增
│   ├── etf_constituent_store.py   # 新增
│   └── models.py
└── metadata_query_service.py      # 域级查询服务
```

---

## 任务 1: 创建 Metadata 域目录结构

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/__init__.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/metadata/__init__.py`

**步骤 1: 创建域级 __init__.py**

```python
# packages/datahub/src/ditto_datahub/domains/__init__.py
"""DataHub 域级组织."""

from ditto_datahub.domains.metadata import MetadataQueryService

__all__ = ["MetadataQueryService"]
```

**步骤 2: 创建 Metadata 域 __init__.py**

```python
# packages/datahub/src/ditto_datahub/domains/metadata/__init__.py
"""Metadata 域 - 元数据访问."""

from ditto_datahub.domains.metadata.metadata_query_service import MetadataQueryService

__all__ = ["MetadataQueryService"]
```

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/
git commit -m "feat(datahub): create domain-level directory structure for Metadata"
```

---

## 任务 2: 迁移 Security 相关代码到 Metadata 域

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/metadata/security/__init__.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/metadata/security/security_store.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/metadata/security/models.py`
- 修改: `packages/datahub/src/ditto_datahub/stores/security_store.py` (添加弃用警告)

**步骤 1: 创建 models.py**

```python
# packages/datahub/src/ditto_datahub/domains/metadata/security/models.py
"""Security 相关数据模型."""

from __future__ import annotations

from dataclasses import dataclass


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
```

**步骤 2: 迁移 SecurityStore**

```python
# packages/datahub/src/ditto_datahub/domains/metadata/security/security_store.py
"""
SecurityStore for securities master data with PIT support.

从 stores/security_store.py 迁移而来。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced
from ditto_foundation.cache import DataCache

from ditto_datahub.domains.metadata.security.models import SecurityRegistration
from ditto_datahub.stores.base.sqlite_store import SQLiteStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


def _build_in_clause(
    column: str,
    items: list[Any],
    chunk_size: int = 200,
) -> tuple[str, list[Any]]:
    """构建参数化 IN 子句（自动分块）。"""
    if not items:
        return ("1=0", [])

    if len(items) <= chunk_size:
        placeholders = ",".join("?" * len(items))
        return f"{column} IN ({placeholders})", items

    # 分块处理
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

    注意: 此类从 stores/security_store.py 迁移而来。
    未来版本将继承 SQLiteStore 基类。

    迁移路径: stores/security_store.py -> domains/metadata/security/security_store.py
    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any] | None = None,
    ) -> None:
        """Initialize SecurityStore."""
        self._client = sqlite_client
        self._data_cache = data_cache

    # ... 复制现有 SecurityStore 的所有方法 ...
    # 这里省略，保持原有实现不变

    @traced("data.sid_resolve")
    def resolve_sid(self, src_code: str, source: str, asof: str | None) -> int | None:
        """Resolve src_code to sid (with PIT support)."""
        # 保持原有实现
        ...

    # 其他方法保持不变
```

**步骤 3: 在旧位置添加弃用警告**

```python
# packages/datahub/src/ditto_datahub/stores/security_store.py
"""
SecurityStore for securities master data with PIT support.

⚠️ DEPRECATED: 此模块已迁移到 domains/metadata/security/security_store.py

请使用新的导入路径：
    from ditto_datahub.domains.metadata.security import SecurityStore

此文件保留用于向后兼容，将在未来版本中移除。
"""

import warnings

warnings.warn(
    "SecurityStore 已迁移到 ditto_datahub.domains.metadata.security",
    DeprecationWarning,
    stacklevel=2,
)

# 从新位置导入
from ditto_datahub.domains.metadata.security.security_store import (  # noqa: F401
    SecurityStore,
    SecurityRegistration,
    _build_in_clause,
)

__all__ = ["SecurityStore", "SecurityRegistration", "_build_in_clause"]
```

**步骤 4: 更新测试导入**

```bash
# 搜索所有使用旧导入的文件
grep -r "from ditto_datahub.stores.security_store" packages/datahub/tests/
grep -r "from ditto_datahub.stores import SecurityStore" packages/datahub/
```

**步骤 5: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/metadata/security/
git add packages/datahub/src/ditto_datahub/stores/security_store.py
git commit -m "refactor(datahub): migrate SecurityStore to domains/metadata/security/"
```

---

## 任务 3: 拆分 Identity 功能为独立 Store

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/metadata/identity/identity_store.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/metadata/identity/models.py`

**步骤 1: 编写失败测试**

```python
# packages/datahub/tests/unit/domains/metadata/identity/test_identity_store_unit.py
def test_identity_resolve_sid_pit():
    """测试 PIT 查询功能."""
    # 测试代码...
    pass
```

**步骤 2: 实现 IdentityStore**

```python
# packages/datahub/src/ditto_datahub/domains/metadata/identity/identity_store.py
"""
IdentityStore for identity mapping with PIT support.

从 SecurityStore 拆分出来的 identity_mapping 表专用 Store。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.base.sqlite_store import SQLiteStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


class IdentityStore(SQLiteStore):
    """
    Identity 映射存储。

    管理 identity_mapping 表，支持 PIT 查询。

    表结构:
        - sid: 证券内部标识符
        - source: 数据源标识
        - src_code: 数据源原始代码
        - effective_from: 生效开始日期
        - effective_to: 生效结束日期 (NULL 表示当前有效)
        - is_primary: 是否主标识符
    """

    def __init__(self, db_path: Path) -> None:
        """初始化 IdentityStore."""
        super().__init__(db_path)

    @traced("data.identity.resolve")
    def resolve_sid(
        self,
        src_code: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int | None:
        """
        解析 src_code 到 sid (支持 PIT)。

        Args:
            src_code: 源代码，如 "600000.SH"
            source: 数据源标识
            asof: Point-in-time 查询日期

        Returns:
            sid 或 None

        """
        if asof:
            # PIT 模式
            row = self.fetchone(
                """SELECT sid FROM identity_mapping
                WHERE source = ? AND src_code = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [source, src_code, asof, asof],
            )
        else:
            # 当前模式
            row = self.fetchone(
                """SELECT sid FROM identity_mapping
                WHERE source = ? AND src_code = ?
                  AND effective_to IS NULL""",
                [source, src_code],
            )

        return int(row["sid"]) if row else None

    @traced("data.identity.resolve_batch")
    def resolve_sids_batch(
        self,
        src_codes: list[str],
        source: str = "tushare",
        asof: str | None = None,
    ) -> dict[str, int]:
        """
        批量解析 src_codes 到 sids。

        Args:
            src_codes: 源代码列表
            source: 数据源标识
            asof: Point-in-time 查询日期

        Returns:
            {src_code: sid} 映射字典

        """
        result: dict[str, int] = {}
        for code in src_codes:
            sid = self.resolve_sid(code, source, asof)
            if sid:
                result[code] = sid
        return result

    @traced("data.identity.reverse_lookup")
    def get_src_code(
        self,
        sid: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """
        反向查询：sid 到 src_code。

        Args:
            sid: 证券 ID
            source: 数据源标识
            asof: Point-in-time 查询日期

        Returns:
            src_code 或 None

        """
        if asof:
            row = self.fetchone(
                """SELECT src_code FROM identity_mapping
                WHERE sid = ? AND source = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [sid, source, asof, asof],
            )
        else:
            row = self.fetchone(
                """SELECT src_code FROM identity_mapping
                WHERE sid = ? AND source = ?
                  AND effective_to IS NULL""",
                [sid, source],
            )

        return str(row["src_code"]) if row else None

    @traced("data.identity.register")
    def register(
        self,
        sid: int,
        src_code: str,
        source: str = "tushare",
        effective_from: str | None = None,
        is_primary: bool = True,
    ) -> None:
        """
        注册 identity_mapping 记录。

        Args:
            sid: 证券 ID
            src_code: 源代码
            source: 数据源标识
            effective_from: 生效开始日期
            is_primary: 是否主标识符

        """
        effective_from = effective_from or str(pl.Date.today())

        # 失效旧记录
        self.execute(
            """UPDATE identity_mapping
            SET effective_to = ?
            WHERE sid = ? AND source = ? AND effective_to IS NULL""",
            [effective_from, sid, source],
        )

        # 插入新记录
        self.execute(
            """INSERT INTO identity_mapping
            (sid, source, src_code, effective_from, is_primary)
            VALUES (?, ?, ?, ?, ?)""",
            [sid, source, src_code, effective_from, is_primary],
        )
```

**步骤 3: 运行测试**

```bash
pixi run -e dev pytest tests/unit/domains/metadata/identity/test_identity_store_unit.py -v
```

**步骤 4: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/metadata/identity/
git commit -m "feat(datahub): add IdentityStore for identity mapping"
```

---

## 任务 4: 实现 Industry 相关 Store

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/metadata/industry/industry_basic_store.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/metadata/industry/industry_mapping_store.py`
- 新建: `packages/datahub/src/ditto_datahub/domains/metadata/industry/models.py`

**步骤 1: 定义数据模型**

```python
# packages/datahub/src/ditto_datahub/domains/metadata/industry/models.py
"""Industry 相关数据模型."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class IndustryBasic:
    """申万行业基本信息."""

    industry_id: str
    industry_name: str
    industry_level: str  # 一级/二级行业
    parent_id: str | None = None
    is_active: bool = True


@dataclass(frozen=True)
class IndustryMapping:
    """股票-行业映射."""

    sid: int
    industry_id: str
    source: str = "sw"  # 申万
    effective_from: date | None = None
    effective_to: date | None = None
    entry_reason: str | None = None
```

**步骤 2: 实现 IndustryBasicStore**

```python
# packages/datahub/src/ditto_datahub/domains/metadata/industry/industry_basic_store.py
"""
IndustryBasicStore for industry master data.

支持申万行业分类的存储和查询。
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.domains.metadata.industry.models import IndustryBasic
from ditto_datahub.stores.base.sqlite_store import SQLiteStore


class IndustryBasicStore(SQLiteStore):
    """申万行业主数据存储."""

    def __init__(self, db_path: Path) -> None:
        """初始化 IndustryBasicStore."""
        super().__init__(db_path)

    @traced("data.industry.get_all")
    def get_all(
        self,
        is_active: bool = True,
        industry_level: str | None = None,
    ) -> pl.DataFrame:
        """
        获取所有行业信息。

        Args:
            is_active: 是否只返回活跃行业
            industry_level: 行业级别过滤

        Returns:
            行业信息 DataFrame

        """
        sql = "SELECT * FROM industry_basic WHERE 1=1"
        params: list[object] = []

        if is_active:
            sql += " AND is_active = ?"
            params.append(is_active)

        if industry_level:
            sql += " AND industry_level = ?"
            params.append(industry_level)

        with self._get_connection() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame([dict(row) for row in rows])

    @traced("data.industry.get_by_id")
    def get_by_id(self, industry_id: str) -> dict[str, object] | None:
        """
        根据 ID 获取行业信息。

        Args:
            industry_id: 行业 ID

        Returns:
            行业信息字典

        """
        return self.fetchone(
            "SELECT * FROM industry_basic WHERE industry_id = ?",
            [industry_id],
        )

    @traced("data.industry.register")
    def register(self, industry: IndustryBasic) -> None:
        """
        注册行业信息。

        Args:
            industry: 行业基本信息

        """
        self.execute(
            """INSERT OR REPLACE INTO industry_basic
            (industry_id, industry_name, industry_level, parent_id, is_active)
            VALUES (?, ?, ?, ?, ?)""",
            [
                industry.industry_id,
                industry.industry_name,
                industry.industry_level,
                industry.parent_id,
                industry.is_active,
            ],
        )
```

**步骤 3: 实现 IndustryMappingStore**

```python
# packages/datahub/src/ditto_datahub/domains/metadata/industry/industry_mapping_store.py
"""
IndustryMappingStore for stock-industry mapping with PIT support.

支持股票-行业映射的 PIT 查询。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.base.sqlite_store import SQLiteStore


class IndustryMappingStore(SQLiteStore):
    """股票-行业映射存储."""

    def __init__(self, db_path: Path) -> None:
        """初始化 IndustryMappingStore."""
        super().__init__(db_path)

    @traced("data.industry.get_stocks")
    def get_stocks(
        self,
        industry_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        获取行业的所有成分股。

        Args:
            industry_id: 行业 ID
            asof: Point-in-time 查询日期

        Returns:
            SID 列表

        """
        if asof:
            rows = self.fetchall(
                """SELECT sid FROM industry_mapping
                WHERE industry_id = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY sid""",
                [industry_id, asof, asof],
            )
        else:
            rows = self.fetchall(
                """SELECT sid FROM industry_mapping
                WHERE industry_id = ? AND effective_to IS NULL
                ORDER BY sid""",
                [industry_id],
            )

        return [int(r["sid"]) for r in rows]

    @traced("data.industry.get_stock_industry")
    def get_stock_industry(
        self,
        sid: int,
        asof: str | None = None,
    ) -> dict[str, Any] | None:
        """
        获取股票所属行业。

        Args:
            sid: 证券 ID
            asof: Point-in-time 查询日期

        Returns:
            行业映射信息

        """
        if asof:
            return self.fetchone(
                """SELECT * FROM industry_mapping
                WHERE sid = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [sid, asof, asof],
            )
        else:
            return self.fetchone(
                """SELECT * FROM industry_mapping
                WHERE sid = ? AND effective_to IS NULL""",
                [sid],
            )

    @traced("data.industry.update_mapping")
    def update_mapping(
        self,
        sid: int,
        industry_id: str,
        effective_from: str,
        entry_reason: str | None = None,
    ) -> None:
        """
        更新股票的行业映射。

        Args:
            sid: 证券 ID
            industry_id: 行业 ID
            effective_from: 生效日期
            entry_reason: 入选原因

        """
        # 失效旧映射
        self.execute(
            """UPDATE industry_mapping
            SET effective_to = ?
            WHERE sid = ? AND effective_to IS NULL""",
            [effective_from, sid],
        )

        # 插入新映射
        self.execute(
            """INSERT INTO industry_mapping
            (sid, industry_id, effective_from, entry_reason)
            VALUES (?, ?, ?, ?)""",
            [sid, industry_id, effective_from, entry_reason],
        )
```

**步骤 4: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/metadata/industry/
git commit -m "feat(datahub): add Industry stores (IndustryBasicStore, IndustryMappingStore)"
```

---

## 任务 5: 迁移 Calendar 到 Metadata 域

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/metadata/calendar/calendar_store.py`
- 修改: `packages/datahub/src/ditto_datahub/stores/calendar_store.py` (添加弃用警告)

**步骤 1: 迁移 CalendarStore**

```python
# packages/datahub/src/ditto_datahub/domains/metadata/calendar/calendar_store.py
"""
CalendarStore for trading calendar data.

从 stores/calendar_store.py 迁移而来。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.base.sqlite_store import SQLiteStore


class CalendarStore(SQLiteStore):
    """
    交易日历存储。

    迁移路径: stores/calendar_store.py -> domains/metadata/calendar/calendar_store.py
    """

    def __init__(self, db_path: Path) -> None:
        """初始化 CalendarStore."""
        super().__init__(db_path)

    # ... 复制现有 CalendarStore 的所有方法 ...
    # 保持原有实现不变

    @traced("data.calendar.get")
    def get(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> pl.DataFrame:
        """获取交易日历."""
        # 保持原有实现
        ...

    # 其他方法保持不变
```

**步骤 2: 在旧位置添加弃用警告**

```python
# packages/datahub/src/ditto_datahub/stores/calendar_store.py
"""
CalendarStore for trading calendar data.

⚠️ DEPRECATED: 此模块已迁移到 domains/metadata/calendar/calendar_store.py

请使用新的导入路径：
    from ditto_datahub.domains.metadata.calendar import CalendarStore
"""

import warnings

warnings.warn(
    "CalendarStore 已迁移到 ditto_datahub.domains.metadata.calendar",
    DeprecationWarning,
    stacklevel=2,
)

from ditto_datahub.domains.metadata.calendar.calendar_store import CalendarStore

__all__ = ["CalendarStore"]
```

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/metadata/calendar/
git add packages/datahub/src/ditto_datahub/stores/calendar_store.py
git commit -m "refactor(datahub): migrate CalendarStore to domains/metadata/calendar/"
```

---

## 任务 6: 实现 MetadataQueryService

**文件:**
- 新建: `packages/datahub/src/ditto_datahub/domains/metadata/metadata_query_service.py`

**步骤 1: 编写失败测试**

```python
# packages/datahub/tests/unit/domains/metadata/test_metadata_query_service_unit.py
def test_metadata_query_service_resolve_sid():
    """测试 MetadataQueryService 的 SID 解析功能."""
    # 测试代码...
    pass
```

**步骤 2: 实现 MetadataQueryService**

```python
# packages/datahub/src/ditto_datahub/domains/metadata/metadata_query_service.py
"""
MetadataQueryService - Metadata 域统一查询入口.

合并 SecurityAccessor 和部分 CalendarAccessor 的功能。
"""

from __future__ import annotations

from typing import Any, Literal

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.domains.metadata.calendar.calendar_store import CalendarStore
from ditto_datahub.domains.metadata.identity.identity_store import IdentityStore
from ditto_datahub.domains.metadata.industry.industry_basic_store import IndustryBasicStore
from ditto_datahub.domains.metadata.industry.industry_mapping_store import IndustryMappingStore
from ditto_datahub.domains.metadata.security.security_store import SecurityStore
from ditto_datahub.domains.metadata.universe.universe_store import UniverseStore
from ditto_datahub.runtime.sid_allocator import SidAllocator


class MetadataQueryService:
    """
    Metadata 域统一查询服务。

    整合 Metadata 域所有 Store 的查询功能，提供统一的访问入口。

    替代: SecuritiesAccessor + CalendarAccessor 的部分功能
    """

    def __init__(
        self,
        security_store: SecurityStore,
        identity_store: IdentityStore,
        calendar_store: CalendarStore,
        industry_basic_store: IndustryBasicStore,
        industry_mapping_store: IndustryMappingStore,
        universe_store: UniverseStore,
        sid_allocator: SidAllocator,
    ) -> None:
        """初始化 MetadataQueryService."""
        self._security_store = security_store
        self._identity_store = identity_store
        self._calendar_store = calendar_store
        self._industry_basic_store = industry_basic_store
        self._industry_mapping_store = industry_mapping_store
        self._universe_store = universe_store
        self._sid_allocator = sid_allocator

    # ============ Identity 解析 ============

    @traced("metadata.resolve_sid")
    def resolve_sid(
        self,
        identifier: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int | None:
        """
        解析标识符为 SID。

        Args:
            identifier: src_code 或 symbol
            source: 数据源标识
            asof: Point-in-time 查询日期

        Returns:
            SID 或 None

        """
        # 优先尝试 src_code 解析
        sid = self._identity_store.resolve_sid(identifier, source, asof)
        if sid:
            return sid

        # 尝试 symbol 解析
        sids = self._security_store.resolve_by_symbol(identifier, source)
        if sids:
            return sids[0]

        return None

    @traced("metadata.resolve_sids_batch")
    def resolve_sids_batch(
        self,
        identifiers: list[str],
        source: str = "tushare",
        asof: str | None = None,
    ) -> dict[str, int]:
        """
        批量解析标识符为 SID。

        Args:
            identifiers: 标识符列表
            source: 数据源标识
            asof: Point-in-time 查询日期

        Returns:
            {identifier: sid} 映射字典

        """
        result: dict[str, int] = {}
        for identifier in identifiers:
            sid = self.resolve_sid(identifier, source, asof)
            if sid:
                result[identifier] = sid
        return result

    # ============ 证券查询 ============

    @traced("metadata.get_securities")
    def get_securities(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        source: str = "tushare",
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        查询证券信息。

        替代 SecuritiesAccessor.get()

        """
        return self._security_store.find_securities(
            sids=sids,
            src_codes=src_codes,
            source=source,
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
            asof=asof,
        )

    @traced("metadata.get_symbol")
    def get_symbol(self, sid: int) -> str | None:
        """获取 SID 对应的 symbol."""
        return self._security_store.get_symbol(sid)

    @traced("metadata.get_src_code")
    def get_src_code(
        self,
        sid: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """获取 SID 对应的 src_code."""
        return self._identity_store.get_src_code(sid, source, asof)

    # ============ 行业查询 ============

    @traced("metadata.get_industries")
    def get_industries(
        self,
        is_active: bool = True,
        industry_level: str | None = None,
    ) -> pl.DataFrame:
        """获取所有行业信息."""
        return self._industry_basic_store.get_all(is_active, industry_level)

    @traced("metadata.get_stock_industry")
    def get_stock_industry(
        self,
        sid: int,
        asof: str | None = None,
    ) -> dict[str, Any] | None:
        """获取股票所属行业."""
        return self._industry_mapping_store.get_stock_industry(sid, asof)

    @traced("metadata.get_industry_stocks")
    def get_industry_stocks(
        self,
        industry_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """获取行业的成分股."""
        return self._industry_mapping_store.get_stocks(industry_id, asof)

    # =交易日历查询 ============

    @traced("metadata.get_trading_days")
    def get_trading_days(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> list[str]:
        """获取交易日列表."""
        df = self._calendar_store.get(start, end, only_open)
        return df["trade_date"].to_list()

    @traced("metadata.is_trading_day")
    def is_trading_day(self, date: str) -> bool:
        """检查是否为交易日."""
        return self._calendar_store.is_trading_day(date)

    # ============ 标的池查询 ============

    @traced("metadata.get_universe")
    def get_universe(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """获取标的池成分股."""
        return self._universe_store.get_constituents(universe_id, asof)

    # ============ 证券注册 ============

    @traced("metadata.register_security")
    def register_security(
        self,
        src_code: str,
        symbol: str,
        name: str,
        exchange: str,
        asset_class: str,
        list_date: str,
        source: str = "tushare",
        board: str | None = None,
    ) -> int:
        """
        注册新证券。

        替代 SecuritiesAccessor.register()

        """
        # 分配 SID
        sid = self._sid_allocator.allocate(asset_class)

        # 注册到 SecurityStore
        from ditto_datahub.domains.metadata.security.models import SecurityRegistration

        registration = SecurityRegistration(
            src_code=src_code,
            symbol=symbol,
            name=name,
            exchange=exchange,
            asset_class=asset_class,
            list_date=list_date,
            source=source,
            board=board,
        )

        self._security_store.register(sid, registration)

        return sid
```

**步骤 3: 运行测试**

```bash
pixi run -e dev pytest tests/unit/domains/metadata/test_metadata_query_service_unit.py -v
```

**步骤 4: 提交**

```bash
git add packages/datahub/src/ditto_datahub/domains/metadata/metadata_query_service.py
git commit -m "feat(datahub): implement MetadataQueryService"
```

---

## 任务 7: 更新 DataHub 集成

**文件:**
- 修改: `packages/datahub/src/ditto_datahub/hub.py`
- 修改: `packages/datahub/src/ditto_datahub/init_providers.py`

**步骤 1: 更新 DataHub 使用 MetadataQueryService**

```python
# packages/datahub/src/ditto_datahub/hub.py

# 在导入部分添加
from ditto_datahub.domains.metadata import MetadataQueryService

# 在 DataHub 类中替换 SecuritiesAccessor 为 MetadataQueryService
class DataHub:
    def __init__(
        self,
        # ... 其他依赖 ...
        metadata_query_service: MetadataQueryService,  # 替换 securities
        # ... 其他依赖 ...
    ) -> None:
        # ... 其他初始化 ...

        # 替换 self.securities = securities
        self.metadata = metadata_query_service

        # 保留向后兼容的别名
        self.securities = metadata_query_service
```

**步骤 2: 更新 Provider**

```python
# packages/datahub/src/ditto_datahub/init_providers.py

from ditto_datahub.domains.metadata import MetadataQueryService
from ditto_datahub.domains.metadata.calendar.calendar_store import CalendarStore
from ditto_datahub.domains.metadata.identity.identity_store import IdentityStore
from ditto_datahub.domains.metadata.industry.industry_basic_store import IndustryBasicStore
from ditto_datahub.domains.metadata.industry.industry_mapping_store import IndustryMappingStore
from ditto_datahub.domains.metadata.security.security_store import SecurityStore
from ditto_datahub.domains.metadata.universe.universe_store import UniverseStore

class DataHubProvider(Provider):
    # ... 其他提供者 ...

    @staticmethod
    @provide
    def identity_store(config: DataRootConfig) -> IdentityStore:
        """提供 IdentityStore."""
        return IdentityStore(config.metadata_db_path)

    @staticmethod
    @provide
    def industry_basic_store(config: DataRootConfig) -> IndustryBasicStore:
        """提供 IndustryBasicStore."""
        return IndustryBasicStore(config.metadata_db_path)

    @staticmethod
    @provide
    def industry_mapping_store(config: DataRootConfig) -> IndustryMappingStore:
        """提供 IndustryMappingStore."""
        return IndustryMappingStore(config.metadata_db_path)

    @staticmethod
    @provide
    def metadata_query_service(
        security_store: SecurityStore,
        identity_store: IdentityStore,
        calendar_store: CalendarStore,
        industry_basic_store: IndustryBasicStore,
        industry_mapping_store: IndustryMappingStore,
        universe_store: UniverseStore,
        sid_allocator: SidAllocator,
    ) -> MetadataQueryService:
        """提供 MetadataQueryService."""
        return MetadataQueryService(
            security_store=security_store,
            identity_store=identity_store,
            calendar_store=calendar_store,
            industry_basic_store=industry_basic_store,
            industry_mapping_store=industry_mapping_store,
            universe_store=universe_store,
            sid_allocator=sid_allocator,
        )
```

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/hub.py
git add packages/datahub/src/ditto_datahub/init_providers.py
git commit -m "refactor(datahub): integrate MetadataQueryService into DataHub"
```

---

## 任务 8: 清理旧代码和文档更新

**文件:**
- 删除: `packages/datahub/src/ditto_datahub/accessors/security_accessor.py` (功能已迁移)
- 删除: `packages/datahub/src/ditto_datahub/accessors/calendar_accessor.py` (功能已迁移)
- 修改: `packages/datahub/README.md`

**步骤 1: 删除已迁移的 Accessor**

```bash
# 确认没有其他代码引用这些 Accessor
grep -r "from ditto_datahub.accessors.security_accessor" packages/datahub/
grep -r "from ditto_datahub.accessors.calendar_accessor" packages/datahub/

# 删除文件
git rm packages/datahub/src/ditto_datahub/accessors/security_accessor.py
git rm packages/datahub/src/ditto_datahub/accessors/calendar_accessor.py
```

**步骤 2: 更新 README**

```markdown
# DataHub Package

## 架构

### 域级组织

- `domains/metadata/`: Metadata 域
  - `security/`: 证券主数据
  - `identity/`: 标识符映射
  - `industry/`: 申万行业分类
  - `calendar/`: 交易日历
  - `universe/`: 标的池
  - `metadata_query_service.py`: 域级查询服务

- `domains/market/`: Market 域 (待实现)

## 使用示例

```python
# Metadata 查询
from ditto_datahub.domains.metadata import MetadataQueryService

sid = metadata.resolve_sid("600000.SH", source="tushare")
df = metadata.get_securities(sids=[sid], asset_class="stock")
```
```

**步骤 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/accessors/
git add packages/datahub/README.md
git commit -m "refactor(datahub): remove migrated accessors and update documentation"
```

---

## 任务 9: 创建 Git Tag

**步骤 1: 确保所有测试通过**

```bash
pixi run -e dev ci
```

**步骤 2: 创建 Tag**

```bash
git tag -a datahub-phase1-metadata-complete -m "完成 Metadata 域重构：domains/metadata/ 结构完整"
git push origin datahub-phase1-metadata-complete
```

---

## 验收标准

### 功能验收

- [ ] domains/metadata/ 目录结构完整
- [ ] SecurityStore 成功迁移到 metadata/security/
- [ ] IdentityStore 成功拆分并实现 PIT 查询
- [ ] IndustryBasicStore 和 IndustryMappingStore 实现完整
- [ ] CalendarStore 成功迁移到 metadata/calendar/
- [ ] MetadataQueryService 实现所有查询接口
- [ ] DataHub 集成 MetadataQueryService 完成
- [ ] 旧的 Accessor 成功删除

### 测试验收

- [ ] 新增测试覆盖率 ≥ 80%
- [ ] 所有现有测试通过
- [ ] 集成测试通过

### 文档验收

- [ ] README 更新完成
- [ ] API 文档完整

### 代码质量

- [ ] Pyright 类型检查通过 (strict)
- [ ] Ruff 代码检查通过
- [ ] Pre-commit hooks 通过

---

## 依赖关系

### 前置依赖

- Phase 0: 基础层重构 (BaseStore, DataRootConfig)

### 后续依赖

- Phase 2: Market 域重构 (依赖 Metadata 域的 identity 解析)

---

## 预计时间

- 任务 1: 0.5 天
- 任务 2-3: 2 天
- 任务 4: 1.5 天
- 任务 5: 1 天
- 任务 6: 2 天
- 任务 7: 1 天
- 任务 8-9: 1 天

**总计: 约 9 个工作日**
