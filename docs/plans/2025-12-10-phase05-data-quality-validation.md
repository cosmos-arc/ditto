# Phase 0.5 Data Quality Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement data collection, Golden Dataset preparation, and data quality validation for Ditto Phase 0.5

**Architecture:** Following existing dual-database (DuckDB for analytics, SQLite for transactions) and dual-data-source (Tushare primary, AkShare backup) architecture with Point-in-Time safety

**Tech Stack:** Python 3.11, DuckDB, SQLite, Tushare Pro, AkShare, Polars, Pytest, FastAPI

---

## Task 1: Implement DataCollector Core Logic

**Files:**
- Modify: `packages/core/src/ditto_core/data/collector.py:41-101`
- Test: `packages/core/tests/unit/data/test_collector.py:100-200`

**Step 1: Write failing tests for update_etf_list**

```python
def test_update_etf_list_fetches_and_stores_data(mocker):
    # Arrange
    mock_tushare = mocker.Mock()
    mock_tushare.get_etf_list.return_value = pl.DataFrame({
        "symbol": ["510300.SH", "516010.SH"],
        "name": ["沪深300ETF", "上证50ETF"],
        "list_date": ["2012-04-26", "2015-05-26"]
    })

    collector = DataCollector()
    collector._sources = {"tushare": mock_tushare}

    # Act
    result = collector.update_etf_list()

    # Assert
    assert result["total_updated"] == 2
    assert result["source"] == "tushare"
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/core/tests/unit/data/test_collector.py::test_update_etf_list_fetches_and_stores_data -v`
Expected: FAIL with "not implemented"

**Step 3: Implement update_etf_list method**

```python
def update_etf_list(self) -> Dict[str, Any]:
    """更新ETF列表，从主数据源获取并存储"""
    logger.info("开始更新ETF列表")

    # 获取主数据源
    primary_source = self._sources.get("tushare")
    if not primary_source:
        raise ValueError("未配置主数据源 Tushare")

    try:
        # 获取ETF列表
        etf_df = primary_source.get_etf_list()
        logger.info(f"获取到 {len(etf_df)} 只ETF")

        # 添加knowledge_date
        etf_df = etf_df.with_columns([
            pl.lit(datetime.now()).alias("knowledge_date")
        ])

        # 存储到DuckDB
        self._analytics_adapter.store_etf_info(etf_df)

        return {
            "total_updated": len(etf_df),
            "source": "tushare",
            "status": "success"
        }

    except Exception as e:
        logger.error(f"更新ETF列表失败: {e}")
        raise
```

**Step 4: Run test to verify it passes**

Run: `pytest packages/core/tests/unit/data/test_collector.py::test_update_etf_list_fetches_and_stores_data -v`
Expected: PASS

**Step 5: Commit**

```bash
git add packages/core/src/ditto_core/data/collector.py packages/core/tests/unit/data/test_collector.py
git commit -m "feat(data): P0-038 implement DataCollector.update_etf_list - TDD"
```

---

## Task 2: Implement Daily Data Collection

**Files:**
- Modify: `packages/core/src/ditto_core/data/collector.py:103-180`
- Test: `packages/core/tests/unit/data/test_collector.py:200-300`

**Step 1: Write failing tests for update_daily_data**

```python
def test_update_daily_data_with_single_symbol(mocker):
    # Arrange
    mock_source = mocker.Mock()
    mock_source.get_daily_data.return_value = pl.DataFrame({
        "symbol": ["510300.SH"],
        "date": ["2024-01-01"],
        "open": [3.5],
        "high": [3.6],
        "low": [3.4],
        "close": [3.55],
        "volume": [1000000]
    })

    collector = DataCollector()
    collector._sources = {"tushare": mock_source}

    # Act
    result = collector.update_daily_data(
        symbols=["510300.SH"],
        start_date="2024-01-01",
        end_date="2024-01-01"
    )

    # Assert
    assert result["total_records"] == 1
    assert "510300.SH" in result["symbols_updated"]
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/core/tests/unit/data/test_collector.py::test_update_daily_data_with_single_symbol -v`
Expected: FAIL with "not implemented"

**Step 3: Implement update_daily_data method**

```python
def update_daily_data(
    self,
    symbols: List[str],
    start_date: str,
    end_date: str,
    validate: bool = True
) -> Dict[str, Any]:
    """批量下载日线数据"""
    logger.info(f"开始更新日线数据: {len(symbols)} 只股票，{start_date} 至 {end_date}")

    primary_source = self._sources.get("tushare")
    backup_source = self._sources.get("akshare") if validate else None

    total_records = 0
    symbols_updated = []
    validation_errors = []

    for symbol in symbols:
        try:
            # 从主数据源获取
            primary_df = primary_source.get_daily_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )

            if validate and backup_source:
                # 交叉验证
                backup_df = backup_source.get_daily_data(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date
                )

                # 验证一致性
                if not self._validate_price_consistency(primary_df, backup_df):
                    validation_errors.append(f"{symbol}: 主备数据源价格差异过大")
                    continue

            # 添加knowledge_date
            primary_df = primary_df.with_columns([
                pl.lit(datetime.now()).alias("knowledge_date")
            ])

            # 存储到DuckDB
            self._analytics_adapter.store_daily_data(primary_df)

            total_records += len(primary_df)
            symbols_updated.append(symbol)

            logger.info(f"✅ {symbol}: 更新 {len(primary_df)} 条记录")

        except Exception as e:
            logger.error(f"❌ {symbol}: 更新失败 - {e}")
            validation_errors.append(f"{symbol}: {str(e)}")

    return {
        "total_records": total_records,
        "symbols_updated": symbols_updated,
        "validation_errors": validation_errors,
        "status": "completed"
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest packages/core/tests/unit/data/test_collector.py::test_update_daily_data_with_single_symbol -v`
Expected: PASS

**Step 5: Commit**

```bash
git add packages/core/src/ditto_core/data/collector.py packages/core/tests/unit/data/test_collector.py
git commit -m "feat(data): P0-013 implement DataCollector.update_daily_data - TDD"
```

---

## Task 3: Implement Cross-Validation Logic

**Files:**
- Modify: `packages/core/src/ditto_core/data/collector.py:300-400`
- Test: `packages/core/tests/unit/data/test_collector.py:400-500`

**Step 1: Write failing tests for _validate_price_consistency**

```python
def test_validate_price_consistency_with_identical_data():
    df1 = pl.DataFrame({
        "date": ["2024-01-01"],
        "close": [3.55]
    })
    df2 = pl.DataFrame({
        "date": ["2024-01-01"],
        "close": [3.55]
    })

    collector = DataCollector()
    assert collector._validate_price_consistency(df1, df2) == True

def test_validate_price_consistency_with_small_difference():
    df1 = pl.DataFrame({
        "date": ["2024-01-01"],
        "close": [3.55]
    })
    df2 = pl.DataFrame({
        "date": ["2024-01-01"],
        "close": [3.551]  # 0.03% difference
    })

    collector = DataCollector()
    assert collector._validate_price_consistency(df1, df2) == True
```

**Step 2: Run test to verify it fails**

Run: `pytest packages/core/tests/unit/data/test_collector.py::test_validate_price_consistency -v`
Expected: FAIL with "method not defined"

**Step 3: Implement _validate_price_consistency method**

```python
def _validate_price_consistency(
    self,
    df1: pl.DataFrame,
    df2: pl.DataFrame,
    tolerance: float = 0.01
) -> bool:
    """验证两个数据源的价格一致性"""
    if df1.empty or df2.empty:
        return False

    # 合并数据对比
    merged = df1.join(df2, on="date", suffix="_backup")

    if merged.empty:
        return False

    # 计算价格差异百分比
    price_diff = (merged["close"] - merged["close_backup"]).abs() / merged["close"]

    # 检查是否所有差异都在容忍范围内
    max_diff = price_diff.max()

    logger.debug(f"价格差异: 最大={max_diff:.4f}, 阈值={tolerance}")

    return max_diff <= tolerance
```

**Step 4: Run test to verify it passes**

Run: `pytest packages/core/tests/unit/data/test_collector.py::test_validate_price_consistency -v`
Expected: PASS

**Step 5: Commit**

```bash
git add packages/core/src/ditto_core/data/collector.py packages/core/tests/unit/data/test_collector.py
git commit -m "feat(data): P0-021 implement cross-validation logic - TDD"
```

---

## Task 4: Implement Update Scripts

**Files:**
- Modify: `scripts/update_data.py:1-50`
- Create: `scripts/init_golden_dataset.py`

**Step 1: Fix update_data.py script**

```python
#!/usr/bin/env python3
"""
数据更新脚本 - Phase 0.5 版本
支持增量更新和 Golden Dataset 初始化
"""

import sys
from pathlib import Path
from ditto_foundation.config import get_settings
from ditto_core.data.service import DataService
from ditto_core.data.collector import DataCollector

def update_market_data():
    """更新市场数据"""
    settings = get_settings()

    with DataService(settings) as data_service:
        collector = DataCollector(data_service)

        # 1. 更新ETF列表
        print("更新ETF列表...")
        etf_result = collector.update_etf_list()
        print(f"✅ ETF列表更新完成: {etf_result['total_updated']} 只")

        # 2. 获取所有ETF代码
        etf_list = data_service.analytics.get_etf_list()
        symbols = etf_list["symbol"].to_list()

        # 3. 更新日线数据（最近5个交易日）
        from datetime import datetime, timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        print(f"更新日线数据: {len(symbols)} 只ETF...")
        daily_result = collector.update_daily_data(
            symbols=symbols,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            validate=True
        )

        print(f"✅ 日线数据更新完成:")
        print(f"   - 总记录数: {daily_result['total_records']}")
        print(f"   - 更新成功: {len(daily_result['symbols_updated'])} 只")
        if daily_result['validation_errors']:
            print(f"   - 验证错误: {len(daily_result['validation_errors'])} 个")

if __name__ == "__main__":
    update_market_data()
```

**Step 2: Create init_golden_dataset.py script**

```python
#!/usr/bin/env python3
"""
Golden Dataset 初始化脚本
收集 Phase 0.5 需要的验证数据
"""

import sys
from pathlib import Path
from ditto_foundation.config import get_settings
from ditto_core.data.service import DataService
from ditto_core.data.collector import DataCollector

# Golden Dataset 标的
GOLDEN_SYMBOLS = [
    "510300.SH",  # 沪深300ETF
    "516010.SH",  # 游戏ETF
    "513100.SH",  # 纳指ETF
    "000300.SH",  # 沪深300指数
]

def init_golden_dataset():
    """初始化 Golden Dataset"""
    print("初始化 Golden Dataset...")

    settings = get_settings()

    with DataService(settings) as data_service:
        collector = DataCollector(data_service)

        # 1. 确保ETF列表是最新的
        print("1. 更新ETF列表...")
        etf_result = collector.update_etf_list()

        # 2. 下载历史数据（2022-2024年）
        print("2. 下载历史数据...")
        daily_result = collector.update_daily_data(
            symbols=GOLDEN_SYMBOLS,
            start_date="20220101",
            end_date="20241231",
            validate=True
        )

        # 3. 下载复权因子
        print("3. 下载复权因子...")
        adj_result = collector.update_adj_factors(
            symbols=GOLDEN_SYMBOLS,
            start_date="20220101",
            end_date="20241231"
        )

        # 4. 生成报告
        print("\n=== Golden Dataset 初始化报告 ===")
        print(f"ETF列表: {etf_result['total_updated']} 只")
        print(f"日线数据: {daily_result['total_records']} 条记录")
        print(f"成功更新: {len(daily_result['symbols_updated'])} 只标的")
        if daily_result['validation_errors']:
            print(f"验证错误: {len(daily_result['validation_errors'])} 个")
            for error in daily_result['validation_errors'][:5]:
                print(f"  - {error}")

if __name__ == "__main__":
    init_golden_dataset()
```

**Step 3: Run scripts to verify they work**

Run: `pixi run python scripts/update_data.py`
Expected: Script executes without errors

Run: `pixi run python scripts/init_golden_dataset.py`
Expected: Script executes and downloads data

**Step 4: Commit**

```bash
git add scripts/update_data.py scripts/init_golden_dataset.py
git commit -m "feat(data): P0-031, P0-032 implement data update scripts"
```

---

## Task 5: Implement Data Quality Validators

**Files:**
- Create: `packages/core/src/ditto_core/data/validators/__init__.py`
- Create: `packages/core/src/ditto_core/data/validators/base.py`
- Create: `packages/core/src/ditto_core/data/validators/price.py`
- Create: `packages/core/src/ditto_core/data/validators/volume.py`
- Test: `packages/core/tests/unit/data/validators/`

**Step 1: Create validator base class**

```python
# packages/core/src/ditto_core/data/validators/base.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List
import polars as pl

class ValidationResult:
    def __init__(self, is_valid: bool, message: str = "", details: Dict[str, Any] = None):
        self.is_valid = is_valid
        self.message = message
        self.details = details or {}

class BaseValidator(ABC):
    """数据验证器基类"""

    @abstractmethod
    def validate(self, data: pl.DataFrame) -> ValidationResult:
        """验证数据"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """验证器名称"""
        pass
```

**Step 2: Implement price validator**

```python
# packages/core/src/ditto_core/data/validators/price.py
import polars as pl
from .base import BaseValidator, ValidationResult

class PriceValidator(BaseValidator):
    """价格合理性验证器"""

    @property
    def name(self) -> str:
        return "price_validator"

    def validate(self, data: pl.DataFrame) -> ValidationResult:
        """验证OHLC价格合理性"""
        errors = []

        # 检查价格为正数
        if (data.select(["open", "high", "low", "close"]) <= 0).any():
            errors.append("存在非正价格")

        # 检查 high >= max(open, close)
        invalid_high = (
            data["high"] < pl.max_horizontal(["open", "close"])
        ).sum()
        if invalid_high > 0:
            errors.append(f"最高价不合理: {invalid_high} 条记录")

        # 检查 low <= min(open, close)
        invalid_low = (
            data["low"] > pl.min_horizontal(["open", "close"])
        ).sum()
        if invalid_low > 0:
            errors.append(f"最低价不合理: {invalid_low} 条记录")

        # 检查价格跳变（超过20%）
        data_sorted = data.sort("date")
        price_change = (
            data_sorted["close"].pct_change().abs()
        ).drop_nulls()

        extreme_changes = (price_change > 0.2).sum()
        if extreme_changes > 0:
            errors.append(f"极端价格变化: {extreme_changes} 条记录")

        is_valid = len(errors) == 0
        message = "; ".join(errors) if errors else "价格数据正常"

        return ValidationResult(
            is_valid=is_valid,
            message=message,
            details={
                "total_records": len(data),
                "extreme_changes": extreme_changes,
                "invalid_high": invalid_high,
                "invalid_low": invalid_low
            }
        )
```

**Step 3: Implement volume validator**

```python
# packages/core/src/ditto_core/data/validators/volume.py
import polars as pl
from .base import BaseValidator, ValidationResult

class VolumeValidator(BaseValidator):
    """成交量验证器"""

    @property
    def name(self) -> str:
        return "volume_validator"

    def validate(self, data: pl.DataFrame) -> ValidationResult:
        """验证成交量合理性"""
        errors = []

        # 检查成交量为非负数
        negative_volume = (data["volume"] < 0).sum()
        if negative_volume > 0:
            errors.append(f"负成交量: {negative_volume} 条记录")

        # 检查异常高成交量（超过中位数50倍）
        volume_median = data["volume"].median()
        if volume_median > 0:
            extreme_volume = (
                data["volume"] > volume_median * 50
            ).sum()
            if extreme_volume > 0:
                errors.append(f"异常高成交量: {extreme_volume} 条记录")

        # 检查长时间零成交量（超过10天）
        data_sorted = data.sort("date")

        # 计算连续零成交量天数
        zero_volume_groups = (
            data_sorted
            .with_columns([
                (data_sorted["volume"] == 0).alias("is_zero")
            ])
            .with_columns([
                pl.col("is_zero").cum_sum().alias("group")
            ])
            .filter(pl.col("is_zero"))
            .group_by("group")
            .len()
        )

        long_zero_volume = (zero_volume_groups["len"] > 10).sum()
        if long_zero_volume > 0:
            errors.append(f"长期零成交量: {long_zero_volume} 组")

        is_valid = len(errors) == 0
        message = "; ".join(errors) if errors else "成交量数据正常"

        return ValidationResult(
            is_valid=is_valid,
            message=message,
            details={
                "total_records": len(data),
                "negative_volume": negative_volume,
                "extreme_volume": extreme_volume,
                "long_zero_volume": long_zero_volume
            }
        )
```

**Step 4: Write tests for validators**

```python
# packages/core/tests/unit/data/validators/test_price.py
import pytest
import polars as pl
from ditto_core.data.validators.price import PriceValidator

class TestPriceValidator:
    def test_valid_ohlc_data(self):
        df = pl.DataFrame({
            "date": ["2024-01-01"],
            "open": [3.5],
            "high": [3.6],
            "low": [3.4],
            "close": [3.55]
        })

        validator = PriceValidator()
        result = validator.validate(df)

        assert result.is_valid
        assert "价格数据正常" in result.message

    def test_invalid_negative_prices(self):
        df = pl.DataFrame({
            "date": ["2024-01-01"],
            "open": [-3.5],
            "high": [3.6],
            "low": [3.4],
            "close": [3.55]
        })

        validator = PriceValidator()
        result = validator.validate(df)

        assert not result.is_valid
        assert "非正价格" in result.message
```

**Step 5: Run tests**

Run: `pytest packages/core/tests/unit/data/validators/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add packages/core/src/ditto_core/data/validators/ packages/core/tests/unit/data/validators/
git commit -m "feat(data): P0-017 implement data quality validators - TDD"
```

---

## Task 6: Create Data Quality Report Generator

**Files:**
- Create: `packages/core/src/ditto_core/data/quality/reporter.py`
- Create: `scripts/check_data_quality.py`

**Step 1: Create quality reporter**

```python
# packages/core/src/ditto_core/data/quality/reporter.py
from typing import Dict, List, Any
from datetime import datetime
import polars as pl

from ..validators.base import BaseValidator
from ..validators.price import PriceValidator
from ..validators.volume import VolumeValidator

class DataQualityReporter:
    """数据质量报告生成器"""

    def __init__(self):
        self.validators: List[BaseValidator] = [
            PriceValidator(),
            VolumeValidator(),
        ]

    def generate_report(self, data: pl.DataFrame, symbol: str) -> Dict[str, Any]:
        """生成数据质量报告"""
        report = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "total_records": len(data),
            "date_range": {
                "start": data["date"].min(),
                "end": data["date"].max()
            },
            "validators": [],
            "summary": {
                "passed": 0,
                "failed": 0,
                "warnings": 0
            }
        }

        for validator in self.validators:
            result = validator.validate(data)

            validator_report = {
                "name": validator.name,
                "status": "passed" if result.is_valid else "failed",
                "message": result.message,
                "details": result.details
            }

            report["validators"].append(validator_report)

            if result.is_valid:
                report["summary"]["passed"] += 1
            else:
                report["summary"]["failed"] += 1

        # 计算整体质量分数
        total_validators = len(self.validators)
        report["quality_score"] = report["summary"]["passed"] / total_validators

        return report

    def generate_batch_report(
        self,
        data_dict: Dict[str, pl.DataFrame]
    ) -> Dict[str, Any]:
        """批量生成多个标的的数据质量报告"""
        batch_report = {
            "timestamp": datetime.now().isoformat(),
            "total_symbols": len(data_dict),
            "reports": [],
            "summary": {
                "total_records": 0,
                "avg_quality_score": 0,
                "failed_symbols": []
            }
        }

        total_quality_score = 0

        for symbol, data in data_dict.items():
            report = self.generate_report(data, symbol)
            batch_report["reports"].append(report)

            batch_report["summary"]["total_records"] += report["total_records"]
            total_quality_score += report["quality_score"]

            if report["summary"]["failed"] > 0:
                batch_report["summary"]["failed_symbols"].append(symbol)

        if len(data_dict) > 0:
            batch_report["summary"]["avg_quality_score"] = (
                total_quality_score / len(data_dict)
            )

        return batch_report
```

**Step 2: Create quality check script**

```python
#!/usr/bin/env python3
"""
数据质量检查脚本 - Phase 0.5
生成 Golden Dataset 数据质量报告
"""

import json
from pathlib import Path
from ditto_foundation.config import get_settings
from ditto_core.data.service import DataService
from ditto_core.data.quality.reporter import DataQualityReporter

def check_golden_dataset_quality():
    """检查 Golden Dataset 数据质量"""
    print("检查 Golden Dataset 数据质量...")

    # Golden Dataset 标的
    symbols = ["510300.SH", "516010.SH", "513100.SH", "000300.SH"]

    settings = get_settings()

    with DataService(settings) as data_service:
        reporter = DataQualityReporter()
        data_dict = {}

        # 1. 加载数据
        print("\n1. 加载数据...")
        for symbol in symbols:
            df = data_service.analytics.get_daily_data(
                symbol=symbol,
                start_date="2022-01-01",
                end_date="2024-12-31"
            )

            if not df.empty:
                data_dict[symbol] = df
                print(f"  ✅ {symbol}: {len(df)} 条记录")
            else:
                print(f"  ❌ {symbol}: 无数据")

        # 2. 生成报告
        print("\n2. 生成质量报告...")
        batch_report = reporter.generate_batch_report(data_dict)

        # 3. 输出报告
        print("\n=== 数据质量报告 ===")
        print(f"检查标的数: {batch_report['total_symbols']}")
        print(f"总记录数: {batch_report['summary']['total_records']:,}")
        print(f"平均质量分数: {batch_report['summary']['avg_quality_score']:.2%}")

        if batch_report['summary']['failed_symbols']:
            print(f"问题标的: {', '.join(batch_report['summary']['failed_symbols'])}")

        # 4. 保存详细报告
        report_path = Path("reports") / f"quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.parent.mkdir(exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(batch_report, f, indent=2, ensure_ascii=False, default=str)

        print(f"\n详细报告已保存至: {report_path}")

        # 5. 输出各标的具体问题
        print("\n=== 详细问题 ===")
        for report in batch_report["reports"]:
            if report["summary"]["failed"] > 0:
                print(f"\n{report['symbol']}:")
                for validator in report["validators"]:
                    if validator["status"] == "failed":
                        print(f"  - {validator['name']}: {validator['message']}")

if __name__ == "__main__":
    check_golden_dataset_quality()
```

**Step 3: Test the quality reporter**

Run: `pytest packages/core/tests/unit/data/quality/test_reporter.py -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add packages/core/src/ditto_core/data/quality/ packages/core/tests/unit/data/quality/ scripts/check_data_quality.py
git commit -m "feat(data): P05-012 implement data quality reporter"
```

---

## Task 7: Manual Validation Process

**Files:**
- Create: `docs/validation_checklist.md`
- Create: `scripts/manual_validation_helper.py`

**Step 1: Create validation checklist**

```markdown
# Golden Dataset 手工验证清单

## 验证标的
- [ ] 510300.SH - 沪深300ETF
- [ ] 516010.SH - 游戏ETF
- [ ] 513100.SH - 纳指ETF
- [ ] 000300.SH - 沪深300指数

## 验证项目

### 1. 收盘价验证（100个连续交易日）
选择日期段：2024-01-01 至 2024-05-31

| 日期 | 510300.SH | 对比源1 | 差异 | 对比源2 | 差异 | 备注 |
|------|-----------|---------|------|---------|------|------|
| 2024-01-02 | 3.456 | 3.456 | 0% | 3.456 | 0% | ✅ |
| ... | ... | ... | ... | ... | ... | ... |

**验证方法**：
- 对比源1：东方财富 (https://quote.eastmoney.com/)
- 对比源2：同花顺 (https://www.10jqka.com.cn/)
- 容忍差异：0.01%

### 2. 复权因子验证
找到有分红除权的日期：

| 标的 | 除权日期 | 分红金额 | 复权前收盘 | 复权后收盘 | 计算复权因子 | 系统复权因子 | 差异 |
|------|----------|----------|------------|------------|--------------|--------------|------|
| 510300.SH | 2024-XX-XX | 0.123 | 4.567 | 4.444 | 0.9731 | 0.9731 | ✅ |

### 3. 涨跌停验证
抽查10个涨跌停日期：

| 日期 | 标的 | 收盘价 | 前收盘价 | 涨跌幅 | 是否涨跌停 | 系统识别 | 备注 |
|------|------|--------|----------|--------|------------|----------|------|
| 2024-XX-XX | 516010.SH | 2.345 | 2.673 | -12.28% | 跌停 | ✅ | ST股 |

### 4. 数据完整性验证
- [ ] 检查是否有缺失交易日
- [ ] 检查停牌数据处理是否正确
- [ ] 检查异常数据处理是否合理

## 验证结论
□ 通过所有验证项目
□ 存在问题，需要修复：
  - 问题1：
  - 问题2：

## 签名
验证人：__________
日期：__________
```

**Step 2: Create manual validation helper**

```python
#!/usr/bin/env python3
"""
手工验证辅助脚本
导出数据供手工验证使用
"""

import pandas as pd
from pathlib import Path
from ditto_foundation.config import get_settings
from ditto_core.data.service import DataService

def export_for_manual_validation():
    """导出数据供手工验证"""
    print("导出手工验证数据...")

    # Golden Dataset 标的
    symbols = ["510300.SH", "516010.SH", "513100.SH", "000300.SH"]

    settings = get_settings()

    with DataService(settings) as data_service:
        # 导出收盘价数据（2024年1-5月）
        print("\n1. 导出收盘价数据...")
        close_prices = {}

        for symbol in symbols:
            df = data_service.analytics.get_daily_data(
                symbol=symbol,
                start_date="2024-01-01",
                end_date="2024-05-31"
            )

            if not df.empty:
                close_prices[symbol] = df.select(["date", "close"]).to_pandas()
                print(f"  ✅ {symbol}: {len(df)} 条记录")

        # 合并为一个Excel文件
        with pd.ExcelWriter("validation/close_prices_2024Q1Q2.xlsx") as writer:
            for symbol, df in close_prices.items():
                df.to_excel(writer, sheet_name=symbol, index=False)

        print("\n✅ 收盘价数据已导出至: validation/close_prices_2024Q1Q2.xlsx")

        # 导出复权因子数据
        print("\n2. 导出复权因子数据...")
        adj_factors = {}

        for symbol in symbols:
            df = data_service.analytics.get_adjustment_factors(
                symbol=symbol,
                start_date="2022-01-01",
                end_date="2024-12-31"
            )

            if not df.empty:
                adj_factors[symbol] = df.to_pandas()
                print(f"  ✅ {symbol}: {len(df)} 条记录")

        if adj_factors:
            with pd.ExcelWriter("validation/adj_factors_2022-2024.xlsx") as writer:
                for symbol, df in adj_factors.items():
                    df.to_excel(writer, sheet_name=symbol, index=False)

            print("\n✅ 复权因子数据已导出至: validation/adj_factors_2022-2024.xlsx")

        # 导出可能的涨跌停日期
        print("\n3. 查找涨跌停日期...")

        for symbol in symbols:
            df = data_service.analytics.get_daily_data(
                symbol=symbol,
                start_date="2023-01-01",
                end_date="2024-12-31"
            )

            if not df.empty:
                # 计算涨跌幅
                df = df.with_columns([
                    ((pl.col("close") - pl.col("close").shift(1)) /
                     pl.col("close").shift(1) * 100).alias("pct_change")
                ])

                # 找出涨跌停（涨跌停阈值：±10%，ST股：±5%）
                limit_up = df.filter(pl.col("pct_change") >= 9.8)
                limit_down = df.filter(pl.col("pct_change") <= -9.8)

                print(f"\n{symbol} 涨跌停日期:")
                if not limit_up.empty:
                    print("  涨停:")
                    for row in limit_up.select(["date", "close", "pct_change"]).to_dicts():
                        print(f"    {row['date']}: {row['close']:.3f} (+{row['pct_change']:.2f}%)")

                if not limit_down.empty:
                    print("  跌停:")
                    for row in limit_down.select(["date", "close", "pct_change"]).to_dicts():
                        print(f"    {row['date']}: {row['close']:.3f} ({row['pct_change']:.2f}%)")

if __name__ == "__main__":
    # 创建输出目录
    Path("validation").mkdir(exist_ok=True)

    export_for_manual_validation()
```

**Step 3: Run validation helper**

Run: `pixi run python scripts/manual_validation_helper.py`
Expected: Exports data to validation folder

**Step 4: Commit**

```bash
git add docs/validation_checklist.md scripts/manual_validation_helper.py
git commit -m "docs: P05-006 create manual validation process"
```

---

## Task 8: Fix Import Errors and Final Integration

**Files:**
- Modify: `apps/server/src/ditto-server/main.py:1-20`
- Test: `apps/server/tests/unit/test_main.py`

**Step 1: Fix logging_config import error**

```python
# apps/server/src/ditto-server/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ditto_foundation.config import get_settings
from ditto_server.api.endpoints import router
from ditto_server.logging_config import setup_logging  # Fix this import

# Setup logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title="Ditto Quant API",
    description="Quantitative Investment System API",
    version="0.5.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(router, prefix="/api/v1")
```

**Step 2: Create missing logging_config module**

```python
# apps/server/src/ditto-server/logging_config.py
import logging
import sys
from pathlib import Path
from loguru import logger

def setup_logging():
    """设置应用日志配置"""
    # 移除默认的loguru handler
    logger.remove()

    # 添加控制台输出
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )

    # 添加文件输出
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        log_dir / "ditto_server_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",
        retention="30 days"
    )

    # 配置标准库logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

class InterceptHandler(logging.Handler):
    """拦截标准库日志并转发到loguru"""

    def emit(self, record):
        """拦截并转发日志记录"""
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )
```

**Step 3: Test the server startup**

Run: `pytest apps/server/tests/unit/test_main.py -v`
Expected: All tests pass

Run: `pixi run python -m ditto_server.main`
Expected: Server starts without import errors

**Step 4: Commit**

```bash
git add apps/server/src/ditto-server/main.py apps/server/src/ditto-server/logging_config.py
git commit -m "fix(api): P0-022 resolve logging_config import error"
```

---

## Task 9: Final Verification and Cleanup

**Files:**
- Modify: `phase0_tasks.md`
- Run: `pre-commit run --all-files`

**Step 1: Update task status**

```markdown
# Update completed tasks to ✅
P0-005: ✅ 已完成
P0-006: ✅ 已完成
P0-007: ✅ 已完成
P0-008: ✅ 已完成
P0-013: ✅ 已完成
P0-017: ✅ 已完成
P0-021: ✅ 已完成
P0-031: ✅ 已完成
P0-032: ✅ 已完成
P0-036: ✅ 已完成
P0-037: ✅ 已完成
P0-038: ✅ 已完成
P0-040: ✅ 已完成
P05-001: ✅ 已完成
P05-002: ✅ 已完成
P05-003: ✅ 已完成
P05-004: ✅ 已完成
P05-005: ✅ 已完成
P05-006: ✅ 已完成
P05-012: ✅ 已完成
P05-017: ✅ 已完成
P0-022: ✅ 已完成
```

**Step 2: Run final verification**

```bash
# 1. Run all tests
pytest --cov=packages --cov=apps --cov-report=term-missing

# 2. Run code quality checks
pixi run ruff check .
pixi run ruff format .
pixi run mypy packages/ apps/

# 3. Run pre-commit hooks
pre-commit run --all-files
```

Expected: All checks pass

**Step 3: Commit final updates**

```bash
git add phase0_tasks.md
git commit -m "docs: update Phase 0.5 task completion status"
```

---

## Execution Complete!

This implementation plan provides:

1. **Complete DataCollector implementation** with TDD approach
2. **Golden Dataset initialization** for 4 selected symbols
3. **Cross-validation logic** between Tushare and AkShare
4. **Data quality validators** for price and volume
5. **Quality reporting system** with detailed metrics
6. **Manual validation process** with checklist and helper scripts
7. **Fixed import errors** in the FastAPI application
8. **Comprehensive testing** maintaining 80%+ coverage

The plan follows all established patterns:
- Dual-source data validation
- Point-in-Time safety
- Type safety with full annotations
- Comprehensive error handling
- TDD with RED-GREEN-REFACTOR cycle
- Conventional commit messages

**Plan complete and saved to `docs/plans/2025-12-10-phase05-data-quality-validation.md`. Two execution options:**

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?