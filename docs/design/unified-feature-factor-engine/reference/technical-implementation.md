# 技术实现参考

## 1. 表达式引擎

### Pratt Parser

Pratt 解析器是处理运算符优先级的经典算法，适合数学表达式解析。

**核心概念**：
- `nud` (null denotation): 处理前缀操作（如 `-x`, `!x`）
- `led` (left denotation): 处理中缀操作（如 `a + b`, `a * b`）
- 优先级绑定：每个运算符绑定绑定优先级

**实现参考**：
```python
def parse_expression(precedence=0):
    token = advance()
    left = nud(token)

    while precedence < current_precedence():
        token = advance()
        left = led(token, left)

    return left
```

**业界使用**：
- Clang C++ 编译器
- Rust 编译器
- SQLite SQL 解析器

### AST 节点设计

```python
class Expr(Node):
    pass

class Binary(Expr):
    op: str          # "+", "-", "*", "/"
    left: Expr
    right: Expr

class Unary(Expr):
    op: str          # "-", "!"
    operand: Expr

class Call(Expr):
    name: str        # "ts_mean", "cs_rank"
    args: list[Expr]
    kwargs: dict[str, Expr]

class Column(Expr):
    name: str        # "close", "volume"
    namespace: str   # "$" (market), "$$" (fundamental)
```

## 2. Polars Expr 代码生成

### 映射规则

| AST 节点 | Polars Expr |
|---------|-------------|
| `Binary(+, a, b)` | `pl.col("a") + pl.col("b")` |
| `Call(ts_mean, x, 5)` | `pl.col("x").rolling_mean(5, closed="left")` |
| `Call(cs_rank, x)` | `pl.col("x").rank().over("trade_date")` |
| `Call(ts_ref, x, 1)` | `pl.col("x").shift(1)` |

> **注意**: 所有滚动窗口操作必须使用 `closed="left"` 以避免数据泄漏（见 PIT 安全窗口约束）。

### 分组处理

```python
# TS 算子：按 instrument_id 分组
ts_expr = pl.col("close").rolling_mean(5, closed="left").over("instrument_id")

# CS 算子：按 trade_date 分组
cs_expr = pl.col("close").rank().over("trade_date")
```

## 3. 增量计算

### Watermark 机制

**概念**：记录每个数据集的最新成功计算时间点

```python
@dataclass
class Watermark:
    entity_id: str
    version: int
    last_computed: date
    last_updated: datetime
```

**更新策略**：
1. 成功物化后更新 watermark
2. 失败则保持不变
3. 支持回退（用于 backfill）

### Invalidation 扩展

**TS 算子扩展规则**：
```
invalidation_date = T
lookback = 5
affected_dates = [T-5, T-4, T-3, T-2, T-1, T]
```

**CS 算子扩展规则**：
```
invalidation_point = (instrument_id, T)
requires_full_day = True
affected_scope = ALL instruments on date T
```

## 4. 状态管理

### sortedcontainers 使用

**场景**：ts_rank 精确计算需要维护有序窗口

```python
from sortedcontainers import SortedList

class TSRankState:
    def __init__(self, window_size: int):
        self.window = SortedList()
        self.values = deque(maxlen=window_size)

    def update(self, value: float) -> float:
        if len(self.values) == self.values.maxlen:
            self.window.remove(self.values[0])

        self.window.add(value)
        self.values.append(value)

        # O(log n) 排名查询
        rank = self.window.bisect_left(value)
        return rank / len(self.window)
```

**性能对比**：
| 操作 | bisect (list) | SortedList |
|------|---------------|------------|
| 插入 | O(n) | O(log n) |
| 查询 | O(log n) | O(log n) |
| 删除 | O(n) | O(log n) |

## 5. Catalog 存储

### SQLite 事务模式

```python
def atomic_write(spec, state, run):
    with sqlite3.connect(CATALOG_PATH) as conn:
        conn.execute("BEGIN IMMEDIATE")

        try:
            conn.execute(INSERT_SPEC, spec)
            conn.execute(INSERT_STATE, state)
            conn.execute(INSERT_RUN, run)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
```

### 锁粒度设计

```
Lock Key Pattern: derived/{entity_type}/{entity_id}/v{version}

Examples:
- derived/factor/alpha_001/v1
- derived/feature/rsi_14/v2
- derived/factor/alpha_001/v1/2024-03
```

## 6. 并发控制

### 文件锁模式

```python
from filelock import FileLock

def materialize_with_lock(entity_id: str, version: int):
    lock_key = f"derived/factor/{entity_id}/v{version}"
    lock_path = f"/tmp/ditto/{lock_key}.lock"

    with FileLock(lock_path, timeout=3600):
        # 计算并写入
        result = compute()
        write_partition(result)
        update_catalog(result)
```

### 原子提交顺序

1. 获取锁
2. 写临时目录 `.tmp/`
3. 校验数据
4. 原子 rename
5. 更新 Catalog
6. 释放锁

## 7. PIT 实现

### 版本化表设计

```sql
CREATE TABLE factor_values (
    instrument_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    factor_id TEXT NOT NULL,

    -- PIT 列
    effective_from TEXT NOT NULL,
    effective_to TEXT,

    -- 值
    value REAL,

    PRIMARY KEY (instrument_id, trade_date, factor_id, effective_from)
);
```

### 查询语义

```python
def query_pit(factor_id: str, as_of: date):
    return f"""
    SELECT * FROM factor_values
    WHERE factor_id = '{factor_id}'
      AND effective_from <= '{as_of}'
      AND (effective_to IS NULL OR effective_to > '{as_of}')
    """
```

## 8. 测试策略

### 表达式引擎测试

```python
def test_expression_roundtrip():
    """表达式 → AST → 重建表达式"""
    expr = "ts_mean(close, 5) + cs_rank(volume)"
    ast = parse(expr)
    reconstructed = to_string(ast)
    assert expr == reconstructed

def test_codegen_correctness():
    """代码生成与 Polars 原生结果一致"""
    expr = "ts_mean(close, 5)"
    result = evaluate(expr, test_data)
    expected = test_data.select(
        pl.col("close").rolling_mean(5, closed="left").over("instrument_id")
    )
    assert_frame_equal(result, expected)
```

### 增量一致性测试

```python
def test_incremental_equals_full():
    """增量结果与全量结果一致"""
    # 全量计算
    full_result = compute_full(start=date(2024, 1, 1), end=date(2024, 3, 1))

    # 增量计算
    compute_full(start=date(2024, 1, 1), end=date(2024, 2, 15))
    inc_result = compute_incremental(end=date(2024, 3, 1))

    # 验证最后一个月数据一致
    assert_frame_equal(
        full_result.filter(pl.col("trade_date") >= date(2024, 2, 16)),
        inc_result
    )
```

## 9. 资源与链接

### 开源实现参考

| 项目 | 链接 | 借鉴点 |
|------|------|--------|
| Qlib | https://github.com/microsoft/qlib | 表达式引擎、PIT |
| DolphinDB | https://dolphindb.com/ | TS 函数实现 |
| DuckDB | https://duckdb.org/ | 查询优化 |
| Feast | https://feast.dev/ | Feature Store 架构 |

### 技术文档

- Pratt Parser: https://journal.stuffwithstuff.com/2011/03/19/pratt-parsers-expression-parsing-made-easy/
- Polars Expr: https://pola-rs.github.io/polars/py-polars/html/reference/expressions/
- SQLite Concurrency: https://www.sqlite.org/lockingv3.html
