# DQ Checkers - 数据质量检查器

## 功能概述

实现 L1/L2/L3 三层数据质量检查的具体逻辑，提供可扩展的检查器接口和丰富的预置规则。

## 检查器架构

```
┌─────────────────────────────────────────┐
│            DQEngine (协调器)             │
├─────────────────────────────────────────┤
│  TechnicalChecker  │  BusinessChecker   │
│      (L1)          │       (L2)         │
├─────────────────────────────────────────┤
│       StatisticalChecker (L3)           │
└─────────────────────────────────────────┘
```

## TechnicalChecker - L1 技术检查器

### 检查规则

| 规则 | 说明 | 严重程度 | 影响 |
|------|------|----------|------|
| `not_null` | 非空校验 | ERROR | 阻断写入 |
| `unique` | 唯一性校验 | ERROR | 阻断写入 |
| `foreign_key` | 外键引用校验 | ERROR | 阻断写入 |
| `type_check` | 数据类型校验 | ERROR | 阻断写入 |

### not_null - 非空校验

```python
# 配置示例
l1_technical:
  - rule: not_null
    columns: [sid, trade_date, open, high, low, close, volume]
    message: "关键字段不能为空"

# 检查逻辑
def _check_not_null(self, df, rule):
    columns = rule.get("columns", [])
    for col in columns:
        if col in df.columns:
            null_count = df.filter(pl.col(col).is_null()).height
            if null_count > 0:
                return DQIssue(
                    level=DQLevel.L1_TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="not_null",
                    message=f"{col} has null values",
                    affected_rows=null_count,
                )
    return None
```

### unique - 唯一性校验

```python
# 配置示例
l1_technical:
  - rule: unique
    columns: [sid, trade_date]
    message: "SID 和交易日期组合必须唯一"

# 检查逻辑
def _check_unique(self, df, rule):
    columns = rule.get("columns", [])

    # 检查所有列是否存在
    missing_cols = [c for c in columns if c not in df.columns]
    if missing_cols:
        return None

    # 统计重复行
    total_rows = df.height
    unique_rows = df.select(columns).n_unique()
    duplicate_count = total_rows - unique_rows

    if duplicate_count > 0:
        return DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="unique",
            message=f"Duplicate key: {columns}",
            affected_rows=duplicate_count,
        )
    return None
```

### foreign_key - 外键引用校验

```python
# 配置示例
l1_technical:
  - rule: foreign_key
    column: sid
    reference: "security.sid"
    message: "SID 必须在 security 表中存在"

# 检查逻辑
def _check_foreign_key(self, df, rule, context):
    column = rule.get("column")
    reference = rule.get("reference")

    # 解析引用: "dataset.column" -> dataset, column
    ref_dataset, ref_column = reference.rsplit(".", 1)

    # 获取 hub 上下文
    if not context or "hub" not in context:
        return None

    hub = context["hub"]

    # SQL 注入防护
    if ref_dataset not in self._ALLOWED_REF_DATASETS:
        return None

    # 查询参考数据
    query = f"SELECT DISTINCT {ref_column} FROM {ref_dataset}"
    result_df = hub.sql(query)

    # 执行外键校验
    valid_values = set(result_df[ref_column].drop_nulls().to_list())
    invalid_rows = df.filter(
        ~pl.col(column).is_null() & ~pl.col(column).is_in(valid_values)
    )

    if invalid_rows.height > 0:
        return DQIssue(
            level=DQLevel.L1_TECHNICAL,
            severity=DQSeverity.ERROR,
            rule_name="foreign_key",
            message=f"Column '{column}' has {invalid_rows.height} invalid references",
            affected_rows=invalid_rows.height,
            sample_data=invalid_rows.select(column).head(5).to_dicts(),
        )
    return None
```

### type_check - 数据类型校验

```python
# 配置示例
l1_technical:
  - rule: type_check
    types:
      sid: Int64
      trade_date: Date
      open: Float64
      close: Float64
      volume: Int64
    message: "数据类型不匹配"

# 检查逻辑
def _check_type(self, df, rule):
    expected_types = rule.get("types", {})

    for col, expected_type in expected_types.items():
        if col in df.columns:
            actual_dtype = str(df[col].dtype)

            # Polars dtypes: "Int64", "Float64", "String", "Date"
            if not actual_dtype.startswith(expected_type):
                return DQIssue(
                    level=DQLevel.L1_TECHNICAL,
                    severity=DQSeverity.ERROR,
                    rule_name="type_check",
                    message=f"Column '{col}' has type {actual_dtype}, expected {expected_type}",
                    affected_rows=df.height,
                )
    return None
```

## BusinessChecker - L2 业务检查器

### 检查规则

| 规则 | 说明 | 严重程度 | 影响 |
|------|------|----------|------|
| `positive` | 正值校验 | WARNING | 记录日志 |
| `expression` | 表达式校验 | WARNING | 记录日志 |
| `range_check` | 范围校验 | WARNING | 记录日志 |
| `no_zero_volume` | 非零成交量校验 | WARNING | 记录日志 |

### positive - 正值校验

```python
# 配置示例
l2_business:
  - rule: positive
    columns: [open, high, low, close, volume]
    message: "价格和成交量必须为正数"

# 检查逻辑
def _check_positive(self, df, rule):
    columns = rule.get("columns", [])

    for col in columns:
        if col in df.columns:
            invalid_count = df.filter(pl.col(col) <= 0).height
            if invalid_count > 0:
                return DQIssue(
                    level=DQLevel.L2_BUSINESS,
                    severity=DQSeverity.WARNING,
                    rule_name="positive",
                    message=f"{col} has non-positive values",
                    affected_rows=invalid_count,
                )
    return None
```

### expression - 表达式校验

```python
# 配置示例
l2_business:
  - rule: expression
    name: ohlc_consistency
    message: "OHLC 关系不正确: high >= max(open, close), low <= min(open, close)"

# 检查逻辑
def _check_expression(self, df, rule):
    name = rule.get("name", "expression")

    # OHLC 一致性检查
    if "ohlc" in name.lower():
        required_cols = ["open", "high", "low", "close"]
        if not all(col in df.columns for col in required_cols):
            return None

        # high >= max(open, close) and low <= min(open, close)
        bad_count = df.filter(
            (pl.col("high") < pl.col("open"))
            | (pl.col("high") < pl.col("close"))
            | (pl.col("low") > pl.col("open"))
            | (pl.col("low") > pl.col("close"))
        ).height

        if bad_count > 0:
            return DQIssue(
                level=DQLevel.L2_BUSINESS,
                severity=DQSeverity.WARNING,
                rule_name="ohlc_consistency",
                message="OHLC relationship violated",
                affected_rows=bad_count,
            )
    return None
```

### range_check - 范围校验

```python
# 配置示例
l2_business:
  - rule: range_check
    column: close
    min: 0.01
    max: 10000.0
    message: "收盘价格超出合理范围"

# 检查逻辑
def _check_range(self, df, rule):
    column = rule.get("column")
    if not column or column not in df.columns:
        return None

    min_val = rule.get("min")
    max_val = rule.get("max")

    conditions = []
    if min_val is not None:
        conditions.append(pl.col(column) < min_val)
    if max_val is not None:
        conditions.append(pl.col(column) > max_val)

    if not conditions:
        return None

    # 组合条件 (OR)
    condition = conditions[0]
    for cond in conditions[1:]:
        condition = condition | cond

    bad_count = df.filter(condition).height

    if bad_count > 0:
        return DQIssue(
            level=DQLevel.L2_BUSINESS,
            severity=DQSeverity.WARNING,
            rule_name="range_check",
            message=f"{column} out of range",
            affected_rows=bad_count,
        )
    return None
```

### no_zero_volume - 非零成交量校验

```python
# 配置示例
l2_business:
  - rule: no_zero_volume
    column: volume
    message: "成交量不应为零"

# 检查逻辑
def _check_no_zero_volume(self, df, rule):
    column = rule.get("column", "volume")
    if column not in df.columns:
        return None

    zero_count = df.filter(pl.col(column) == 0).height

    if zero_count > 0:
        return DQIssue(
            level=DQLevel.L2_BUSINESS,
            severity=DQSeverity.WARNING,
            rule_name="no_zero_volume",
            message=f"{column} has zero values",
            affected_rows=zero_count,
        )
    return None
```

## StatisticalChecker - L3 统计检查器

### 检查规则

| 规则 | 说明 | 严重程度 | 影响 |
|------|------|----------|------|
| `zscore` | Z-Score 异常检测 | ALERT | 发送告警 |
| `completeness` | 数据完整性检查 | ALERT | 发送告警 |

### zscore - Z-Score 异常检测

```python
# 配置示例
l3_statistical:
  - rule: zscore
    name: price_anomaly_detection
    column: close
    window: 60
    threshold: 3.0
    group_by: sid
    message: "收盘价 Z-Score 异常"

# 检查逻辑
def _check_zscore(self, dataset, trade_date, rule, hub, asset_class, market_wide):
    column = rule.get("column")
    window = rule.get("window", 60)
    threshold = rule.get("threshold", 3.0)
    group_by = rule.get("group_by")

    # 1. 查询历史数据
    trade_dt = datetime.fromisoformat(trade_date)
    start_dt = trade_dt - timedelta(days=window * 2)

    historical = hub.bars.get(
        start=start_dt.strftime("%Y-%m-%d"),
        end=trade_date,
        asset_class=asset_class,
        market_wide=market_wide,
    )

    # 2. 查询当前数据
    current = hub.bars.get(
        start=trade_date,
        end=trade_date,
        asset_class=asset_class,
        market_wide=market_wide,
    )

    # 3. 计算统计量
    if group_by:
        stats = historical.group_by(group_by).agg(
            pl.col(column).mean().alias("mean"),
            pl.col(column).std().alias("std"),
        )
        current = current.join(stats, on=group_by, how="left")
    else:
        mean_val = historical[column].mean()
        std_val = historical[column].std()
        current = current.with_columns(
            pl.lit(mean_val).alias("mean"),
            pl.lit(std_val).alias("std"),
        )

    # 4. 计算 Z-Score
    current = current.with_columns(
        ((pl.col(column) - pl.col("mean")) / pl.col("std")).alias("zscore")
    )

    # 5. 检测异常
    anomalies = current.filter(
        pl.col("zscore").is_finite() & (pl.col("zscore").abs() > threshold)
    )

    if anomalies.height > 0:
        return DQIssue(
            level=DQLevel.L3_STATISTICAL,
            severity=DQSeverity.ALERT,
            rule_name="zscore",
            message=f"Found {anomalies.height} Z-score anomalies in '{column}'",
            affected_rows=anomalies.height,
            sample_data=anomalies.select(["sid", column, "zscore"]).head(10).to_dicts(),
        )
    return None
```

### completeness - 数据完整性检查

```python
# 配置示例
l3_statistical:
  - rule: completeness
    name: daily_data_completeness
    lookback_days: 5
    message: "最近 5 个交易日数据缺失"

# 检查逻辑
def _check_completeness(self, dataset, trade_date, rule, hub, asset_class, market_wide):
    lookback_days = rule.get("lookback_days", 5)

    # 1. 查询交易日历
    trade_dt = datetime.fromisoformat(trade_date)
    start_dt = trade_dt - timedelta(days=lookback_days * 2)

    calendar = hub.calendar.get(
        start=start_dt.strftime("%Y-%m-%d"),
        end=trade_date,
    )

    # 2. 获取预期交易日
    expected_dates = set(
        calendar.filter(pl.col("is_open"))["trade_date"].cast(str).to_list()
    )

    # 3. 查询实际数据
    actual_df = hub.bars.get(
        start=start_dt.strftime("%Y-%m-%d"),
        end=trade_date,
        asset_class=asset_class,
        market_wide=market_wide,
    )

    # 4. 检查缺失
    actual_dates = set(actual_df["trade_date"].cast(str).unique().to_list())
    missing_dates = expected_dates - actual_dates

    if missing_dates:
        return DQIssue(
            level=DQLevel.L3_STATISTICAL,
            severity=DQSeverity.ALERT,
            rule_name="completeness",
            message=f"Missing data for {len(missing_dates)} trading days",
            affected_rows=len(missing_dates),
        )
    return None
```

## 检查器接口

### 基础接口

```python
from abc import ABC, abstractmethod
from typing import Any
import polars as pl

class BaseChecker(ABC):
    """检查器基类"""

    @abstractmethod
    def check(
        self,
        df: pl.DataFrame,
        rules: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[DQIssue]:
        """
        执行检查

        Args:
            df: 待检查数据
            rules: 规则配置列表
            context: 额外上下文 (如 hub, asof)

        Returns:
            DQIssue 列表
        """
        pass
```

### 扩展检查器

```python
# 自定义 L2 检查器
class CustomBusinessChecker(BusinessChecker):
    """扩展业务检查器"""

    def check(self, df, rules, context):
        issues = super().check(df, rules, context)

        # 添加自定义检查
        for rule in rules:
            if rule.get("rule") == "custom_check":
                issue = self._custom_check(df, rule)
                if issue:
                    issues.append(issue)

        return issues

    def _custom_check(self, df, rule):
        """自定义检查逻辑"""
        # 实现自定义逻辑
        return None
```

## 使用示例

### L1 + L2 写入时检查

```python
from ditto_datahub.dq import DQEngine

# 初始化引擎
engine = DQEngine(config_path="config/dq")

# 准备数据
df = pl.DataFrame({
    "sid": [1000001, 1000002],
    "trade_date": ["2024-01-02", "2024-01-02"],
    "open": [10.5, 20.3],
    "close": [10.8, 20.5],
    "volume": [1000000, 2000000],
})

# 执行检查
result = engine.check(
    df=df,
    dataset="stock_daily",
    levels=["l1", "l2"],
    context={"hub": hub},
)

# 处理结果
if result.passed:
    print("写入通过")
else:
    print(f"写入失败: {result.error_count} 个错误")
```

### L3 批量统计检查

```python
# 执行统计检查
result = engine.check_statistical(
    dataset="stock_daily",
    trade_date="2024-01-02",
    hub=hub,
    asset_class="stock",
    market_wide=True,
)

# 处理告警
for issue in result.issues:
    if issue.severity == DQSeverity.ALERT:
        print(f"[ALERT] {issue.message}")
        print(f"样本数据: {issue.sample_data}")
```

## 性能优化

### 批量检查

```python
# 一次执行多个规则
issues = checker.check(df, rules)

# 比逐个检查更高效
# for rule in rules:
#     issue = checker._check_rule(df, rule)
```

### 外键缓存

```python
# 外键检查时缓存参考数据
class TechnicalChecker:
    def __init__(self):
        self._ref_cache: dict[str, set] = {}

    def _load_reference(self, dataset, column, hub):
        cache_key = f"{dataset}.{column}"

        if cache_key not in self._ref_cache:
            query = f"SELECT DISTINCT {column} FROM {dataset}"
            result_df = hub.sql(query)
            self._ref_cache[cache_key] = set(
                result_df[column].drop_nulls().to_list()
            )

        return self._ref_cache[cache_key]
```

## 错误处理

### 检查失败

```python
# 检查器不应抛出异常，而是返回 DQIssue
def _check_rule(self, df, rule, context):
    try:
        # 检查逻辑
        pass
    except Exception as e:
        logger.error(
            "dq_check_error",
            event="dq_check",
            rule=rule.get("rule"),
            error=str(e),
        )
        return None  # 返回 None 而非抛出异常
```

## 相关文档

- [DQ 模块总览](../README.md)
- [配置示例](../../../../../config/dq/)
- [数据质量设计](../../../../../docs/design/09_data_quality_design.md)
