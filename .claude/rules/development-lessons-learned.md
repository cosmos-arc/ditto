# 开发经验总结

> 记录在开发过程中遇到的问题、解决方案和最佳实践，供后续开发参考。

---

## 一、类型注解关键模式

### 1.1 Polars DataFrame 操作返回 Any

```python
# ❌ 错误：MyPy 会报错 no-any-return
def list_sids(self, dataset: str) -> list[int]:
    result = lf.select(pl.col("sid").unique()).collect()
    return result["sid"].to_list()  # 返回 Any

# ✅ 正确：显式类型声明
def list_sids(self, dataset: str) -> list[int]:
    result = lf.select(pl.col("sid").unique()).collect()
    sids: list[int] = result["sid"].to_list()
    return sids
```

**规则**: Polars 的 `to_list()` 返回 `Any`，必须显式类型注解。

### 1.2 日期处理使用 Python 原生类型

```python
# ❌ 错误：pl.date() 返回表达式，不是值
data = {"trade_date": [pl.date(2024, 1, 2), ...]}

# ✅ 正确：使用 datetime.date
from datetime import date
data = {"trade_date": [date(2024, 1, 2), ...]}
```

**规则**: 使用 Python `datetime.date` 而非 `pl.date()` 创建日期值。

### 1.3 日期字符串解析

```python
# ❌ 错误：pl.strptime() 不存在
start_dt = pl.strptime(start_date, "%Y-%m-%d")

# ✅ 正确：使用 datetime.strptime
from datetime import datetime
start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
# 然后在 Polars filter 中使用 pl.lit()
lf = lf.filter(pl.col("trade_date") >= pl.lit(start_dt))
```

---

## 二、模块文档字符串格式

### 2.1 单行文档字符串

```python
"""Single-line docstring."""
```

### 2.2 多行文档字符串

```python
"""Multi-line docstring.

Details here.
"""

from __future__ import annotations  # imports 在 docstring 之后
```

**规则**:
- 简单文档用单行，不需要 period 结尾（除非是完整句子）
- 复杂文档用多行，summary 行后空一行
- `from __future__ import annotations` 必须在 docstring 之后

### 2.3 Ruff D213 规则

```python
# ❌ 触发 D213 错误
"""Module docstring
with summary on first line.
"""

# ✅ 符合 D213
"""Module docstring with summary on first line.

Details here.
"""
```

---

## 三、SQLite 特定问题

### 3.1 BOOLEAN 类型处理

SQLite 存储 BOOLEAN 为 INTEGER (0/1)，读取时需要转换：

```python
def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert SQLite row to dict with proper type conversions."""
    result = dict(row)
    # 转换 INTEGER back to bool
    for key in ("dq_passed", "is_open", "is_active", ...):
        if isinstance(result[key], int):
            result[key] = bool(result[key])
    return result
```

**规则**: SQLite 返回的 BOOLEAN 字段是 `int`，需要手动转换为 `bool`。

---

## 四、代码质量检查清单

提交前必须执行：

```bash
# 方法1：一键检查（推荐）
pre-commit run --all-files

# 方法2：分步检查
pixi run ruff check .           # Lint
pixi run ruff format --check .  # Format
pixi run mypy packages/         # Type check
pixi run pytest                 # Tests
```

**规则**: 每次提交前必须通过所有检查，不得使用 `--no-verify` 绕过。

---

## 五、测试数据创建模式

### 5.1 日期测试数据

```python
from datetime import date

@pytest.fixture
def sample_df(self) -> pl.DataFrame:
    """Create sample data."""
    data: dict[str, list[Any]] = {
        "sid": [100000001, 100000002],
        "trade_date": [
            date(2024, 1, 2),
            date(2024, 1, 3),
        ],
        "close": [10.5, 20.5],
    }
    return pl.DataFrame(data)
```

### 5.2 跨年测试数据

```python
# 需要将数据年份与分区年份对应
df_2023 = sample_df.with_columns(
    pl.col("trade_date").map_elements(
        lambda d: d.replace(year=2023), return_dtype=pl.Date
    )
)
store.write("dataset", df_2023, 2023)
```

---

## 六、命名约定记录

### 6.1 数据集命名

| 原设计 | 实际实现 | 原因 |
|--------|----------|------|
| `market_daily` | `stock_daily` | 更明确表示股票日线 |

**记录位置**: `docs/design/02_data_design.md`

---

## 七、TDD 开发流程

```
RED → GREEN → REFACTOR
```

1. **RED**: 编写失败的测试
   - 测试可能因为类型检查失败（正常）
   - 聚焦于API设计

2. **GREEN**: 实现最小代码使测试通过
   - 不过度设计
   - 关注功能正确性

3. **REFACTOR**: 重构优化
   - 代码格式化
   - 类型注解完善
   - 性能优化

---

## 八、文档同步清单

实现完成后需要更新的文档：

| 文档 | 用途 |
|------|------|
| `docs/sprints/sprint-*.md` | 更新任务完成状态 |
| `docs/plans/YYYY-MM-DD-sprint*-task*.md` | 更新实施状态和验收标准 |
| `docs/design/02_data_design.md` | 同步命名变更、接口变更 |

---

## 九、常用导入模板

```python
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest
```

---

## 十、年分区存储边界处理

```python
# 日期跨年查询时的年份范围计算
start_year = int(start_date[:4]) if start_date else 1990
end_year = int(end_date[:4]) if end_date else 2099
```

**规则**: 年分区计算需要考虑日期过滤的边界情况。
