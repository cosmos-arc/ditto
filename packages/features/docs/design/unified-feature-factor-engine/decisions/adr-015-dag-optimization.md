> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-015: DAG 优化策略

**状态**: 已决策（2026-03-05）

---

## 背景

因子计算涉及 DAG（有向无环图）执行优化。需要明确：
1. 多因子执行顺序（串行 vs 并行）
2. 增量计算边界（数据变更后重算范围）
3. 中间结果内存管理

---

## 决策

### 1. 多因子执行：拓扑排序 + 串行

采用**拓扑排序 + 串行执行**，不使用 Python 层并行。

**理由分析**:

| 方案 | Python 并行收益 | 原因 |
|------|----------------|------|
| 单因子计算 | ❌ 无 | Polars 内部已并行 |
| 多因子串行（当前） | - | 每个因子内部并行 |
| 多因子并行（threading） | ❌ 负收益 | GIL 阻塞，额外开销 |
| 多因子并行（multiprocessing） | ⚠️ 有限 | 进程启动开销 + 内存复制 |

**Polars 并行机制**:
- Polars 用 Rust 编写，计算时释放 GIL
- 16 核可达 12x 加速（相对于 Pandas）
- 单次 Polars 操作内部已是并行的

**Python Free-Threading（2026）**:
- Python 3.14（2025-10）正式支持 free-threading
- 多线程 CPU 密集任务可达 10x 加速
- 但 Ditto 当前使用 Python 3.12+，暂不可用

**性能估算**:

```
场景：100 个因子，5000 标的，3 年数据

单因子计算：~0.5-2s（Polars 内部并行）
100 因子串行：~50-200s（主要耗时）
I/O 写入：~10-30s（Parquet 写入）

结论：串行不是主要瓶颈
- 因子计算本身已通过 Polars 并行优化
- 100 因子 3 分钟内可完成，满足日更需求
- 真正瓶颈在 I/O 而非计算并行度
```

**执行流程**:

```python
def execute_factors(specs: list[FactorSpec], data: pl.DataFrame) -> None:
    """按拓扑顺序串行执行因子计算"""
    # 1. 构建依赖图
    dag = build_dependency_graph(specs)

    # 2. 拓扑排序
    ordered = topological_sort(dag)

    # 3. 串行执行（每个因子内部 Polars 并行）
    for spec in ordered:
        expr = compile_expression(spec)
        result = data.lazy().with_columns([expr.alias("value")]).collect()
        write_factor(result, spec)
```

---

### 2. 增量计算边界：精确影响范围

当输入数据变更时，按**精确影响范围**重算，与 ADR-006 Invalidation 规则一致。

**规则**:

| 因子类型 | 影响范围 | 说明 |
|---------|---------|------|
| **TS 因子** | `(change_date - lookback, watermark]` | 向后扩展 lookback 天 |
| **CS 因子** | `change_date` 整日 | `requires_full_day=True`，整日全截面重算 |
| **混合因子** | TS 规则 + CS 规则 | 取两者并集 |

**示例**:

```python
# 因子: alpha_001 = ts_rank(cs_rank(close), 9)
# lookback = 9, requires_full_day = True
# 2026-01-15 的 market.close 修正

# 影响范围计算
change_date = date(2026, 1, 15)
lookback = 9
requires_full_day = True

if requires_full_day:
    # CS 因子：整日重算（所有标的）
    affected_dates = [change_date]
else:
    # TS 因子：向后扩展 lookback
    affected_dates = date_range(change_date, change_date + lookback)

# 计算边界
compute_start = min(affected_dates) - lookback  # 2026-01-06
compute_end = watermark  # 2026-03-05
```

**Invalidation 处理流程**:

```
源数据变更（market.close 2026-01-15 修正）
    │
    ├─ 查询依赖该列的所有因子
    │   SELECT entity_id FROM derived_dependency
    │   WHERE dep_column = 'market.close'
    │
    ├─ 对每个受影响因子：
    │   ├─ 计算 lookback 和 requires_full_day
    │   ├─ 确定受影响日期范围
    │   └─ 写入 derived_invalidation 表
    │
    └─ 下次增量执行时：
        ├─ 读取 pending invalidation
        ├─ 调整 compute_start/compute_end
        └─ 执行重算
```

---

### 3. 中间结果内存：Polars 自动管理

采用 **Polars Lazy 执行**，中间列自动管理。

**Lazy 执行优势**:

| 特性 | 说明 |
|------|------|
| **延迟计算** | `collect()` 时才真正执行 |
| **查询优化** | Polars 自动优化执行计划 |
| **内存高效** | 中间列用完即释放 |
| **谓词下推** | 过滤条件下推到数据源 |

**示例**:

```python
# 因子表达式
alpha_001 = "cs_rank(ts_delta(close, 5) / ts_mean(close, 20))"

# Lazy 执行（推荐）
result = (
    df.lazy()
    .with_columns([
        pl.col("close").diff(5).alias("delta_5"),        # 临时列
        pl.col("close").rolling_mean(20, closed="left").alias("mean_20"),  # 临时列
    ])
    .with_columns([
        (pl.col("delta_5") / pl.col("mean_20")).alias("ratio"),  # 临时列
    ])
    .with_columns([
        pl.col("ratio").rank().over("trade_date").alias("value"),  # 最终结果
    ])
    .select(["instrument_id", "trade_date", "value"])  # 只保留最终列
    .collect()  # 执行时才计算，中间列自动释放
)
```

**内存估算**:

```
场景：5000 标的 × 250 交易日 × 10 列（原始 + 临时）

Eager 模式：5000 × 250 × 10 × 8 bytes = ~100 MB
Lazy 模式：峰值 ~50 MB（中间列用完即释放）
```

---

## 决策汇总

| 决策点 | 决策 | 理由 |
|-------|------|------|
| **多因子执行** | 拓扑排序 + 串行 | Polars 内部已并行，Python 层串行开销可控 |
| **增量计算边界** | 精确影响范围 | TS 向后扩展 lookback，CS 整日重算 |
| **中间结果内存** | Polars 自动管理 | Lazy 执行引擎自动优化 |

---

## 业界对标

| 平台 | 执行模式 | 增量边界 | 内存管理 |
|------|---------|---------|---------|
| Qlib | 串行 | lookback 回退 | Eager（用户管理） |
| DolphinDB | 并行 | 精确范围 | 自动 GC |
| **Ditto** | **串行** | **精确范围** | **Lazy 自动** |
