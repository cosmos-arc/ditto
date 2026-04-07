# ADR-027: 表达式 Pushdown 策略

**状态**: 已决策（2026-03-10）

---

## 背景

因子表达式引擎需要决定在何处执行计算：
1. **QuestDB 下推**：将计算下推到 QuestDB，利用其时序优化
2. **Polars 本地计算**：将数据拉取到本地用 Polars 计算

QuestDB 对时序聚合（SAMPLE BY）和 ASOF JOIN 有原生优化，但并非所有 Polars 算子都能下推。需要一套清晰的策略来决定何时下推、何时回退。

---

## 核心原则

> **统一语义，不统一物理实现。**
>
> 表达式语义只定义一次在 Polars/FeatureSpec，QuestDB 只是可下推后端，不是语义源头。

---

## 三层判定架构

下推决策分三层，逐层判断：

```
┌─────────────────────────────────────────────────────────────┐
│                    第一层：能力层（代码）                      │
│                                                              │
│  定义：哪些算子**技术上可以**下推到 QuestDB                    │
│  管理：代码中的 OperatorRegistry.can_pushdown                │
│  示例：ts_mean → ✅ 可以，cs_rank → ❌ 不可以                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    第二层：模式层（表达式映射）                  │
│                                                              │
│  定义：表达式如何映射到 QuestDB SQL                           │
│  管理：PushdownPatternRegistry                               │
│  示例：ts_mean(x, 20) → AVG(x) OVER (ORDER BY ts ROWS 19)   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    第三层：开关层（运行时控制）                  │
│                                                              │
│  定义：运行时是否**实际启用**下推                              │
│  管理：SQLite 配置表 pushdown_config                          │
│  示例：生产环境启用，测试环境禁用                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 第一层：能力层

### 下推能力矩阵

| 算子 | 下推支持 | QuestDB 语法 | 说明 |
|------|---------|-------------|------|
| `ts_mean(x, w)` | ✅ | `AVG(x) OVER (ORDER BY ts ROWS w-1)` | 窗口平均 |
| `ts_sum(x, w)` | ✅ | `SUM(x) OVER (ORDER BY ts ROWS w-1)` | 窗口求和 |
| `ts_min(x, w)` | ✅ | `MIN(x) OVER (ORDER BY ts ROWS w-1)` | 窗口最小 |
| `ts_max(x, w)` | ✅ | `MAX(x) OVER (ORDER BY ts ROWS w-1)` | 窗口最大 |
| `ts_count(x, w)` | ✅ | `COUNT(x) OVER (ORDER BY ts ROWS w-1)` | 窗口计数 |
| `ts_std(x, w)` | ✅ | `STDDEV(x) OVER (ORDER BY ts ROWS w-1)` | 窗口标准差 |
| `ts_rank(x, w)` | ✅ | `RANK() OVER (...)` | 窗口排名 |
| `ts_delta(x, n)` | ✅ | `x - LAG(x, n) OVER (ORDER BY ts)` | 差分 |
| `ts_pct_change(x, n)` | ✅ | `(x - LAG(x, n)) / LAG(x, n)` | 涨跌幅 |
| `ref(x, n)` | ✅ | `LAG(x, n) OVER (ORDER BY ts)` | 引用前值 |
| `cs_rank(x)` | ❌ | - | 需全截面，回退 Polars |
| `cs_zscore(x)` | ❌ | - | 需全截面，回退 Polars |
| `neutralize(x, g)` | ❌ | - | 复杂截面计算，回退 Polars |
| `winsorize(x, p)` | ❌ | - | 需分位数，回退 Polars |

### 首版下推白名单

```
基础数据：
- 1m/5m/15m/60m OHLCV bars
- session VWAP
- cumulative volume / amount

时序聚合（短窗口，w ≤ 120）：
- rolling sum/mean/min/max/count
- simple return / rolling return
- short rolling vol

跨资产对齐：
- ASOF JOIN 指数/ETF/成分对齐

盘口因子：
- 盘口不平衡、价差、前五档量差

市场广度：
- breadth: up/down counts, adv/dec ratio, turnover sums
```

### 代码定义

```python
# packages/analytics/src/ditto_analytics/expression/pushdown.py

from enum import Enum
from typing import Callable

class PushdownCapability(Enum):
    FULL = "full"          # 完全可下推
    PARTIAL = "partial"    # 部分可下推（有条件）
    NONE = "none"          # 不可下推

# 能力注册表
PUSHDOWN_CAPABILITIES: dict[str, PushdownCapability] = {
    "ts_mean": PushdownCapability.FULL,
    "ts_sum": PushdownCapability.FULL,
    "ts_min": PushdownCapability.FULL,
    "ts_max": PushdownCapability.FULL,
    "ts_std": PushdownCapability.FULL,
    "ts_delta": PushdownCapability.FULL,
    "ts_pct_change": PushdownCapability.FULL,
    "ref": PushdownCapability.FULL,
    # 截面算子不可下推
    "cs_rank": PushdownCapability.NONE,
    "cs_zscore": PushdownCapability.NONE,
    "neutralize": PushdownCapability.NONE,
    "winsorize": PushdownCapability.NONE,
}

def can_pushdown(op_name: str) -> bool:
    """检查算子是否可以下推"""
    cap = PUSHDOWN_CAPABILITIES.get(op_name, PushdownCapability.NONE)
    return cap != PushdownCapability.NONE
```

---

## 第二层：模式层

### 表达式到 SQL 映射

```python
# packages/analytics/src/ditto_analytics/expression/pushdown_patterns.py

from dataclasses import dataclass
from typing import Any

@dataclass
class PushdownPattern:
    """下推模式定义"""
    op_name: str
    sql_template: str
    param_validator: Callable[[dict], bool]

# 模式注册表
PUSHDOWN_PATTERNS: dict[str, PushdownPattern] = {
    "ts_mean": PushdownPattern(
        op_name="ts_mean",
        sql_template="AVG({col}) OVER (PARTITION BY instrument_id ORDER BY trade_date ROWS {window}-1 PRECEDING)",
        param_validator=lambda p: isinstance(p.get("window"), int) and p["window"] <= 120,
    ),
    "ts_sum": PushdownPattern(
        op_name="ts_sum",
        sql_template="SUM({col}) OVER (PARTITION BY instrument_id ORDER BY trade_date ROWS {window}-1 PRECEDING)",
        param_validator=lambda p: isinstance(p.get("window"), int) and p["window"] <= 120,
    ),
    "ts_delta": PushdownPattern(
        op_name="ts_delta",
        sql_template="{col} - LAG({col}, {n}) OVER (PARTITION BY instrument_id ORDER BY trade_date)",
        param_validator=lambda p: isinstance(p.get("n"), int) and p["n"] > 0,
    ),
    "ref": PushdownPattern(
        op_name="ref",
        sql_template="LAG({col}, {n}) OVER (PARTITION BY instrument_id ORDER BY trade_date)",
        param_validator=lambda p: isinstance(p.get("n"), int) and p["n"] > 0,
    ),
}

def build_pushdown_sql(op_name: str, params: dict) -> str | None:
    """构建下推 SQL，失败返回 None"""
    pattern = PUSHDOWN_PATTERNS.get(op_name)
    if not pattern:
        return None
    if not pattern.param_validator(params):
        return None
    return pattern.sql_template.format(**params)
```

---

## 第三层：开关层

### SQLite 配置表

```sql
-- runtime/derived.sqlite
CREATE TABLE IF NOT EXISTS pushdown_config (
    op_name TEXT PRIMARY KEY,        -- 算子名
    enabled INTEGER DEFAULT 1,       -- 是否启用（0/1）
    max_window INTEGER DEFAULT 120,  -- 最大窗口限制
    timeout_ms INTEGER DEFAULT 5000, -- 超时阈值
    notes TEXT                       -- 备注说明
);

-- 默认配置
INSERT INTO pushdown_config (op_name, enabled, max_window, notes) VALUES
    ('ts_mean', 1, 120, '时序平均，短窗口'),
    ('ts_sum', 1, 120, '时序求和，短窗口'),
    ('ts_std', 1, 120, '时序标准差'),
    ('ts_delta', 1, 60, '时序差分'),
    ('ref', 1, 60, '引用前值'),
    ('cs_rank', 0, 0, '截面排名，不支持');
```

### 运行时检查

```python
# packages/analytics/src/ditto_analytics/expression/pushdown.py

import sqlite3

class PushdownConfig:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)

    def is_enabled(self, op_name: str) -> bool:
        """检查算子是否在运行时启用"""
        cursor = self.conn.execute(
            "SELECT enabled FROM pushdown_config WHERE op_name = ?",
            (op_name,)
        )
        row = cursor.fetchone()
        if row is None:
            return False  # 未配置默认不启用
        return bool(row[0])

    def get_max_window(self, op_name: str) -> int:
        """获取算子的最大窗口限制"""
        cursor = self.conn.execute(
            "SELECT max_window FROM pushdown_config WHERE op_name = ?",
            (op_name,)
        )
        row = cursor.fetchone()
        return row[0] if row else 0
```

---

## 执行决策流程

```python
def decide_execution_path(expr: Expression, config: PushdownConfig) -> ExecutionPath:
    """决定执行路径"""

    # 1. 遍历表达式中的所有算子
    ops = extract_operators(expr)

    # 2. 检查能力层：是否所有算子都可下推
    for op in ops:
        if not can_pushdown(op.name):
            return ExecutionPath.POLARS  # 有不可下推算子，回退 Polars

    # 3. 检查模式层：是否有有效的 SQL 映射
    for op in ops:
        if not build_pushdown_sql(op.name, op.params):
            return ExecutionPath.POLARS  # 无有效映射，回退 Polars

    # 4. 检查开关层：运行时是否启用
    for op in ops:
        if not config.is_enabled(op.name):
            return ExecutionPath.POLARS  # 运行时禁用，回退 Polars

        # 检查窗口限制
        if "window" in op.params:
            if op.params["window"] > config.get_max_window(op.name):
                return ExecutionPath.POLARS  # 窗口超限，回退 Polars

    # 全部通过，走 QuestDB 下推
    return ExecutionPath.QUESTDB
```

---

## 失败处理策略

### 回退策略

| 情况 | 日志级别 | 行为 |
|------|---------|------|
| QuestDB 不支持某算子 | WARNING | 回退 Polars，记录原因 |
| QuestDB 执行超时 | ERROR | 回退 Polars，记录超时时间 |
| QuestDB 执行报错 | ERROR | 回退 Polars，记录错误详情 |
| 窗口超限 | INFO | 回退 Polars，正常行为 |

### 可观测性

```python
# 指标定义
PUSHDOWN_METRICS = {
    "pushdown_attempts_total": Counter,
    "pushdown_success_total": Counter,
    "pushdown_fallback_total": Counter,
    "pushdown_latency_seconds": Histogram,
}

def execute_with_pushdown(expr: Expression, config: PushdownConfig):
    """带可观测性的下推执行"""
    pushdown_attempts_total.labels(op=expr.root_op).inc()

    path = decide_execution_path(expr, config)

    if path == ExecutionPath.QUESTDB:
        try:
            start = time.time()
            result = execute_on_questdb(expr)
            pushdown_success_total.labels(op=expr.root_op).inc()
            pushdown_latency_seconds.labels(op=expr.root_op).observe(time.time() - start)
            return result
        except QuestDBTimeoutError as e:
            logger.error(f"QuestDB timeout: {e}")
            pushdown_fallback_total.labels(op=expr.root_op, reason="timeout").inc()
            return execute_on_polars(expr)
        except QuestDBError as e:
            logger.error(f"QuestDB error: {e}")
            pushdown_fallback_total.labels(op=expr.root_op, reason="error").inc()
            return execute_on_polars(expr)
    else:
        logger.info(f"Pushdown not available for {expr.root_op}, using Polars")
        pushdown_fallback_total.labels(op=expr.root_op, reason="not_supported").inc()
        return execute_on_polars(expr)
```

---

## 未来扩展

### 短期（Phase 1）

- [ ] 实现三层判定架构
- [ ] 完成首批算子下推（ts_mean/ts_sum/ts_delta/ref）
- [ ] SQLite 配置表与运行时检查
- [ ] 可观测性指标

### 中期（Phase 2）

- [ ] 扩展下推算子白名单
- [ ] 支持 ASOF JOIN 下推
- [ ] 自适应窗口限制（基于数据量动态调整）

### 长期（Phase 3）

- [ ] 基于历史执行统计的自动调优
- [ ] 复杂表达式拆分（部分下推 + 部分本地）

---

## 相关 ADR

- [ADR-026: DuckDB 定位与使用规范](adr-026-duckdb-positioning.md) - DuckDB 不承担下推角色
- [ADR-028: QuestDB 热表与物化视图 DDL](adr-028-questdb-hot-tables.md) - 下推目标表设计
- [ADR-029: 盘中实时路径与盘后批量路径](../adr-029-intraday-postmarket-paths.md) - 执行路径选择
- [ADR-012: 物化写入与查询引擎](../computation/adr-012-operator-incremental-impl.md) - 执行引擎设计
