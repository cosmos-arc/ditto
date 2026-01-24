# DataHub Accessors 模块重构设计

**日期**: 2026-01-23
**状态**: 设计已完成，待实施
**目标**: 提升 accessors 模块的架构清晰度，拆分可复用逻辑

---

## 一、背景分析

### 1.1 当前架构

```
DataHub (门面层)
  └── Accessors (业务逻辑层) ← 标识符转换逻辑分散在这里
      └── Stores (数据访问层)
```

### 1.2 识别的问题

| 问题 | 描述 | 影响 |
|------|------|------|
| **标识符处理重复** | SecuritiesAccessor、BarsAccessor 各自实现 | 逻辑不一致，维护成本高 |
| **enrich 逻辑分散** | enrich_with_sid、enrich_with_symbol、enrich_with_status 分散在多处 | 代码重复 |
| **批量操作模式不统一** | 各 Accessor 批量操作策略不同 | 无通用模式可复用 |
| **PIT 查询逻辑分散** | asof 参数处理逻辑在多处 | PIT 安全性风险 |

### 1.3 代码规模统计

| 访问器 | 代码行数 | 公开方法数 | 复杂度 |
|--------|----------|-----------|--------|
| BarsAccessor | 645 | 3 + 6私有 | ⭐⭐⭐⭐⭐ |
| SecuritiesAccessor | 512 | 12 | ⭐⭐⭐⭐ |
| IndexAccessor | 334 | 7 | ⭐⭐⭐ |
| UniverseAccessor | 301 | 7 | ⭐⭐⭐ |
| CalendarAccessor | 218 | 10 | ⭐⭐ |
| QuarantineAccessor | 195 | 5 | ⭐⭐ |
| IngestionLogAccessor | 257 | 5 | ⭐⭐ |
| AdjFactorAccessor | 95 | 1 | ⭐ |

---

## 二、重构方案

### 2.1 标识符处理

**确定方案**: DataHub 双层 API（便捷方法 + 底层方法）

**核心原则**:
- **Accessor 只接受 SID** - 数据访问层职责单一
- **DataHub 提供双层 API**：
  - **便捷 API**：支持混合标识符输入，自动转换
  - **底层 API**：直接访问 Accessor，只接受 SID
- **SecuritiesAccessor 作为底层解析服务** - 提供标识符解析的底层能力

**目标架构**:
```
┌─────────────────────────────────────────────────────────────┐
│                         用户代码                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ├─ 便捷 API（推荐大多数场景）
                     │   └─ hub.get_bars(src_codes=["000001.SZ"], ...)
                     │       ↓ 内部转换 SID
                     │       └─ hub.bars.get(sids=[1, ...])
                     │
                     └─ 底层 API（性能敏感，已知 SID）
                         └─ hub.bars.get(sids=[1, 2, 3], ...)
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                      DataHub (门面层)                          │
├─────────────────────────────────────────────────────────────┤
│  # ========== 便捷 API（支持混合标识符）==========        │
│  get_bars(src_codes, symbols, sids, ...) → DataFrame      │  ← 自动转换标识符
│  get_securities(src_codes, symbols, sids, ...) → DataFrame │
│  get_index_bars(symbols, sids, ...) → DataFrame            │
│                                                              │
│  # ========== 标识符转换门面 ============                 │
│  resolve_sid(identifier, source, asof) → int | None        │
│  resolve_identifiers(identifiers, source, asof) → dict      │
│  resolve_sids_from_inputs(sids, src_codes, symbols) → list │
│                                                              │
│  # ========== 底层 Accessor（只接受 SID）==============    │
│  bars: BarsAccessor     ← 只接受 sids=[...]               │
│  securities: SecuritiesAccessor                             │
│  calendar: CalendarAccessor                                 │
│  index: IndexAccessor                                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ├─ 标识符转换
                     │   └─ SecuritiesAccessor.resolve_identifiers_batch()
                     │       └─ SecurityStore
                     │
                     └─ 数据操作（只接受 SID）
                         └─ BarsAccessor.get(sids=[...])
                             └─ BarsStore
```

**DataHub 门面接口设计**:

```python
# packages/datahub/src/ditto_datahub/hub.py

class DataHub:
    """
    数据访问统一门面。

    提供两层 API：
    - 便捷 API：支持混合标识符输入，自动转换为 SID
    - 底层 API：直接访问 Accessor，只接受 SID（高性能）
    """

    # ========== 直接暴露 Accessor（底层 API，只接受 SID）==========
    bars: BarsAccessor
    securities: SecuritiesAccessor
    calendar: CalendarAccessor
    index: IndexAccessor
    # ...

    # ========== 便捷 API（支持混合标识符）==========

    def get_bars(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        ...
    ) -> pl.DataFrame:
        """
        获取 K 线数据（便捷 API，支持混合标识符）。

        内部自动将标识符转换为 SID，然后调用底层 Accessor。

        Args:
            sids: SID 列表（已知的 SID，无需转换）。
            src_codes: src_code 列表（需要转换）。
            symbols: symbol 列表（需要转换）。
            ...
        """
        resolved_sids = self.resolve_sids_from_inputs(sids, src_codes, symbols)
        return self.bars.get(sids=resolved_sids, start=start, end=end, ...)

    def get_securities(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        symbols: list[str] | None = None,
        ...
    ) -> pl.DataFrame:
        """获取证券数据（便捷 API）。"""
        resolved_sids = self.resolve_sids_from_inputs(sids, src_codes, symbols)
        return self.securities.get(sids=resolved_sids, ...)

    def get_index_bars(
        self,
        sids: list[int] | None = None,
        symbols: list[str] | None = None,
        ...
    ) -> pl.DataFrame:
        """获取指数 K 线（便捷 API）。"""
        resolved_sids = self.resolve_sids_from_inputs(sids, symbols=symbols)
        return self.index.get_bars(sids=resolved_sids, ...)

    # ========== 标识符转换门面 ==========

    def resolve_sid(
        self,
        identifier: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int | None:
        """解析单个标识符为 SID。"""
        return self.securities.resolve_identifier(identifier, source, asof)

    def resolve_identifiers(
        self,
        identifiers: list[str],
        source: str = "tushare",
        asof: str | None = None,
    ) -> dict[str, int]:
        """批量解析标识符为 SID。"""
        return self.securities.resolve_identifiers_batch(identifiers, source, asof)

    def resolve_sids_from_inputs(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        symbols: list[str] | None = None,
        source: str = "tushare",
        asof: str | None = None,
    ) -> list[int]:
        """从多种输入类型解析 SID 列表。"""
        resolved: set[int] = set()

        if sids:
            resolved.update(sids)

        if src_codes:
            mapping = self.resolve_identifiers(src_codes, source, asof)
            resolved.update(mapping.values())

        if symbols:
            for symbol in symbols:
                sid = self.resolve_sid(symbol, source, asof)
                if sid:
                    resolved.add(sid)

        return sorted(resolved)

    # ========== 反向解析门面 ==========

    def get_symbol(self, sid: int) -> str | None:
        """获取 SID 对应的 symbol。"""
        return self.securities.get_symbol(sid)

    def get_src_code(
        self,
        sid: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """获取 SID 对应的 src_code。"""
        return self.securities.get_src_code(sid, source, asof)

    def get_sid_symbol_mapping(self, sids: list[int]) -> dict[int, str]:
        """批量获取 SID 到 symbol 的映射。"""
        return self.securities.get_sid_symbol_map(sids)
```

**Accessor 接口简化**:

```python
# 之前：BarsAccessor 接受混合参数
class BarsAccessor:
    def get(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,  # ← 需要移除
        symbols: list[str] | None = None,    # ← 需要移除
        ...
    ):
        resolved_sids = self._resolve_sids(sids, src_codes, symbols, ...)
        # ...


# 之后：BarsAccessor 只接受 SID
class BarsAccessor:
    def get(
        self,
        sids: list[int],  # ← 只接受 SID
        start: str | None = None,
        end: str | None = None,
        ...
    ):
        # 直接使用 sids，无需解析
        return self._bars_store.read(sids=sids, ...)
```

**使用示例**:

```python
# 用户代码
hub = DataHub(...)

# ========== 便捷 API（推荐大多数场景）==========

# 场景 1: 使用 src_code/symbol（自动转换）
bars = hub.get_bars(
    src_codes=["000001.SZ", "000002.SZ"],
    symbols=["平安银行"],
    start="2024-01-01"
)

# 场景 2: 混合输入（sids + src_codes + symbols）
bars = hub.get_bars(
    sids=[1, 2],
    src_codes=["000003.SZ"],
    symbols=["万科A"],
)

# ========== 底层 API（性能敏感，已知 SID）==========

# 场景 3: 已知 SID，直接调用底层 Accessor
bars = hub.bars.get(sids=[1, 2, 3], start="2024-01-01")

# ========== 标识符转换（高级用法）==========

# 场景 4: 先转换，再使用（批量操作优化）
sids = hub.resolve_sids_from_inputs(
    src_codes=["000001.SZ", "000002.SZ"],
    symbols=["平安银行"],
)
bars = hub.bars.get(sids=sids, start="2024-01-01")
# 后续操作可以复用 sids
```

### 2.2 数据增强 (Enrichment)

**确定方案**: 纯数据 merge 函数

**目标模块**: `internal/enrichment.py`

```python
"""
数据增强纯函数模块。

提供 DataFrame 的列增强逻辑，纯数据操作，无 side effect。
"""

import polars as pl


def enrich_with_sid(
    df: pl.DataFrame,
    sid_mapping: dict[str, int],
    src_code_col: str = "ts_code",
    source: str = "tushare",
) -> pl.DataFrame:
    """
    使用 sid 映射字典为 DataFrame 添加 sid 列。

    Args:
        df: 输入 DataFrame，必须包含 src_code_col 指定的列。
        sid_mapping: {src_code: sid} 映射字典。
        src_code_col: 源代码列名。
        source: 数据源标识符。

    Returns:
        添加了 sid 和 source 列的 DataFrame。
    """
    src_codes = df[src_code_col].to_list()
    sids = [sid_mapping.get(code) for code in src_codes]

    return df.with_columns(
        pl.Series(sids, dtype=pl.Int32).alias("sid"),
        pl.lit(source).alias("source"),
    )


def enrich_with_symbol(
    df: pl.DataFrame,
    symbol_map: pl.DataFrame,
) -> pl.DataFrame:
    """
    使用 symbol 映射表为 DataFrame 添加 symbol 列。

    Args:
        df: 输入 DataFrame，必须包含 sid 列。
        symbol_map: symbol 映射表，包含 sid 和 symbol 列。

    Returns:
        添加了 symbol 列的 DataFrame。
    """
    if "sid" not in df.columns or df.is_empty():
        return df

    return df.join(symbol_map, on="sid", how="left")


def enrich_with_status(
    df: pl.DataFrame,
    status_df: pl.DataFrame,
    on: list[str] | None = None,
) -> pl.DataFrame:
    """
    使用状态数据表为 DataFrame 添加状态列。

    Args:
        df: 输入 DataFrame（通常包含 sid 和 trade_date）。
        status_df: 状态数据表，包含 is_suspended, is_st, st_type, list_status 等列。
        on: 连接键，默认 ["sid", "trade_date"]。

    Returns:
        添加了状态列的 DataFrame，缺失值填充为默认值。
    """
    if df.is_empty():
        return df

    join_keys = on or ["sid", "trade_date"]

    # Select only status columns
    status_cols = ["sid", "trade_date", "is_suspended", "suspend_timing",
                   "is_st", "st_type", "list_status"]
    status_to_join = status_df.select(
        [c for c in status_cols if c in status_df.columns]
    )

    result = df.join(status_to_join, on=join_keys, how="left")

    # Fill null values with defaults
    return result.with_columns(
        pl.col("is_suspended").fill_null(False),
        pl.col("suspend_timing").fill_null(""),
        pl.col("is_st").fill_null(False),
        pl.col("st_type").fill_null(""),
        pl.col("list_status").fill_null("L"),
    )
```

**职责划分**:

| 层级 | 职责 | 示例 |
|------|------|------|
| **Accessor** | 获取映射数据（调用 Store） | `sid_map = store.get_sid_mapping()` |
| **internal/enrichment.py** | 纯数据 merge 逻辑 | `enrich_with_sid(df, sid_map)` |

**使用方式**:

```python
# SecuritiesAccessor
from ditto_datahub.accessors.internal.enrichment import enrich_with_sid

class SecuritiesAccessor:
    def enrich_dataframe_with_sid(self, df, source, asset_class, src_code_col="ts_code"):
        # 获取映射数据（Accessor 的职责）
        sid_mapping = self.resolve_or_create_batch(df, source, asset_class, src_code_col)

        # 纯数据 merge（enrichment 的职责）
        return enrich_with_sid(df, sid_mapping, src_code_col, source)
```

### 2.3 批量操作

**确定方案**: **不拆分**

**理由**:
- 不同操作的批量策略差异大（数据库批量写入 vs 内存循环）
- polars 本身就是批量操作框架
- 强行抽象会增加复杂度

**保持现状**: 各 Accessor 根据自己的特点实现批量逻辑。

### 2.4 PIT 查询逻辑

**确定方案**: 纯函数模块

**目标模块**: `internal/pit.py`

```python
"""
PIT (Point-in-Time) 查询纯函数模块。

提供 PIT 安全的日期过滤逻辑。
"""

from datetime import date

import polars as pl


def parse_asof_date(asof: date | str) -> date:
    """
    解析 asof 参数为 date 对象。

    Args:
        asof: date 对象或 ISO 格式字符串。

    Returns:
        解析后的 date 对象。
    """
    if isinstance(asof, str):
        return date.fromisoformat(asof)
    return asof


def filter_by_knowledge_date(
    df: pl.DataFrame,
    pit_dt: date,
    date_column: str = "knowledge_date",
) -> pl.DataFrame:
    """
    根据 PIT 日期过滤数据（优先使用 knowledge_date）。

    Args:
        df: 输入 DataFrame。
        pit_dt: Point-in-Time 日期。
        date_column: 日期列名，默认 knowledge_date。

    Returns:
        过滤后的 DataFrame。
    """
    if date_column in df.columns:
        return df.filter(pl.col(date_column) <= pit_dt)

    # Fallback to trade_date (会记录警告)
    if "trade_date" in df.columns:
        logger.warning(
            f"Data missing {date_column}, using trade_date (not PIT-safe)",
            event="pit_missing_knowledge_date",
        )
        return df.filter(pl.col("trade_date") <= pit_dt)

    return df
```

**与现有 adjustment.py 的关系**:

| 模块 | 职责 |
|------|------|
| `internal/adjustment.py` | 复权计算（业务特定） |
| `internal/pit.py` | PIT 日期过滤（通用逻辑） |

---

## 三、文件结构

### 3.1 新增文件

```
packages/datahub/src/ditto_datahub/accessors/internal/
├── __init__.py              # 现有
├── adjustment.py            # 现有
├── enrichment.py            # 新增：数据增强纯函数
└── pit.py                   # 新增：PIT 查询纯函数
```

### 3.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `security_accessor.py` | 使用 `enrichment.enrich_with_sid()` |
| `bars_accessor.py` | 使用 `enrichment.enrich_with_status()` |
| `security_store.py` | 使用 `enrichment.enrich_with_symbol()` |
| `hub.py` | 添加统一标识符转换门面（方案 A 确定后） |

---

## 四、实施步骤

### 阶段 1: enrichment 纯函数提取（优先）

1. 创建 `internal/enrichment.py`
2. 编写单元测试
3. 重构 `SecuritiesAccessor.enrich_dataframe_with_sid()`
4. 重构 `SecurityStore.enrich_with_symbol()`
5. 重构 `BarsAccessor._enrich_with_status()`
6. 运行测试验证

### 阶段 2: PIT 纯函数提取

1. 创建 `internal/pit.py`
2. 编写单元测试
3. 重构 `adjustment.py` 使用 `pit.parse_asof_date()`
4. 重构各 Accessor 的 PIT 逻辑
5. 运行测试验证

### 阶段 3: 标识符处理重构（DataHub 双层 API）

**步骤 1: 重构 BarsAccessor（简化接口）**

1. 修改 `BarsAccessor.get()` 签名：
   - 移除 `src_codes`, `symbols` 参数
   - 只保留 `sids` 参数
   - 移除 `_resolve_sids()` 私有方法

2. 更新相关方法：
   - `_get_bars_for_sids()` - 直接接受 sids
   - `_fetch_and_merge_adj_factors()` - 使用 sids

3. 编写单元测试

**步骤 2: 重构 IndexAccessor**

1. 修改 `IndexAccessor.get_bars()` 签名：
   - 移除 `symbols` 参数
   - 只保留 `sids` 参数

2. 移除内联的标识符解析逻辑

3. 编写单元测试

**步骤 3: 增强 DataHub（添加双层 API）**

1. 添加标识符转换方法：
   - `resolve_sid()` - 单个标识符转换
   - `resolve_identifiers()` - 批量标识符转换
   - `resolve_sids_from_inputs()` - 混合输入解析
   - `get_symbol()`, `get_src_code()` - 反向解析
   - `get_sid_symbol_mapping()` - 批量映射

2. 添加便捷 API 方法：
   - `get_bars(src_codes, symbols, sids, ...)` - 自动转换标识符
   - `get_securities(src_codes, symbols, sids, ...)`
   - `get_index_bars(symbols, sids, ...)`

3. 编写单元测试验证便捷方法

**步骤 4: 更新用户代码**

1. 更新 `apps/port` 中使用这些 Accessor 的代码：
   - 优先使用便捷 API：`hub.get_bars(src_codes=...)`
   - 性能敏感场景使用底层 API：`hub.bars.get(sids=...)`

2. 更新测试代码

**步骤 5: 运行集成测试**

1. 运行完整的测试套件
2. 验证 PIT 查询正确性
3. 性能测试（标识符解析缓存）

---

## 五、待确认事项

| 事项 | 状态 |
|------|------|
| enrichment 纯函数设计方案 | ✅ 已确认 |
| PIT 纯函数设计方案 | ✅ 已确认 |
| 批量操作不拆分 | ✅ 已确认 |
| 标识符处理方案（DataHub 双层 API） | ✅ 已确认 |
| DataHub 双层 API 设计 | ✅ 已完成 |
| 重构实施步骤优先级 | ✅ 已确认（enrichment → 标识符 → PIT） |

---

## 六、关键文件清单

### 新增文件

| 文件 | 用途 | 优先级 |
|------|------|--------|
| `packages/datahub/src/ditto_datahub/accessors/internal/enrichment.py` | 数据增强纯函数 | 高 |
| `packages/datahub/src/ditto_datahub/accessors/internal/pit.py` | PIT 查询纯函数 | 中 |

### 修改文件

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| `packages/datahub/src/ditto_datahub/hub.py` | 添加标识符转换门面方法 | 高 |
| `packages/datahub/src/ditto_datahub/accessors/bars_accessor.py` | 简化接口（移除 src_codes/symbols） | 高 |
| `packages/datahub/src/ditto_datahub/accessors/index_accessor.py` | 简化接口（移除 symbols） | 中 |
| `packages/datahub/src/ditto_datahub/accessors/security_accessor.py` | 使用 enrichment 纯函数 | 中 |
| `packages/datahub/src/ditto_datahub/stores/security_store.py` | 使用 enrichment 纯函数 | 中 |
| `packages/datahub/src/ditto_datahub/accessors/internal/adjustment.py` | 使用 pit 纯函数 | 低 |

---

## 七、架构收益

| 方面 | 改进 |
|------|------|
| **职责清晰** | DataHub 处理标识符转换，Accessor 只处理数据 |
| **代码复用** | enrichment、pit 纯函数可被多处复用 |
| **可测试性** | 纯函数易于单元测试 |
| **PIT 安全** | PIT 逻辑集中管理，减少出错风险 |
| **维护性** | 标识符转换逻辑统一，不再分散重复 |

---

## 八、实施优先级建议

| 阶段 | 优先级 | 理由 |
|------|--------|------|
| **阶段 1: enrichment** | 🔥 高 | 独立性强，风险低，收益明显 |
| **阶段 2: 标识符处理** | 🔥 高 | 架构改进核心，影响范围大 |
| **阶段 3: PIT** | 中 | 优化性质，可与阶段 1/2 同步进行 |

---

## 九、参考

- 相关文件: `packages/datahub/src/ditto_datahub/accessors/`
- 设计模式参考: `internal/adjustment.py`（纯函数模块）
- 架构原则: 单一职责、门面模式、纯函数优先
