---
alwaysApply: true
---

# 代码风格

## 函数规范

- 长度 ≤ 50 行
- 嵌套 ≤ 3 层
- 参数 ≤ 5 个（超过用 dataclass）
- 单一职责

## 命名

```python
# 类：PascalCase
class FactorEngine: ...

# 函数/变量：snake_case
def calculate_momentum(): ...

# 常量：UPPER_SNAKE
MAX_DRAWDOWN = 0.20

# 私有：前缀下划线
def _internal_method(): ...
```

## 类型注解

```python
# ✅ 公开函数必须注解
def process(data: pl.DataFrame, config: Config) -> Result: ...

# ✅ 使用现代语法
def get_items() -> list[str]: ...  # 不是 List[str]
def maybe_value() -> int | None: ...  # 不是 Optional[int]
```

## Docstring

```python
def calculate_factor(
    data: pl.DataFrame,
    window: int,
) -> pl.Series:
    """计算因子值。

    Args:
        data: 包含 close 列的价格数据
        window: 回看窗口大小

    Returns:
        因子值序列

    Raises:
        ValueError: 当 window < 1 时
    """
```

## 导入顺序

```python
# 1. 标准库
from datetime import date
from typing import Protocol

# 2. 第三方库
import polars as pl
from fastapi import APIRouter

# 3. 本地模块
from ditto_core.engine import BaseEngine
```
