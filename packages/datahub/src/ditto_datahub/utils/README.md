# Utils - 工具模块

## 功能概述

提供数据访问层常用的工具函数和辅助方法，包括日期处理、数据转换、验证等功能。

## 核心工具

### DateInput - 日期输入类型

```python
from ditto_datahub.utils import DateInput, normalize_date

# 支持多种日期输入格式
date1: DateInput = "2024-01-02"           # ISO 字符串
date2: DateInput = datetime(2024, 1, 2)   # datetime 对象
date3: DateInput = date(2024, 1, 2)       # date 对象
```

### normalize_date - 日期标准化

```python
from ditto_datahub.utils import normalize_date

# 标准化为 date 对象
d = normalize_date("2024-01-02")
# -> datetime.date(2024, 1, 2)

d = normalize_date(datetime(2024, 1, 2, 10, 30, 0))
# -> datetime.date(2024, 1, 2)

d = normalize_date(date(2024, 1, 2))
# -> datetime.date(2024, 1, 2)
```

## 使用示例

### 日期处理

```python
from ditto_datahub.utils import normalize_date
from datetime import datetime, date

# 1. 统一日期输入接口
def query_bars(start: DateInput, end: DateInput):
    start_date = normalize_date(start)
    end_date = normalize_date(end)

    # 现在可以统一处理为 date 对象
    print(f"Query from {start_date} to {end_date}")

# 调用
query_bars("2024-01-01", "2024-12-31")
query_bars(date(2024, 1, 1), datetime(2024, 12, 31))
```

### 类型验证

```python
from ditto_datahub.utils import normalize_date

def validate_date_input(value: DateInput) -> date:
    """验证并标准化日期输入"""
    try:
        return normalize_date(value)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid date input: {value}") from e
```

## 设计原则

### 1. 类型安全

```python
# 使用类型注解确保输入类型正确
from typing import Union

DateInput = Union[str, datetime, date]

def process_date(value: DateInput) -> date:
    return normalize_date(value)
```

### 2. 幂等性

```python
# 多次调用结果一致
d1 = normalize_date("2024-01-02")
d2 = normalize_date(d1)
d3 = normalize_date(d2)

assert d1 == d2 == d3
```

### 3. 错误处理

```python
# 标准化失败时抛出清晰的异常
try:
    normalize_date("invalid-date")
except ValueError as e:
    print(f"日期格式错误: {e}")
```

## 集成示例

### 与 Repository 集成

```python
from ditto_datahub.utils import normalize_date
from typing import Union

DateInput = Union[str, datetime, date]

class BarsRepository:
    def get(
        self,
        start: DateInput | None = None,
        end: DateInput | None = None,
    ):
        # 标准化日期
        start_date = normalize_date(start) if start else None
        end_date = normalize_date(end) if end else None

        # 使用标准化后的日期查询
        return self._store.read(
            start_date=start_date,
            end_date=end_date,
        )
```

### 与 Query Builder 集成

```python
from ditto_datahub.utils import normalize_date

class QueryBuilder:
    def where_date_between(
        self,
        column: str,
        start: DateInput,
        end: DateInput,
    ):
        return self._filter(
            pl.col(column).is_between(
                normalize_date(start),
                normalize_date(end),
            )
        )
```

## 扩展工具

### 自定义日期工具

```python
from ditto_datahub.utils import normalize_date
from datetime import date, timedelta

def get_trading_date(input_date: DateInput, offset: int = 0) -> date:
    """
    获取交易日（偏移 offset 天）

    Args:
        input_date: 日期输入
        offset: 偏移天数

    Returns:
        交易日
    """
    base_date = normalize_date(input_date)
    target_date = base_date + timedelta(days=offset)

    # 这里可以调用 CalendarRepository 判断是否交易日
    return target_date

# 使用
target = get_trading_date("2024-01-02", offset=1)
# -> datetime.date(2024, 1, 3)
```

### 日期范围工具

```python
from ditto_datahub.utils import normalize_date
from datetime import date
from typing import Generator

def date_range(
    start: DateInput,
    end: DateInput,
    inclusive: bool = True,
) -> Generator[date, None, None]:
    """
    生成日期范围

    Args:
        start: 起始日期
        end: 结束日期
        inclusive: 是否包含结束日期

    Yields:
        日期对象
    """
    start_date = normalize_date(start)
    end_date = normalize_date(end)

    current = start_date
    while current <= end_date:
        yield current
        current = date.fromordinal(current.toordinal() + 1)

# 使用
for d in date_range("2024-01-01", "2024-01-05"):
    print(d)
# 2024-01-01
# 2024-01-02
# 2024-01-03
# 2024-01-04
# 2024-01-05
```

## 最佳实践

### 1. 统一日期处理

```python
# ✅ 推荐: 使用 DateInput 类型
def query_data(start: DateInput, end: DateInput):
    start_date = normalize_date(start)
    end_date = normalize_date(end)
    # ...

# ❌ 避免: 只接受字符串
def query_data(start: str, end: str):
    # 缺乏灵活性
    pass
```

### 2. 提前验证

```python
# ✅ 推荐: 在函数入口处标准化
def process_trade_date(trade_date: DateInput):
    normalized = normalize_date(trade_date)
    # 后续使用 normalized
    return normalized

# ❌ 避免: 在函数内部多次转换
def process_trade_date(trade_date: DateInput):
    if isinstance(trade_date, str):
        trade_date = datetime.strptime(trade_date, "%Y-%m-%d")
    # ... 重复转换逻辑
```

### 3. 类型提示

```python
# ✅ 推荐: 明确类型注解
def filter_by_date(
    df: pl.DataFrame,
    date_col: str,
    value: DateInput,
) -> pl.DataFrame:
    target_date = normalize_date(value)
    return df.filter(pl.col(date_col) == target_date)

# ❌ 避免: 缺少类型提示
def filter_by_date(df, date_col, value):
    pass
```

## 性能考虑

### 缓存标准化结果

```python
from functools import lru_cache
from ditto_datahub.utils import normalize_date

@lru_cache(maxsize=128)
def cached_normalize(value: DateInput) -> date:
    """带缓存的日期标准化"""
    return normalize_date(value)

# 重复输入时返回缓存结果
d1 = cached_normalize("2024-01-02")
d2 = cached_normalize("2024-01-02")  # 从缓存读取
assert d1 is d2
```

## 注意事项

### 1. 时区处理

```python
# normalize_date 会丢弃时区信息
from datetime import datetime

dt = datetime(2024, 1, 2, 10, 30, 0, tzinfo=timezone.utc)
d = normalize_date(dt)
# -> datetime.date(2024, 1, 2)  # 时区信息丢失

# 如需时区支持，请预先处理
from datetime import datetime, timezone

def normalize_date_with_tz(value: DateInput) -> date:
    if isinstance(value, datetime):
        # 转换为 UTC 后标准化
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return normalize_date(value)
```

### 2. 日期格式

```python
# 支持的日期字符串格式
normalize_date("2024-01-02")      # ✅ ISO 格式
normalize_date("20240102")        # ❌ 不支持
normalize_date("01/02/2024")      # ❌ 不支持

# 如需支持其他格式，请先解析
from datetime import datetime

def parse_and_normalize(date_str: str, fmt: str) -> date:
    dt = datetime.strptime(date_str, fmt)
    return normalize_date(dt)

d = parse_and_normalize("01/02/2024", "%m/%d/%Y")
# -> datetime.date(2024, 1, 2)
```

## 相关文档

- [Foundation Utils](../../../foundation/src/ditto_foundation/util/dates.py)
- [日期处理设计](../../../../../docs/design/04_data_model_design.md)
- [PIT 查询设计](../../../../../docs/design/07_pit_query_design.md)
