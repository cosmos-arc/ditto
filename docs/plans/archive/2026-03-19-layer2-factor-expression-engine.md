# Layer 2: 因子表达式引擎 — 实施计划

> **状态**: ✅ 全部 6 Phase 完成（2026-03-19）
>
> **验证**: ruff lint ✅ | basedpyright 0 errors ✅ | 287 engine tests ✅

## Context

因子表达式引擎已有完整的编译管线（Lexer → Parser → AST → Analyzer → Codegen → Polars），支持 29 个算子。但存在 5 个 P0 正确性 bug、6 个 P1 功能缺口、7 个 P2 改进项，以及 ADR-005 规划的 30 个因子/特征定义尚未编写。本次实施覆盖全部 18 个缺口项 + 30 个因子定义。

**Polars API 验证（v1.38.1）**：`pl.rolling_corr`、`pl.rolling_cov`、`pl.Expr.ewm_mean` 均可用。

---

## Phase 1: P0 正确性修复（ENG-E-1 ~ E-5）

> 修复导致静默数据损坏或错误结果的 bug。3 个子任务可并行。

### 1A: 除零修复（ENG-E-3, E-4, E-5）

**文件**: `packages/core/src/ditto_core/engine/expression/codegen.py`

| ID | 行号 | 当前 | 修复 |
|----|------|------|------|
| E-3 | 365 | `(x - mean) / std` | `pl.when(std == 0).then(0.0).otherwise((x - mean) / std)` |
| E-4 | 361 | `x / denominator` | `pl.when(denominator == 0).then(0.0).otherwise(x / denominator)` |
| E-5 | 320 | `(x / x.shift(n)) - 1` | 先赋值 `shifted = x.shift(n).over(keys)`，再用 `pl.when(shifted == 0).then(0.0).otherwise((x / shifted) - 1)` |

### 1B: ts_corr/ts_cov codegen（ENG-E-1）

**文件**: `packages/core/src/ditto_core/engine/expression/codegen.py`

在 `_compile_time_series_special()` 末尾添加处理（return None 之前）：

```python
if name in {"ts_corr", "ts_cov"}:
    window = _read_int_literal(raw_arguments, 2, source=source)
    shifted_x = arguments[0].shift(1)
    shifted_y = arguments[1].shift(1)
    if name == "ts_corr":
        return pl.rolling_corr(shifted_x, shifted_y, window_size=window, min_samples=window).over(entity_keys)
    return pl.rolling_cov(shifted_x, shifted_y, window_size=window, min_samples=window).over(entity_keys)
```

关键设计：`pl.rolling_corr`/`pl.rolling_cov` 是命名空间级函数（非 Expr 方法），接受两个 Expr 参数。两者 shift(1) 防 PIT 泄漏。

### 1C: Lookback off-by-1（ENG-E-2）

**文件**: `packages/core/src/ditto_core/engine/expression/analyzer.py`

分类两类算子，重构 `_extract_lookback()`：

- **Rolling 类**（使用 `_rolling()` 内部 shift(1)）→ lookback = window + 1：`ts_mean, ts_sum, ts_std, ts_var, ts_max, ts_min, ts_count, ts_median, ts_rank, ts_argmax, ts_argmin, ts_corr, ts_cov`
- **Shift-only 类**（自行 shift 但无 rolling）→ lookback = period：`ts_delay, ts_delta, ts_diff, ts_pct_change`

实现：用两个 frozenset 分类，_ROLLING_WINDOW_FUNCTIONS 返回 `window + 1`，_SHIFT_ONLY_FUNCTIONS 返回 `window`。

**注意**：新增算子（ts_ema, ts_decay_linear）也属于 Rolling 类，lookback = window + 1。

**影响**：现有测试 `test_incremental_plan_uses_earliest_invalidation_and_lookback` 中 `ts_mean(close, 5)` 的 lookback 从 5 变为 6，compute_start 会后移一天，需更新测试预期值。

### 1A/1B/1C 共用测试

**文件**: `packages/core/tests/unit/engine/test_expression_engine_unit.py`

新增测试：
- `test_codegen_cs_zscore_zero_std` — 全相同值截面，无 Inf/NaN
- `test_codegen_cs_scale_zero_values` — 全零值，无 Inf/NaN
- `test_codegen_ts_pct_change_zero_denominator` — shift(n) 为 0 时返回 0
- `test_codegen_ts_corr` — 多 entity DataFrame，验证相关性计算
- `test_codegen_ts_cov` — 多 entity DataFrame，验证协方差计算
- `test_lookback_rolling_adds_one` — `ts_mean(x, 20)` → lookback=21
- `test_lookback_shift_only` — `ts_delay(x, 5)` → lookback=5
- `test_lookback_two_expr_rolling` — `ts_corr(x, y, 10)` → lookback=11

---

## Phase 2: P1 新算子（ENG-E-6, E-7, E-9, E-10）

> 4 个子任务可并行。每个算子需同步更新 3 个文件。

### ENG-E-6: ts_ema

**实现**：
```python
# codegen.py — _compile_time_series_special()
if name == "ts_ema":
    window = _read_int_literal(raw_arguments, 1, source=source)
    return arguments[0].shift(1).ewm_mean(span=window, min_samples=1).over(entity_keys)
```

Polars `ewm_mean(span=n)` 使用标准 `alpha = 2/(n+1)` 公式。`min_samples=1` 确保 EMA 从第一个有效行开始输出。shift(1) 防 PIT。

**同步更新**：
- `registry.py`: `"ts_ema": _operator("ts_ema", min_args=2, max_args=2, int_literal_positions=(1,))`
- `analyzer.py`: 加入 `_WINDOW_FUNCTIONS` 和 `_ROLLING_WINDOW_FUNCTIONS`

### ENG-E-7: ts_decay_linear

**实现**：使用 `rolling_map` + numpy（Polars 无内置线性衰减加权）：

```python
if name == "ts_decay_linear":
    window = _read_int_literal(raw_arguments, 1, source=source)
    shifted = arguments[0].shift(1)

    def _wma(s: pl.Series) -> float:
        arr = s.to_numpy()
        n = len(arr)
        weights = np.arange(1, n + 1, dtype=np.float64)
        mask = ~np.isnan(arr)
        if not mask.any():
            return float("nan")
        return float(np.dot(weights[mask], arr[mask]) / weights[mask].sum())

    return shifted.rolling_map(_wma, window_size=window, min_samples=window).over(entity_keys)
```

**同步更新**：registry + analyzer 同 ENG-E-6 模式。

### ENG-E-9: coalesce

**实现**：
```python
# codegen.py — _compile_scalar()
if name == "coalesce":
    return pl.coalesce(*arguments)
```

**注册**：`"coalesce": _operator("coalesce", min_args=2, max_args=10)`（变长参数）

### ENG-E-10: group_rank / group_zscore

**设计**：不放入 `_compile_cross_section()`（它用 time_keys 做 over），而是在 `_compile_call()` 中新增 `_compile_grouped_cross_section()` 调度。

```python
def _compile_grouped_cross_section(
    *, name: str, arguments: tuple[pl.Expr, ...],
) -> pl.Expr | None:
    if name == "group_rank":
        return (
            arguments[0].rank(method="ordinal").cast(pl.Float64)
            / pl.len().over(arguments[1]).cast(pl.Float64)
        )
    if name == "group_zscore":
        mean = arguments[0].mean().over(arguments[1])
        std = arguments[0].std().over(arguments[1])
        return pl.when(std == 0).then(0.0).otherwise((arguments[0] - mean) / std)
    return None
```

**注意**：`group_zscore` 内含除零保护（借鉴 E-3 教训）。

**注册**：两个算子均 `min_args=2, max_args=2`，第 2 参数为分组列。

**调度修改**：`_compile_call()` 中在 cross_section 和 scalar 之间插入 grouped cross section 检查。

### Phase 2 测试

每个新算子一个测试：
- `test_codegen_ts_ema` — 已知 EMA 值验证
- `test_codegen_ts_decay_linear` — 手算 WMA 验证
- `test_codegen_coalesce` — 含 null 数据验证
- `test_codegen_group_rank` — 行业分组 rank 验证
- `test_codegen_group_zscore` — 行业分组 zscore 验证（含 std=0 场景）

---

## Phase 3: P1 因子定义 + 循环依赖检测（ENG-E-8, ENG-E-11）

### ENG-E-11: 循环依赖检测

**文件**: `packages/core/src/ditto_core/engine/expression/compiler.py`

新增纯函数 `detect_dependency_cycles(graph: dict[str, tuple[str, ...]]) -> None`：

- 使用 Kahn 算法（拓扑排序），Core 层纯计算
- 若 `visited != len(graph)` 则抛 ValueError
- 用于因子 DAG 验证

### ENG-E-8: 30 个因子/特征定义

**新目录**: `packages/core/src/ditto_core/engine/factors/`

| 文件 | 内容 | 数量 |
|------|------|------|
| `__init__.py` | 导出 `ALL_FACTOR_SPECS`, `TECHNICAL_*`, `FUNDAMENTAL_*`, `ALPHA_*` | - |
| `primitives.py` | `returns_1`, `tr`（True Range）等被多个因子依赖的基础特征 | 2 |
| `technical.py` | RSI, MA, EMA, MACD, Bollinger, ATR, Volatility, VolumeMA, Returns | ~25 个 spec |
| `fundamental.py` | PE, PB, PS, debt_ratio, ROE, net_margin, asset_turnover, earnings_growth | 8 个 spec |
| `alpha.py` | momentum_1m/12m, reversal_1w, value_pe/pb, quality_roe/margin, volatility, liquidity, alpha_001 | 10 个 spec |

**表达式语法适配**（ADR-005 表达式需转换为 DSL 语法）：
- `max(a, b)` → `max2(a, b)`
- 三参数 `max(a, b, c)` → 嵌套 `max2(a, max2(b, c))`
- `min(a, b)` → `min2(a, b)`
- `delay(x, n)` → `ts_delay(x, n)`

**参数化模板**：`ma_{n}`, `ema_{n}`, `returns_{n}`, `volatility_{n}` 等对 `n ∈ {5, 10, 14, 20, 60}` 生成多个 spec。

**测试**：
- `test_factor_definitions.py`：所有 spec 能通过 `ExpressionCompiler.compile()` 无异常
- `test_dependency_dag_valid`：`detect_dependency_cycles(ALL_FACTOR_SPECS)` 通过
- `test_topological_order`：依赖在依赖者之前定义

---

## Phase 4: P2 标量算子 + 参数校验（ENG-E-13, E-15, E-17）

> 3 个子任务可并行。

### ENG-E-17: 缺失标量算子

**codegen.py — `_SCALAR_UNARY_OPERATORS` 新增**：
```python
"log10": lambda e: e.log10(),
"log2": lambda e: e.log(base=2),
"floor": lambda e: e.floor(),
"ceil": lambda e: e.ceil(),
```

**codegen.py — `_compile_scalar()` 新增**：
```python
if name == "round":
    return arguments[0].round(decimals=arguments[1])
```

**registry.py 新增**：
```python
"log10": ..., "log2": ..., "floor": ..., "ceil": ..., "round": (min=2, max=2, int_positions=(1,))
```

### ENG-E-15: 窗口参数正值校验

**codegen.py — `_read_int_literal()` 末尾添加**：
```python
if value <= 0:
    raise make_compile_error(
        source=source,
        message=f"window size must be positive, got {value}",
        error_code="E033_INVALID_PARAMETER",
        span=argument.span,
    )
```

### ENG-E-13: cs_winsorize 可配置 sigma

**重构 `_compile_cross_section()`**：需传入 `raw_arguments` 以读取 sigma 参数。

```python
if name == "cs_winsorize":
    mean = arguments[0].mean().over(time_keys)
    std = arguments[0].std().over(time_keys)
    n_sigma = 3  # 默认
    if len(raw_arguments) >= 2:
        n_sigma = _read_int_literal(raw_arguments, 1, source=source)
    return arguments[0].clip(mean - n_sigma * std, mean + n_sigma * std)
```

**注意**：需修改 `_compile_cross_section()` 签名，新增 `raw_arguments` 和 `source` 参数。调用处 `_compile_call()` 同步更新。

**registry 更新**：`"cs_winsorize": _operator(..., max_args=2, int_literal_positions=(1,))`

---

## Phase 5: P2 缓存优化（ENG-E-12, E-16）

### ENG-E-12: L1 缓存 LRU 化

**文件**: `packages/core/src/ditto_core/engine/compile_cache.py`

```python
import cachebox

class SQLiteCompileCache:
    def __init__(self, sqlite_client, *, max_cache_size: int = 256) -> None:
        self._sqlite_client = sqlite_client
        self._memory_cache = cachebox.LRUCache(maxsize=max_cache_size)
```

`cachebox` 是允许的依赖，`LRUCache` 接口与 dict 兼容（`__contains__`, `__getitem__`, `__setitem__`），零迁移成本。

### ENG-E-16: L2 命中时避免双重解析

**文件**: `packages/core/src/ditto_core/engine/expression/compiler.py`

重构 `compute_compile_cache_key()` 返回 AST：
```python
def compute_compile_cache_key(spec) -> tuple[str, Analysis, CompileIdentity, ExpressionNode]:
    # ... 已有解析逻辑 ...
    return cache_key, analysis, compile_identity, ast
```

`ExpressionCompiler.compile()` 接受可选的预解析 AST：
```python
def compile(self, spec, *, ast: ExpressionNode | None = None) -> CompiledDerivedExpression:
    cache_key, analysis, compile_identity = compute_compile_cache_key(spec)
    if ast is None:
        tokens = tokenize(spec.expression)
        ast = ExpressionParser(tokens, spec.expression).parse()
    # ...
```

`compile_cache.py` L2 命中路径：
```python
cache_key, analysis, compile_identity, ast = compute_compile_cache_key(spec)
compiled = self._compiler.compile(spec, ast=ast)
```

**影响**：`_precompute_cache_key()` 也需更新以接收 4 元组返回值。

---

## Phase 6: P2 质量保障（ENG-E-14, E-18）

### ENG-E-14: 最小化表达式类型检查

在 `_validate_operator_call()` 中新增：ts_* 算子的表达式参数不接受 StringNode。

```python
if name.startswith("ts_"):
    for i, arg in enumerate(arguments):
        if isinstance(arg, StringNode):
            raise make_compile_error(..., message=f"'{name}' argument {i} must be numeric")
```

仅做最小化校验（AST 节点级），不做完整类型推断。

### ENG-E-18: 算子 golden data 测试

**新文件**: `packages/core/tests/unit/engine/test_operator_golden_data.py`

用参数化 pytest + 手算预期值覆盖所有算子：
- 所有 ts_* 算子（含新增 ts_ema, ts_decay_linear, ts_corr, ts_cov）
- 所有 cs_* 算子（含 group_rank, group_zscore）
- 所有标量算子
- 边界条件：全零、全相同、含 null、单值

---

## 依赖关系与并行策略

```
Phase 1 (P0)  ← 立即开始，3 子任务可并行
    ↓
Phase 2 (P1 算子)  ← Phase 1 完成后，4 子任务可并行
    ↓
Phase 3 (P1 因子定义)  ← Phase 2 完成后（因子依赖新算子）
    ↓
Phase 4 (P2 标量+校验)  ← 独立于 Phase 1-3，可并行
Phase 5 (P2 缓存)       ← 独立于 Phase 1-3，可并行
    ↓
Phase 6 (P2 质量保障)  ← 所有前置完成后
```

## 关键修改文件清单

| 文件 | 涉及项 |
|------|--------|
| `packages/core/src/ditto_core/engine/expression/codegen.py` | E-1~E-5, E-6, E-7, E-9, E-10, E-13, E-14, E-15, E-17 |
| `packages/core/src/ditto_core/engine/expression/analyzer.py` | E-2, E-6, E-7 |
| `packages/core/src/ditto_core/engine/expression/registry.py` | E-6, E-7, E-9, E-10, E-13, E-17 |
| `packages/core/src/ditto_core/engine/expression/compiler.py` | E-11, E-16 |
| `packages/core/src/ditto_core/engine/compile_cache.py` | E-12, E-16 |
| `packages/core/tests/unit/engine/test_expression_engine_unit.py` | 所有 P0/P1 测试 |
| **新增** `packages/core/src/ditto_core/engine/factors/` 目录 | E-8 |
| **新增** `packages/core/tests/unit/engine/test_operator_golden_data.py` | E-18 |
| **新增** `packages/core/tests/unit/engine/test_factor_definitions.py` | E-8, E-11 |

## 验证

每个 Phase 完成后运行：
```bash
pixi run -e dev check   # lint + fmt + type + test --fast
```

全部完成后运行：
```bash
pixi run -e dev ci      # 完整 CI
```
