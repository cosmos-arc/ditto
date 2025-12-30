# DQ 检查器完善实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 完成数据质量检查器中未实现的 L1/L3 检查器，并确保调整因子数据包含 knowledge_date 字段

**架构:** 扩展现有的 DQ 检查框架，实现缺失的 type_check、foreign_key、zscore、completeness 检查器，并在数据摄取时验证必需列

**技术栈:** Polars, Pytest, Python 3.12+

---

## Task 1: 实现 check_required_columns 函数

**文件:**
- 修改: `packages/datahub/src/ditto_datahub/runtime/dq_rules.py:79` (在 check_weight_positive 之后)

**Step 1: 添加检查函数**

```python
def check_required_columns(
    df: pl.DataFrame, params: dict[str, Any]
) -> tuple[bool, int, str]:
    """Check required columns exist.

    Args:
        df: Data to check
        params: Dict with "columns" key containing list of required column names

    Returns:
        Tuple of (passed, affected_columns, message)
    """
    required = params.get("columns", [])
    missing = [col for col in required if col not in df.columns]

    if missing:
        logger.warning(
            "dq_rule_missing_columns",
            event="dq_check",
            rule="required_columns",
            missing_columns=missing,
        )

    return (
        len(missing) == 0,
        len(missing),
        f"Missing columns: {missing}" if missing else "All required columns present",
    )
```

**Step 2: 为 adj_factor 添加规则**

修改 DQ_RULES 字典中 `adj_factor` 的配置（第 216-224 行）:

```python
"adj_factor": [
    DQRule(
        "primary_key_unique",
        DQSeverity.ERROR,
        check_pk_unique,
        {"keys": ["sid", "trade_date"]},
    ),
    DQRule(
        "has_knowledge_date",
        DQSeverity.ERROR,
        check_required_columns,
        {"columns": ["knowledge_date"]},
    ),
],
```

**Step 3: 运行测试验证**

```bash
cd d:/code/quant/ditto
pixi run -e dev pytest tests/unit/test_dq_rules.py -v -k adj_factor
```

**Step 4: 提交**

```bash
git add packages/datahub/src/ditto_datahub/runtime/dq_rules.py
git commit -m "feat(datahub): 添加 required_columns DQ 检查器

- 新增 check_required_columns 函数验证必需列存在
- 为 adj_factor 数据集添加 knowledge_date 必填检查
- 确保调整因子数据始终包含 knowledge_date 字段
```

---

## Task 2: 实现 TechnicalChecker._check_type()

**文件:**
- 修改: `packages/datahub/src/ditto_datahub/dq/checkers/technical.py:141-144`

**Step 1: 先写测试**

创建 `packages/datahub/tests/unit/dq/checkers/test_technical_checker.py`:

```python
"""Tests for TechnicalChecker."""

import polars as pl
import pytest
from ditto_datahub.dq.checkers.technical import TechnicalChecker
from ditto_datahub.dq.models import DQLevel, DQSeverity


def test_type_check_valid():
    """Test type check with valid types."""
    df = pl.DataFrame({
        "sid": [1, 2, 3],
        "close": [10.0, 20.0, 30.0],
        "volume": [100, 200, 300],
    })
    rule = {
        "rule": "type_check",
        "types": {"sid": "Int64", "close": "Float64", "volume": "Int64"}
    }

    checker = TechnicalChecker()
    issues = checker.check(df, [rule])

    assert len(issues) == 0


def test_type_check_invalid():
    """Test type check with invalid types."""
    df = pl.DataFrame({
        "sid": [1, 2, 3],  # Int64
        "close": ["10.0", "20.0", "30.0"],  # String (wrong)
    })
    rule = {
        "rule": "type_check",
        "types": {"sid": "Int64", "close": "Float64"}
    }

    checker = TechnicalChecker()
    issues = checker.check(df, [rule])

    assert len(issues) == 1
    assert issues[0].level == DQLevel.L1_TECHNICAL
    assert issues[0].severity == DQSeverity.ERROR
    assert "close" in issues[0].message


def test_type_check_column_not_exist():
    """Test type check with non-existent column (should skip)."""
    df = pl.DataFrame({"sid": [1, 2, 3]})
    rule = {
        "rule": "type_check",
        "types": {"sid": "Int64", "close": "Float64"}  # close doesn't exist
    }

    checker = TechnicalChecker()
    issues = checker.check(df, [rule])

    assert len(issues) == 0  # Should skip missing columns
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_technical_checker.py::test_type_check_valid -v
```

预期: PASS (检查器返回 None，即无问题)

**Step 3: 运行类型错误测试**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_technical_checker.py::test_type_check_invalid -v
```

预期: FAIL (检查器未实现，返回 None)

**Step 4: 实现检查器**

```python
def _check_type(self, df: pl.DataFrame, rule: dict) -> DQIssue | None:
    """Check data types.

    Args:
        df: Data to check
        rule: Rule config with "types" dict mapping column -> expected dtype

    Returns:
        DQIssue if type mismatch, None otherwise
    """
    expected_types = rule.get("types", {})

    for col, expected_type in expected_types.items():
        if col not in df.columns:
            continue

        actual_dtype = str(df[col].dtype)
        # Polars dtypes like "Int64", "Float64", "String"
        if not actual_dtype.startswith(expected_type):
            logger.warning(
                "dq_rule_type_mismatch",
                event="dq_check",
                rule="type_check",
                column=col,
                expected=expected_type,
                actual=actual_dtype,
            )
            return DQIssue(
                level=DQLevel.L1_TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="type_check",
                message=f"Column '{col}' has type {actual_dtype}, expected {expected_type}",
                affected_rows=df.height,
            )

    return None
```

**Step 5: 运行测试验证通过**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_technical_checker.py -v
```

**Step 6: 提交**

```bash
git add packages/datahub/src/ditto_datahub/dq/checkers/technical.py
git add packages/datahub/tests/unit/dq/checkers/test_technical_checker.py
git commit -m "feat(datahub): 实现 type_check DQ 检查器

- 实现 TechnicalChecker._check_type() 方法
- 验证列数据类型是否符合预期
- 添加单元测试覆盖正常/异常/边界情况
"
```

---

## Task 3: 实现 TechnicalChecker._check_foreign_key()

**文件:**
- 修改: `packages/datahub/src/ditto_datahub/dq/checkers/technical.py:130-139`

**Step 1: 先写测试**

```python
def test_foreign_key_valid():
    """Test foreign key check with valid references."""
    # Mock context with hub
    df = pl.DataFrame({
        "sid": [1, 2, 3],
        "index_sid": [100, 200, 300],
    })

    # Mock hub that returns valid sids
    mock_hub = MagicMock()
    mock_hub.execute.return_value.pl.return_value = pl.DataFrame({
        "sid": [100, 200, 300, 400]
    })

    rule = {
        "rule": "foreign_key",
        "column": "index_sid",
        "reference": "security.sid"
    }
    context = {"hub": mock_hub}

    checker = TechnicalChecker()
    issues = checker.check(df, [rule], context)

    assert len(issues) == 0


def test_foreign_key_invalid():
    """Test foreign key check with invalid references."""
    df = pl.DataFrame({
        "sid": [1, 2, 3],
        "index_sid": [100, 999, 300],  # 999 is invalid
    })

    mock_hub = MagicMock()
    mock_hub.execute.return_value.pl.return_value = pl.DataFrame({
        "sid": [100, 200, 300, 400]
    })

    rule = {
        "rule": "foreign_key",
        "column": "index_sid",
        "reference": "security.sid"
    }
    context = {"hub": mock_hub}

    checker = TechnicalChecker()
    issues = checker.check(df, [rule], context)

    assert len(issues) == 1
    assert issues[0].rule_name == "foreign_key"
    assert issues[0].affected_rows == 1


def test_foreign_key_no_context():
    """Test foreign key check without hub context (should skip)."""
    df = pl.DataFrame({"index_sid": [100, 200]})
    rule = {"rule": "foreign_key", "column": "index_sid", "reference": "security.sid"}

    checker = TechnicalChecker()
    issues = checker.check(df, [rule], context=None)

    assert len(issues) == 0  # Should skip without context
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_technical_checker.py::test_foreign_key_invalid -v
```

**Step 3: 实现检查器**

```python
def _check_foreign_key(
    self,
    df: pl.DataFrame,
    rule: dict,
    context: dict[str, Any] | None = None,
) -> DQIssue | None:
    """Check foreign key constraint.

    Args:
        df: Data to check
        rule: Rule config with "column" and "reference" (format: "dataset.column")
        context: Optional context containing "hub" for querying reference data

    Returns:
        DQIssue if FK violation, None otherwise
    """
    column = rule.get("column")
    reference = rule.get("reference")

    if not column or not reference:
        return None

    # Need hub context to validate
    if not context or "hub" not in context:
        logger.debug(
            "dq_fk_skip_no_context",
            event="dq_check",
            rule="foreign_key",
            column=column,
        )
        return None

    hub = context["hub"]

    try:
        # Parse reference: "dataset.column" -> dataset, column
        if "." not in reference:
            logger.warning(
                "dq_fk_invalid_reference",
                event="dq_check",
                reference=reference,
            )
            return None

        ref_dataset, ref_column = reference.rsplit(".", 1)

        # Query reference values
        query = f"SELECT DISTINCT {ref_column} FROM {ref_dataset}"
        result_df = hub.execute(query)

        if result_df.is_empty() or ref_column not in result_df.columns:
            logger.warning(
                "dq_fk_empty_reference",
                event="dq_check",
                dataset=ref_dataset,
                column=ref_column,
            )
            return None

        valid_values = set(result_df[ref_column].drop_null().to_list())

        # Check for invalid values
        if column not in df.columns:
            return None

        invalid_rows = df.filter(
            ~pl.col(column).is_null() & ~pl.col(column).is_in(valid_values)
        )

        if invalid_rows.height > 0:
            logger.warning(
                "dq_rule_fk_violation",
                event="dq_check",
                rule="foreign_key",
                column=column,
                reference=reference,
                invalid_count=invalid_rows.height,
            )
            return DQIssue(
                level=DQLevel.L1_TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="foreign_key",
                message=f"Column '{column}' has {invalid_rows.height} invalid references to {reference}",
                affected_rows=invalid_rows.height,
                sample_data=invalid_rows.select(column).head(5).to_dicts(),
            )

    except Exception as e:
        logger.error(
            "dq_fk_check_error",
            event="dq_check",
            error=str(e),
        )
        # Don't fail the whole DQ check on FK error
        return None

    return None
```

**Step 4: 运行测试验证**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_technical_checker.py::test_foreign_key -v
```

**Step 5: 提交**

```bash
git add packages/datahub/src/ditto_datahub/dq/checkers/technical.py
git add packages/datahub/tests/unit/dq/checkers/test_technical_checker.py
git commit -m "feat(datahub): 实现 foreign_key DQ 检查器

- 实现 TechnicalChecker._check_foreign_key() 方法
- 支持通过 DataHub 查询参考表验证外键
- 缺少 hub 上下文时跳过检查（不阻塞）
- 添加完整的单元测试
"
```

---

## Task 4: 实现 StatisticalChecker._check_zscore()

**文件:**
- 修改: `packages/datahub/src/ditto_datahub/dq/checkers/statistical.py:72-97`

**Step 1: 先写测试**

创建 `packages/datahub/tests/unit/dq/checkers/test_statistical_checker.py`:

```python
"""Tests for StatisticalChecker."""

from datetime import date, timedelta
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.dq.checkers.statistical import StatisticalChecker
from ditto_datahub.dq.models import DQLevel, DQSeverity


@pytest.fixture
def mock_hub_with_history():
    """Create mock hub with historical data."""
    hub = MagicMock()

    # Mock historical data (60 days)
    dates = [date.today() - timedelta(days=i) for i in range(60, 0, -1)]
    historical_data = []
    for d in dates:
        historical_data.extend([
            {"sid": 1, "trade_date": d, "close": 100.0},
            {"sid": 2, "trade_date": d, "close": 200.0},
        ])

    hub.bars.get.return_value = pl.DataFrame(historical_data)
    return hub


def test_zscore_no_anomalies(mock_hub_with_history):
    """Test Z-score check with normal data."""
    df = pl.DataFrame({
        "sid": [1, 2],
        "trade_date": [date.today(), date.today()],
        "close": [100.0, 200.0],  # Normal values
    })

    rule = {
        "rule": "zscore",
        "column": "close",
        "window": 60,
        "threshold": 3.0,
    }

    checker = StatisticalChecker()
    issues = checker.check("test_dataset", str(date.today()), [rule], mock_hub_with_history)

    assert len(issues) == 0


def test_zscore_detects_anomalies(mock_hub_with_history):
    """Test Z-score check detects outliers."""
    df = pl.DataFrame({
        "sid": [1],
        "trade_date": [date.today()],
        "close": 500.0,  # Way outside normal range (100-200)
    })

    rule = {
        "rule": "zscore",
        "column": "close",
        "window": 60,
        "threshold": 3.0,
    }

    checker = StatisticalChecker()
    issues = checker.check("test_dataset", str(date.today()), [rule], mock_hub_with_history)

    assert len(issues) == 1
    assert issues[0].level == DQLevel.L3_STATISTICAL
    assert issues[0].severity == DQSeverity.ALERT
    assert "zscore" in issues[0].rule_name


def test_zscore_with_group_by():
    """Test Z-score check with grouping."""
    hub = MagicMock()
    # Mock data with different stats per sid
    hub.bars.get.return_value = pl.DataFrame({
        "sid": [1] * 60 + [2] * 60,
        "close": [100.0] * 60 + [200.0] * 60,
    })

    df = pl.DataFrame({
        "sid": [1, 2],
        "close": [105.0, 210.0],  # Both normal relative to their group
    })

    rule = {
        "rule": "zscore",
        "column": "close",
        "window": 60,
        "threshold": 3.0,
        "group_by": "sid",
    }

    checker = StatisticalChecker()
    issues = checker.check("test_dataset", str(date.today()), [rule], hub)

    assert len(issues) == 0
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_statistical_checker.py::test_zscore_no_anomalies -v
```

**Step 3: 实现检查器**

```python
def _check_zscore(
    self,
    dataset: str,
    trade_date: str,
    rule: dict,
    hub: Any,
) -> DQIssue | None:
    """Check Z-score anomaly.

    Args:
        dataset: Dataset identifier
        trade_date: Trade date to check (YYYY-MM-DD)
        rule: Rule config with column, window, threshold, group_by
        hub: DataHub instance for historical data access

    Returns:
        DQIssue if anomaly detected, None otherwise
    """
    column = rule.get("column")
    window = rule.get("window", 60)
    threshold = rule.get("threshold", 3.0)
    group_by = rule.get("group_by")

    if not column:
        return None

    try:
        from datetime import datetime, timedelta

        # Calculate start date for historical data
        trade_dt = datetime.fromisoformat(trade_date)
        start_dt = trade_dt - timedelta(days=window * 2)  # Get extra days for weekends
        start_date = start_dt.strftime("%Y-%m-%d")

        # Query historical data
        historical = hub.bars.get(
            start=start_date,
            end=trade_date,
        )

        if historical.is_empty() or column not in historical.columns:
            logger.debug(
                "dq_zscore_no_historical",
                event="dq_check",
                dataset=dataset,
                column=column,
            )
            return None

        # Calculate statistics by group or overall
        if group_by:
            stats = historical.group_by(group_by).agg(
                pl.col(column).mean().alias("mean"),
                pl.col(column).std().alias("std"),
            )

            # Get current data to check
            current = hub.bars.get(
                start=trade_date,
                end=trade_date,
            ).join(stats, on=group_by, how="left")
        else:
            mean_val = historical[column].mean()
            std_val = historical[column].std()

            current = hub.bars.get(
                start=trade_date,
                end=trade_date,
            ).with_columns(
                pl.lit(mean_val).alias("mean"),
                pl.lit(std_val).alias("std"),
            )

        if current.is_empty():
            return None

        # Calculate Z-score
        current = current.with_columns(
            ((pl.col(column) - pl.col("mean")) / pl.col("std")).alias("zscore")
        )

        # Find anomalies
        anomalies = current.filter(
            pl.col("zscore").is_finite() & (pl.col("zscore").abs() > threshold)
        )

        if anomalies.height > 0:
            logger.warning(
                "dq_rule_zscore_anomaly",
                event="dq_check",
                dataset=dataset,
                column=column,
                anomaly_count=anomalies.height,
                threshold=threshold,
            )
            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="zscore",
                message=f"Found {anomalies.height} Z-score anomalies in '{column}' (threshold: {threshold})",
                affected_rows=anomalies.height,
                sample_data=anomalies.select(["sid", column, "zscore"]).head(10).to_dicts(),
            )

    except Exception as e:
        logger.error(
            "dq_zscore_error",
            event="dq_check",
            error=str(e),
        )
        return None

    return None
```

**Step 4: 运行测试验证**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_statistical_checker.py::test_zscore -v
```

**Step 5: 提交**

```bash
git add packages/datahub/src/ditto_datahub/dq/checkers/statistical.py
git add packages/datahub/tests/unit/dq/checkers/test_statistical_checker.py
git commit -m "feat(datahub): 实现 zscore DQ 检查器

- 实现 StatisticalChecker._check_zscore() 方法
- 使用历史数据计算 Z-score 检测异常值
- 支持分组统计（group_by）
- 添加完整的单元测试
"
```

---

## Task 5: 实现 StatisticalChecker._check_completeness()

**文件:**
- 修改: `packages/datahub/src/ditto_datahub/dq/checkers/statistical.py:99-123`

**Step 1: 先写测试**

```python
@pytest.fixture
def mock_hub_with_calendar():
    """Create mock hub with calendar data."""
    hub = MagicMock()

    # Mock calendar with 5 trading days
    dates = [date.today() - timedelta(days=i) for i in range(6, 0, -1) if (date.today() - timedelta(days=i)).weekday() < 5]
    calendar_data = [
        {"trade_date": d, "is_open": True}
        for d in dates
    ]

    hub.calendar.get.return_value = pl.DataFrame(calendar_data)
    return hub


def test_completeness_full(mock_hub_with_calendar):
    """Test completeness check with all data present."""
    # Assume calendar has 5 trading days
    df = pl.DataFrame({
        "trade_date": mock_hub_with_calendar.calendar.get.return_value["trade_date"].to_list(),
        "close": [100.0] * 5,
    })

    rule = {
        "rule": "completeness",
        "lookback_days": 5,
    }

    checker = StatisticalChecker()
    issues = checker.check("test_dataset", str(date.today()), [rule], mock_hub_with_calendar)

    assert len(issues) == 0


def test_completeness_missing_days(mock_hub_with_calendar):
    """Test completeness check with missing trading days."""
    df = pl.DataFrame({
        "trade_date": [date.today() - timedelta(days=i) for i in [3, 2]],  # Missing days 5, 4, 1
        "close": [100.0, 200.0],
    })

    rule = {
        "rule": "completeness",
        "lookback_days": 5,
    }

    checker = StatisticalChecker()
    issues = checker.check("test_dataset", str(date.today()), [rule], mock_hub_with_calendar)

    assert len(issues) == 1
    assert issues[0].rule_name == "completeness"
    assert "missing" in issues[0].message.lower()
```

**Step 2: 运行测试确认失败**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_statistical_checker.py::test_completeness_missing_days -v
```

**Step 3: 实现检查器**

```python
def _check_completeness(
    self,
    dataset: str,
    trade_date: str,
    rule: dict,
    hub: Any,
) -> DQIssue | None:
    """Check data completeness.

    Args:
        dataset: Dataset identifier
        trade_date: Current trade date (YYYY-MM-DD)
        rule: Rule config with lookback_days
        hub: DataHub instance for calendar access

    Returns:
        DQIssue if missing data detected, None otherwise
    """
    lookback_days = rule.get("lookback_days", 5)

    try:
        from datetime import datetime, timedelta

        trade_dt = datetime.fromisoformat(trade_date)
        start_dt = trade_dt - timedelta(days=lookback_days * 2)  # Extra buffer
        start_date = start_dt.strftime("%Y-%m-%d")

        # Query trading calendar
        calendar = hub.calendar.get(
            start=start_date,
            end=trade_date,
        )

        if calendar.is_empty():
            logger.debug(
                "dq_completeness_no_calendar",
                event="dq_check",
                dataset=dataset,
            )
            return None

        # Get expected trading days (open days only)
        expected_dates = set(
            calendar.filter(pl.col("is_open") == True)["trade_date"].cast(str).to_list()
        )

        # Query actual data dates
        actual_df = hub.bars.get(
            start=start_date,
            end=trade_date,
        )

        if actual_df.is_empty():
            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="completeness",
                message=f"No data found for dataset '{dataset}' in the last {lookback_days} days",
                affected_rows=0,
            )

        actual_dates = set(actual_df["trade_date"].cast(str).unique().to_list())

        # Check for missing dates
        missing_dates = expected_dates - actual_dates

        if missing_dates:
            sorted_missing = sorted(list(missing_dates))
            logger.warning(
                "dq_rule_completeness_gap",
                event="dq_check",
                dataset=dataset,
                missing_count=len(missing_dates),
                missing_dates=sorted_missing,
            )
            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="completeness",
                message=f"Missing data for {len(missing_dates)} trading days: {sorted_missing}",
                affected_rows=len(missing_dates),
            )

    except Exception as e:
        logger.error(
            "dq_completeness_error",
            event="dq_check",
            error=str(e),
        )
        return None

    return None
```

**Step 4: 运行测试验证**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_statistical_checker.py::test_completeness -v
```

**Step 5: 提交**

```bash
git add packages/datahub/src/ditto_datahub/dq/checkers/statistical.py
git add packages/datahub/tests/unit/dq/checkers/test_statistical_checker.py
git commit -m "feat(datahub): 实现 completeness DQ 检查器

- 实现 StatisticalChecker._check_completeness() 方法
- 通过交易日历验证数据完整性
- 检测缺失的交易日数据
- 添加完整的单元测试
"
```

---

## Task 6: 更新数据摄取任务处理 knowledge_date

**文件:**
- 修改: `packages/datahub/src/ditto_datahub/sources/tushare/source.py`

**Step 1: 修改 fetch_adj_factor 方法**

在 `fetch_adj_factor` 方法中（第 519-595 行），添加 `knowledge_date` 列：

```python
@traced("source.tushare.fetch_adj_factor")
def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
    """
    Fetch stock adjustment factors.

    Args:
        trade_date: Trade date (YYYY-MM-DD).

    Returns:
        DataFrame with columns:
        - src_code: Source code
        - trade_date: Date
        - knowledge_date: Knowledge date (same as trade_date for Tushare)
        - adj_factor: Float64

    Raises:
        SourceFetchError: If fetch fails.

    """
    logger.info(
        "Fetching Tushare adj factors",
        event="tushare_adj_factor_fetch_start",
        trade_date=trade_date,
    )

    try:
        ts_date = trade_date.replace("-", "")
        response = self._client.query(
            api_name="adj_factor",
            trade_date=ts_date,
        )

        if len(response) == 0:
            logger.info(
                "Tushare adj factor empty",
                event="tushare_adj_factor_fetch_complete",
                row_count=0,
            )
            return pl.DataFrame(
                schema={
                    "src_code": pl.String,
                    "trade_date": pl.Date,
                    "knowledge_date": pl.Date,  # 添加此列
                    "adj_factor": pl.Float64,
                }
            )

        df = pl.from_pandas(response).rename({"ts_code": "src_code"})

        # 添加 knowledge_date 列（Tushare 当日数据，knowledge_date = trade_date）
        df = df.with_columns(
            pl.col("trade_date").str.strptime(pl.Date, "%Y%m%d").alias("trade_date"),
            pl.col("trade_date").str.strptime(pl.Date, "%Y%m%d").alias("knowledge_date"),  # 新增
            pl.col("adj_factor").cast(pl.Float64),
        )

        df = df.select("src_code", "trade_date", "knowledge_date", "adj_factor")

        row_count = len(df)
        logger.info(
            "Tushare adj factor fetched",
            event="tushare_adj_factor_fetch_complete",
            row_count=row_count,
        )
        M.data_records.add(
            row_count,
            {"source": "tushare", "dataset": "adj_factor", "status": "success"},
        )

        return df

    except Exception as e:
        logger.error(
            "Tushare adj factor fetch failed",
            event="tushare_adj_factor_fetch_error",
            error=str(e),
        )
        raise SourceFetchError(
            message="Failed to fetch adj factor from Tushare",
            source="tushare",
            dataset="adj_factor",
            original_error=str(e),
        ) from e
```

**Step 2: 同样修改 fetch_fund_adj 方法**

对 `fetch_fund_adj` 方法（第 597-673 行）做相同修改，添加 `knowledge_date` 列。

**Step 3: 运行现有测试**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/test_source.py -v -k adj_factor
```

**Step 4: 提交**

```bash
git add packages/datahub/src/ditto_datahub/sources/tushare/source.py
git commit -m "feat(datahub): 为调整因子数据添加 knowledge_date 字段

- 在 fetch_adj_factor 和 fetch_fund_adj 中添加 knowledge_date 列
- Tushare 当日数据，knowledge_date 设置为 trade_date
- 确保 adj_factor 数据集通过 DQ 检查
"
```

---

## Task 7: 运行完整测试套件

**Step 1: 运行所有 DQ 相关测试**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/ -v
pixi run -e dev pytest packages/datahub/tests/unit/runtime/test_dq_checker.py -v
```

**Step 2: 运行相关单元测试**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/sources/tushare/ -v
pixi run -e dev pytest packages/datahub/tests/unit/repositories/test_bars_repository.py -v -k adj
```

**Step 3: 运行类型检查**

```bash
pixi run -e dev ruff check packages/datahub/src/ditto_datahub/dq/
pixi run -e dev mypy packages/datahub/src/ditto_datahub/dq/
```

**Step 4: 更新文档**

更新 `packages/datahub/README.md` 中的 DQ 功能说明：

```markdown
### 数据质量检查

已实现的检查器：

**L1 技术检查**
- `not_null`: 非空约束
- `unique`: 唯一性约束
- `type_check`: 数据类型验证
- `foreign_key`: 外键验证
- `required_columns`: 必需列验证

**L3 统计检查**
- `zscore`: Z-score 异常检测
- `completeness`: 数据完整性检查
```

**Step 5: 最终提交**

```bash
git add packages/datahub/README.md
git commit -m "docs(datahub): 更新 DQ 检查器文档

- 记录新增的 type_check、foreign_key、required_columns 检查器
- 记录新增的 zscore、completeness 检查器
"
```

---

## 总结

此计划完成了以下内容：

1. ✅ 实现 `check_required_columns` 函数验证必需列
2. ✅ 为 `adj_factor` 数据集添加 `knowledge_date` 必填检查
3. ✅ 实现 `TechnicalChecker._check_type()` 类型检查
4. ✅ 实现 `TechnicalChecker._check_foreign_key()` 外键检查
5. ✅ 实现 `StatisticalChecker._check_zscore()` Z-score 异常检测
6. ✅ 实现 `StatisticalChecker._check_completeness()` 数据完整性检查
7. ✅ 更新数据摄取任务，确保调整因子包含 `knowledge_date`
8. ✅ 完整的单元测试覆盖

每个任务遵循 TDD 流程：写测试 → 确认失败 → 实现 → 确认通过 → 提交
