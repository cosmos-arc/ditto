---
paths: **/*.py
---

# Python Code Style Rules

## 1. 核心原则

### 1.1 AI 协作基本约定

```
优先级：正确性 > 可读性 > 性能 > 简洁性
```

- **显式优于隐式**：类型注解、返回值、边界条件都要明确
- **小步迭代**：每次修改聚焦单一职责，便于 review 和回滚
- **自解释代码**：命名和结构应减少对注释的依赖
- **防御性编程**：假设输入可能异常，显式处理边界情况

### 1.2 与工具链对齐

| 工具 | 职责 | 检查时机 |
|------|------|----------|
| Ruff | 格式化 + Lint | 保存时 / pre-commit |
| Pyright | 实时类型检查 | 编辑器内 |
| Mypy | 严格类型检查 | CI/CD |

---

## 2. 代码格式

### 2.1 模块文档字符串格式（重要）

**规则**: 模块文档字符串必须在所有 imports 之前。

```python
# ✅ 正确：单行文档字符串
"""Single-line module docstring."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import polars as pl


# ✅ 正确：多行文档字符串
"""Multi-line module docstring.

Details about the module purpose and usage.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import polars as pl


# ❌ 错误：文档字符串在 imports 之后
from __future__ import annotations
from datetime import datetime

"""Module docstring after imports (violates D213 rule)."""


# ❌ 错误：不符合 D213 规则
"""Module docstring
with summary on first line.
"""

from __future__ import annotations
# 触发 D213：Multi-line docstring summary should start at second line
```

**Ruff D213 规则**: 多行文档字符串的 summary 后需要空一行，details 在新行。

### 2.2 基本格式（Ruff 自动处理）

```python
# 行长度：88 字符
# 缩进：4 空格
# 引号：双引号优先
# 尾随逗号：保留（减少 git diff 噪音）
```

### 2.3 导入顺序（isort 规则）

```python
# 1. 标准库
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

# 2. 第三方库
import polars as pl
from pydantic import BaseModel

# 3. 本地模块
from ditto.core.engine import TradingEngine
from ditto.models.signal import Signal

# 4. 类型检查专用导入（避免循环依赖）
if TYPE_CHECKING:
    from ditto.core.portfolio import Portfolio
```

### 2.3 空行规范

```python
# 模块级：顶层定义之间 2 空行
class FirstClass:
    pass


class SecondClass:
    pass


# 类内部：方法之间 1 空行
class MyClass:
    def method_one(self) -> None:
        pass

    def method_two(self) -> None:
        pass


# 函数内部：逻辑块之间 1 空行（可选）
def process_data(df: pl.DataFrame) -> pl.DataFrame:
    # 数据清洗
    df = df.drop_nulls()
    df = df.unique()

    # 特征计算
    df = df.with_columns(
        pl.col("close").pct_change().alias("returns"),
    )

    return df
```

---

## 3. 类型注解

### 3.1 基本规则

```python
# ✅ 所有公共函数必须有完整类型注解
def calculate_sharpe(
    returns: pl.Series,
    risk_free_rate: float = 0.0,
    periods: int = 252,
) -> float:
    ...


# ✅ 使用 Python 3.11+ 原生类型语法
def get_symbols() -> list[str]:  # 不用 List[str]
    ...

def get_config() -> dict[str, Any]:  # 不用 Dict[str, Any]
    ...

def find_signal(symbol: str) -> Signal | None:  # 不用 Optional[Signal]
    ...


# ✅ 复杂类型使用 TypeAlias
type PriceData = dict[str, pl.DataFrame]
type SignalHandler = Callable[[Signal], Awaitable[None]]


# ✅ 类方法返回 Self（3.11+）
from typing import Self

class Strategy:
    def with_params(self, **kwargs: Any) -> Self:
        ...
        return self
```

### 3.2 泛型与协议

```python
from typing import Protocol, TypeVar

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


# 使用 Protocol 定义接口
class DataSource(Protocol):
    def fetch(self, symbol: str) -> pl.DataFrame: ...
    def validate(self) -> bool: ...


# 泛型容器
class Cache[K, V]:  # Python 3.12+ 语法
    def __init__(self) -> None:
        self._store: dict[K, V] = {}

    def get(self, key: K) -> V | None:
        return self._store.get(key)
```

### 3.3 类型窄化

```python
# ✅ 使用 TypeGuard 进行类型窄化
from typing import TypeGuard

def is_valid_signal(obj: object) -> TypeGuard[Signal]:
    return isinstance(obj, Signal) and obj.strength > 0


# ✅ assert 用于类型窄化（仅开发环境）
def process(value: str | None) -> str:
    assert value is not None, "Value must not be None"
    return value.upper()


# ✅ 使用 cast 作为最后手段（需注释说明原因）
from typing import cast

# cast 用于 Polars 已知但类型系统不识别的情况
result = cast(float, df.select(pl.col("value").mean()).item())
```

### 3.4 DataFrame 驱动系统的类型策略

**核心原则**: 在量化系统中，数据流向为 `SQLite → Polars DataFrame → 向量化运算`。
中间层的 Row 对象（TypedDict）是冗余的，TypedDict 可能是反模式。

#### 何时使用 TypedDict

| 场景 | 是否使用 TypedDict | 原因 |
|------|-------------------|------|
| DataFrame 列数据 | ❌ 不使用 | Polars 提供运行时类型安全 |
| SQL 直接返回值 | ✅ 可使用 | API 边界需要明确契约 |
| 配置/元数据 | ✅ 推荐 | 静态结构，需要文档化 |
| 测试 fixture | ✅ 推荐 | 明确预期结构 |

#### 务实的类型注解策略

```python
# ✅ 好：使用具体类型替代 Any
from ditto_datahub.types import DQResult

@dataclass
class WriteResult:
    """Data write result."""
    path: str
    checksum: str
    failed_checks: list[DQResult]  # 而非 list[Any]


# ✅ 好：SQL 返回值使用具体联合类型
def fetchval(
    self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
) -> str | int | float | None:
    """Fetch first column of first row.

    Returns:
        str | int | float | None: Value from the first column.
    """
    row = self.fetchone(sql, params)
    if row:
        return cast(str | int | float, row[0])
    return None


# ✅ 可接受：低频查询使用 dict[str, Any]
def get_metadata(self) -> dict[str, Any]:
    """Get flexible metadata.

    低频调用、结构多变的情况，dict[str, Any] 是务实的妥协。
    """
    return self._meta


# ❌ 避免：为 SQL 返回值创建 TypedDict
class SecurityRow(TypedDict):
    """Security data row from SQLite."""
    sid: int
    symbol: str
    name: str | None
    # ...

def get_security(sid: int) -> SecurityRow:
    """❌ 冗余：应该直接返回 DataFrame"""
    ...

# ✅ 推荐：返回 DataFrame，让 Polars 提供类型安全
def get_securities(sids: list[int]) -> pl.DataFrame:
    """Get securities as DataFrame.

    Polars LazyFrame 在 Plan 阶段就能验证 Schema，提供更好的类型安全。
    """
    ...
```

#### 类型精确化的优先级

| 优先级 | 问题类型 | 示例 | 是否修复 |
|--------|----------|------|----------|
| P0 | `Any` 返回类型 | `def foo() -> Any:` | ✅ 必须修复 |
| P0 | `Any` 参数类型 | `def foo(x: Any):` | ✅ 必须修复 |
| P1 | `list[Any]` 具体类型已知 | `list[DQResult]` | ✅ 建议修复 |
| P2 | `dict[str, Any]` 灵活配置 | 元数据、配置 | ⚠️ 可保留 |
| P3 | SQL 返回 TypedDict | `SecurityRow` | ❌ 反模式 |

#### 类型别名最佳实践

```python
# ✅ 定义输入类型别名
from datetime import date, datetime

DateInput = str | date | datetime | None

def normalize_date(value: DateInput) -> str | None:
    """Normalize various date input types to YYYY-MM-DD string."""
    if value is None:
        return None
    if isinstance(value, str):
        datetime.strptime(value, "%Y-%m-%d")
        return value
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    raise TypeError(f"Unsupported date type: {type(value)}")


# ✅ 使用 Sequence 替代 list 提高灵活性
from collections.abc import Sequence

def get_symbols(symbols: Sequence[str]) -> pl.DataFrame:
    """Accept any sequence of strings (list, tuple, set, etc.)."""
    ...


# ✅ 使用 Literal 限定字符串选项
from typing import Literal

AdjustmentType = Literal["qfq", "hfq", "none"]

def apply_adjustment(
    df: pl.DataFrame,
    adj_type: AdjustmentType = "none",
) -> pl.DataFrame:
    """Apply price adjustment."""
    ...
```

---

## 4. 命名规范

### 4.1 基本约定

| 类型 | 风格 | 示例 |
|------|------|------|
| 模块 | snake_case | `data_loader.py` |
| 类 | PascalCase | `TradingEngine` |
| 函数/方法 | snake_case | `calculate_returns` |
| 变量 | snake_case | `daily_returns` |
| 常量 | SCREAMING_SNAKE | `MAX_POSITION_SIZE` |
| 类型别名 | PascalCase | `PriceData` |
| 私有成员 | `_`前缀 | `_internal_state` |
| "真正"私有 | `__`前缀 | `__secret`（慎用）|

### 4.2 命名语义

```python
# ✅ 布尔变量/函数：is_, has_, can_, should_
is_valid: bool
has_position: bool
can_trade: bool
def should_rebalance() -> bool: ...

# ✅ 集合类型：复数形式
symbols: list[str]
price_map: dict[str, float]
active_orders: set[Order]

# ✅ 动词开头的函数名
def fetch_data() -> pl.DataFrame: ...
def calculate_pnl() -> float: ...
def validate_order(order: Order) -> bool: ...

# ✅ 工厂方法：create_, from_, build_
@classmethod
def from_config(cls, config: Config) -> Self: ...

def create_engine(mode: str) -> TradingEngine: ...

# ✅ 转换方法：to_, as_
def to_dataframe(self) -> pl.DataFrame: ...
def as_dict(self) -> dict[str, Any]: ...
```

### 4.3 避免的命名

```python
# ❌ 避免
data, info, temp, result, value  # 太泛化
df, df2, df_new  # 无意义后缀
process_data()  # "process" 含义模糊
handle_stuff()  # 不清晰

# ✅ 改为
price_data, order_info, cached_result
raw_prices, cleaned_prices, enriched_prices
normalize_prices()
route_order_to_exchange()
```

---

## 5. 文档字符串

### 5.1 基本格式（Google Style）

```python
def calculate_rolling_sharpe(
    returns: pl.Series,
    window: int,
    risk_free_rate: float = 0.0,
) -> pl.Series:
    """计算滚动夏普比率。

    使用指定窗口大小计算历史滚动夏普比率，适用于策略表现的时序分析。

    Args:
        returns: 日收益率序列，应为小数形式（如 0.01 表示 1%）。
        window: 滚动窗口大小（交易日数）。
        risk_free_rate: 年化无风险利率，默认为 0。

    Returns:
        与输入等长的夏普比率序列，前 window-1 个值为 null。

    Raises:
        ValueError: 当 window 小于 2 时抛出。

    Example:
        >>> returns = pl.Series([0.01, -0.02, 0.015, 0.008])
        >>> calculate_rolling_sharpe(returns, window=3)

    Note:
        - 假设 252 个交易日/年进行年化
        - 结果未经年化调整时需乘以 sqrt(252)
    """
```

### 5.2 简洁版本（简单函数）

```python
def get_trading_dates(start: date, end: date) -> list[date]:
    """获取指定范围内的交易日列表。"""
    ...


def is_market_open() -> bool:
    """检查当前市场是否处于交易时段。"""
    ...
```

### 5.3 类文档字符串

```python
class ETFRotationStrategy:
    """ETF 轮动策略实现。

    基于动量和波动率因子进行 ETF 板块轮动，支持多种调仓频率。

    Attributes:
        universe: 策略 ETF 池。
        lookback: 动量计算回溯期（交易日）。
        top_n: 持仓数量上限。

    Example:
        >>> strategy = ETFRotationStrategy(
        ...     universe=["510300", "510500", "510880"],
        ...     lookback=20,
        ...     top_n=2,
        ... )
        >>> signals = strategy.generate_signals(price_data)
    """
```

---

## 6. 错误处理

### 6.1 异常设计

```python
# ✅ 定义领域异常层次
class DittoError(Exception):
    """Ditto 系统基础异常。"""


class DataError(DittoError):
    """数据相关异常。"""


class DataNotFoundError(DataError):
    """请求的数据不存在。"""

    def __init__(self, symbol: str, date: date) -> None:
        self.symbol = symbol
        self.date = date
        super().__init__(f"No data for {symbol} on {date}")


class ValidationError(DittoError):
    """数据/参数验证失败。"""


class TradingError(DittoError):
    """交易执行相关异常。"""


class RiskLimitExceededError(TradingError):
    """风控限制触发。"""
```

### 6.2 异常处理模式

```python
# ✅ 精确捕获，明确处理
def fetch_price(symbol: str) -> pl.DataFrame:
    try:
        return data_source.get(symbol)
    except ConnectionError as e:
        logger.warning("Data source unavailable: %s", e)
        return load_from_cache(symbol)
    except DataNotFoundError:
        raise  # 重新抛出，让调用方处理


# ✅ 使用 contextmanager 管理资源
from contextlib import contextmanager

@contextmanager
def database_transaction():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ✅ 早期返回 / 快速失败
def validate_order(order: Order) -> None:
    if order.quantity <= 0:
        raise ValidationError("Quantity must be positive")

    if order.symbol not in TRADABLE_UNIVERSE:
        raise ValidationError(f"Symbol {order.symbol} not tradable")

    if order.price < 0:
        raise ValidationError("Price cannot be negative")
```

### 6.3 日志记录

```python
import logging
from typing import Any

logger = logging.getLogger(__name__)


def process_order(order: Order) -> TradeResult:
    logger.info("Processing order: %s", order.id)

    try:
        result = execute(order)
        logger.info(
            "Order executed: id=%s, filled=%d, avg_price=%.4f",
            order.id,
            result.filled_quantity,
            result.avg_price,
        )
        return result
    except TradingError as e:
        logger.exception("Order execution failed: %s", order.id)
        raise


# ✅ 结构化日志
def log_trade(trade: Trade) -> None:
    logger.info(
        "Trade completed",
        extra={
            "trade_id": trade.id,
            "symbol": trade.symbol,
            "side": trade.side,
            "quantity": trade.quantity,
            "price": trade.price,
            "timestamp": trade.timestamp.isoformat(),
        },
    )
```

---

## 7. 类与数据结构

### 7.1 数据类优先

```python
from dataclasses import dataclass, field
from datetime import datetime


# ✅ 简单数据容器：dataclass
@dataclass(frozen=True, slots=True)
class Signal:
    """交易信号。"""

    symbol: str
    direction: int  # 1: long, -1: short, 0: neutral
    strength: float
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


# ✅ 需要验证的数据：Pydantic
from pydantic import BaseModel, Field, field_validator


class OrderRequest(BaseModel):
    """订单请求。"""

    symbol: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    side: Literal["buy", "sell"]

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        if not v.isalnum():
            raise ValueError("Symbol must be alphanumeric")
        return v.upper()
```

### 7.2 类设计原则

```python
# ✅ 组合优于继承
class TradingEngine:
    def __init__(
        self,
        data_source: DataSource,
        risk_manager: RiskManager,
        executor: OrderExecutor,
    ) -> None:
        self._data_source = data_source
        self._risk_manager = risk_manager
        self._executor = executor


# ✅ 依赖注入
class BacktestEngine:
    def __init__(self, config: BacktestConfig) -> None:
        self._config = config
        self._data_source: DataSource | None = None

    def with_data_source(self, source: DataSource) -> Self:
        self._data_source = source
        return self


# ✅ 明确区分公共/私有 API
class Portfolio:
    def __init__(self) -> None:
        self._positions: dict[str, Position] = {}
        self._cash: float = 0.0

    # 公共 API
    @property
    def total_value(self) -> float:
        return self._cash + self._position_value

    def add_position(self, symbol: str, quantity: int, price: float) -> None:
        ...

    # 私有方法
    @property
    def _position_value(self) -> float:
        return sum(p.market_value for p in self._positions.values())
```

---

## 8. Polars 特定规范

### 8.1 表达式风格

```python
# ✅ 链式表达式，每个操作一行
result = (
    df.lazy()
    .filter(pl.col("date") >= start_date)
    .with_columns(
        pl.col("close").pct_change().alias("returns"),
        pl.col("volume").rolling_mean(window_size=20).alias("avg_volume"),
    )
    .group_by("sector")
    .agg(
        pl.col("returns").mean().alias("avg_returns"),
        pl.col("returns").std().alias("volatility"),
    )
    .sort("avg_returns", descending=True)
    .collect()
)


# ✅ 复杂表达式提取为变量
momentum_expr = (
    pl.col("close")
    .pct_change(n=20)
    .over("symbol")
    .alias("momentum_20d")
)

volatility_expr = (
    pl.col("returns")
    .rolling_std(window_size=20)
    .over("symbol")
    .alias("volatility_20d")
)

df = df.with_columns(momentum_expr, volatility_expr)
```

### 8.2 性能最佳实践

```python
# ✅ 优先使用 LazyFrame
def process_large_dataset(path: Path) -> pl.DataFrame:
    return (
        pl.scan_parquet(path)
        .filter(...)
        .select(...)
        .collect()
    )


# ✅ 避免 Python 循环，使用向量化操作
# ❌ 错误
for i, row in enumerate(df.iter_rows()):
    df[i, "new_col"] = some_calculation(row)

# ✅ 正确
df = df.with_columns(
    pl.struct(["col1", "col2"])
    .map_elements(some_calculation, return_dtype=pl.Float64)
    .alias("new_col")
)


# ✅ 使用表达式而非 apply
# ❌ 避免
df.with_columns(
    pl.col("price").apply(lambda x: x * 1.1).alias("adjusted")
)

# ✅ 推荐
df.with_columns(
    (pl.col("price") * 1.1).alias("adjusted")
)
```

### 8.3 Point-in-Time 数据安全

```python
# ✅ 始终使用 as-of join 避免未来信息泄露
def join_with_fundamentals(
    prices: pl.DataFrame,
    fundamentals: pl.DataFrame,
) -> pl.DataFrame:
    """合并价格与基本面数据，确保 PIT 安全。"""
    return prices.join_asof(
        fundamentals.sort("report_date"),
        left_on="date",
        right_on="report_date",
        by="symbol",
        strategy="backward",  # 只使用历史数据
    )


# ✅ 显式标注数据时间点
@dataclass
class PriceSnapshot:
    """某一时刻的价格快照。"""

    symbol: str
    price: float
    as_of: datetime  # 明确标注数据时间点
```

---

## 9. 配置与常量

### 9.1 配置管理

```python
# ✅ 使用 Pydantic Settings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingConfig(BaseSettings):
    """交易系统配置。"""

    model_config = SettingsConfigDict(
        env_prefix="DITTO_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # 数据配置
    data_path: Path = Field(default=Path("./data"))
    cache_ttl: int = Field(default=3600, ge=0)

    # 交易配置
    max_position_size: float = Field(default=0.1, ge=0, le=1)
    risk_free_rate: float = Field(default=0.02)

    # 风控配置
    max_drawdown_pct: float = Field(default=0.15, ge=0, le=1)
    kill_switch_threshold: float = Field(default=0.20, ge=0, le=1)
```

### 9.2 常量定义

```python
# ✅ 模块级常量
TRADING_DAYS_PER_YEAR: Final[int] = 252
MARKET_OPEN_TIME: Final[time] = time(9, 30)
MARKET_CLOSE_TIME: Final[time] = time(15, 0)

# ✅ 使用枚举表示有限状态集
from enum import Enum, auto


class OrderStatus(Enum):
    """订单状态。"""

    PENDING = auto()
    SUBMITTED = auto()
    PARTIAL_FILLED = auto()
    FILLED = auto()
    CANCELLED = auto()
    REJECTED = auto()


class Side(Enum):
    """交易方向。"""

    BUY = "buy"
    SELL = "sell"
```

---

## 10. AI 协作特定指南

### 10.1 代码生成请求格式

```markdown
当向 Claude 请求代码时，提供：

1. **上下文**：相关的现有代码、类型定义
2. **需求**：具体要实现什么功能
3. **约束**：性能要求、兼容性考虑
4. **示例**：输入输出示例（如适用）
```

### 10.2 代码审查检查清单

```python
# Claude 生成代码后，检查：

# □ 类型注解完整且正确
# □ 错误处理覆盖边界情况
# □ 命名符合规范且语义清晰
# □ 无硬编码魔法数字
# □ Docstring 准确描述功能
# □ 无未使用的导入或变量
# □ Polars 操作使用惰性执行
# □ 无潜在的 PIT 数据泄露
```

### 10.3 渐进式开发模式

```python
# 1. 先定义接口/类型
class Strategy(Protocol):
    def generate_signals(self, data: pl.DataFrame) -> list[Signal]: ...


# 2. 实现骨架
class MomentumStrategy:
    def generate_signals(self, data: pl.DataFrame) -> list[Signal]:
        raise NotImplementedError


# 3. 逐步填充实现
class MomentumStrategy:
    def generate_signals(self, data: pl.DataFrame) -> list[Signal]:
        ranked = self._rank_by_momentum(data)
        return self._create_signals(ranked)

    def _rank_by_momentum(self, data: pl.DataFrame) -> pl.DataFrame:
        # TODO: 实现动量排名
        ...

    def _create_signals(self, ranked: pl.DataFrame) -> list[Signal]:
        # TODO: 生成信号
        ...
```

---

## 11. 模块组织约定

```python
# ✅ 每个模块单一职责
# data/sources.py - 只处理数据源
# data/transforms.py - 只处理数据转换
# data/cache.py - 只处理缓存

# ✅ __init__.py 显式导出公共 API
# packages/core/src/ditto_core/__init__.py
from ditto_core.engine import TradingEngine
from ditto_core.portfolio import Portfolio

__all__ = ["TradingEngine", "Portfolio"]
```

---

## 12. 快速参考

### Ruff 常用 noqa

```python
x = some_complex_function()  # noqa: C901 (复杂度)
from module import *  # noqa: F403 (通配符导入)
unused_var = compute()  # noqa: F841 (未使用变量)
```

### Pyright/Mypy 类型忽略

```python
result = external_lib.call()  # type: ignore[no-untyped-call]
value: Any = dynamic_result  # type: ignore[assignment]
```

### 常用类型导入

```python
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Literal,
    Protocol,
    Self,
    TypeAlias,
    TypeGuard,
    TypeVar,
    cast,
    overload,
)
```

---

## 附录：工具命令速查

```bash
# 格式化
ruff format .

# Lint 检查
ruff check .

# Lint 自动修复
ruff check --fix .

# 类型检查
pyright
mypy .

# 一键全检（推荐 alias）
ruff format . && ruff check . && pyright
```
