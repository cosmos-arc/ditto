"""复权因子验证模块."""

from dataclasses import dataclass
from datetime import date
from typing import Any

import polars as pl


@dataclass
class ValidationResult:
    """验证结果."""

    symbol: str
    is_valid: bool
    issues: list[str]
    cumulative_factor: float | None = None
    factor_stats: dict[str, float] | None = None
    expected_cumulative_factor: float | None = None

    def __contains__(self, key: str) -> bool:
        """支持 in 操作符."""
        return hasattr(self, key) or key in self.__dataclass_fields__

    def __getitem__(self, key: str) -> Any:
        """支持字典访问."""
        if hasattr(self, key) or key in self.__dataclass_fields__:
            return getattr(self, key)
        else:
            raise KeyError(f"Key '{key}' not found in ValidationResult")


@dataclass
class ValidationReport:
    """验证报告."""

    summary: dict[str, Any]
    details: dict[str, ValidationResult]
    generated_at: str

    def __contains__(self, key: str) -> bool:
        """支持 in 操作符."""
        return hasattr(self, key) or key in self.__dataclass_fields__

    def __getitem__(self, key: str) -> Any:
        """支持字典访问."""
        if hasattr(self, key) or key in self.__dataclass_fields__:
            return getattr(self, key)
        else:
            raise KeyError(f"Key '{key}' not found in ValidationReport")


class AdjustmentFactorValidator:
    """复权因子验证器."""

    def __init__(self) -> None:
        """初始化验证器."""
        self.tolerance = 0.001  # 浮点数比较容差
        self.min_factor = 0.1  # 最小复权因子
        self.max_factor = 3.0  # 最大复权因子

    def validate_adjustment_factors(
        self, symbol: str, adjustment_data: list[dict[str, Any]]
    ) -> ValidationResult:
        """
        验证单个股票的复权因子数据.

        Args:
            symbol: 股票代码
            adjustment_data: 复权因子数据列表

        Returns:
            ValidationResult: 验证结果

        """
        issues = []

        if not adjustment_data:
            return ValidationResult(
                symbol=symbol, is_valid=False, issues=["No adjustment data"]
            )

        # 转换为DataFrame以便处理
        df = pl.DataFrame(adjustment_data)

        # 1. 检查必要的字段
        required_fields = ["symbol", "date", "adj_factor"]
        missing_fields = [f for f in required_fields if f not in df.columns]
        if missing_fields:
            issues.append(f"Missing required fields: {missing_fields}")
            return ValidationResult(symbol=symbol, is_valid=False, issues=issues)

        # 2. 按日期排序
        df = df.sort("date")

        # 3. 计算统计信息
        factor_stats = self._calculate_statistics(adjustment_data)

        # 4. 检查极端值
        if (
            factor_stats["min"] < self.min_factor
            or factor_stats["max"] > self.max_factor
        ):
            issues.append(
                f"Extreme adjustment factors: min={factor_stats['min']:.4f}, "
                f"max={factor_stats['max']:.4f}"
            )

        # 5. 检测复权类型的一致性
        if "adj_type" in df.columns:
            issues.extend(self._validate_adjustment_types(df))

        # 6. 检测缺失的分红单记录
        if "adj_type" in df.columns:
            missing_dividend_issues = self._detect_missing_dividend_records(df)
            issues.extend(missing_dividend_issues)

        # 7. 检测累积因子的一致性
        cumulative_issue = self._validate_cumulative_factors(df)
        expected_cumulative_factor = None

        if cumulative_issue:
            issues.extend(cumulative_issue)
            # 如果检测到不一致, 期望的累积因子应该是第一个连续记录的因子
            continuation_records = df.filter(pl.col("adj_type").is_null())
            if continuation_records.height > 0:
                expected_cumulative_factor = float(
                    continuation_records["adj_factor"].to_list()[0]
                )

        # 8. 计算最终累积因子
        cumulative_factor = self._calculate_cumulative_factor(df)

        # 9. 检测缺失的日期(如果提供了日期范围)
        if len(adjustment_data) > 1:
            date_issues = self._detect_date_gaps(df)
            issues.extend(date_issues)

        return ValidationResult(
            symbol=symbol,
            is_valid=len(issues) == 0,
            issues=issues,
            cumulative_factor=cumulative_factor,
            factor_stats=factor_stats,
            expected_cumulative_factor=expected_cumulative_factor,
        )

    def generate_validation_report(
        self, symbols_data: dict[str, list[dict[str, Any]]]
    ) -> ValidationReport:
        """
        生成验证报告.

        Args:
            symbols_data: 多个股票的复权因子数据

        Returns:
            ValidationReport: 验证报告

        """
        from datetime import datetime

        details = {}
        valid_count = 0
        total_count = len(symbols_data)

        for symbol, data in symbols_data.items():
            result = self.validate_adjustment_factors(symbol, data)
            details[symbol] = result
            if result.is_valid:
                valid_count += 1

        summary = {
            "total_symbols": total_count,
            "valid_symbols": valid_count,
            "invalid_symbols": total_count - valid_count,
            "validation_rate": valid_count / total_count if total_count > 0 else 0,
        }

        return ValidationReport(
            summary=summary,
            details=details,
            generated_at=datetime.now().isoformat(),
        )

    def batch_validate(
        self, symbols_data: dict[str, list[dict[str, Any]]]
    ) -> dict[str, ValidationResult]:
        """批量验证多个股票."""
        results = {}
        for symbol, data in symbols_data.items():
            result = self.validate_adjustment_factors(symbol, data)
            results[symbol] = result
        return results

    def _calculate_statistics(self, data: list[dict[str, Any]]) -> dict[str, float]:
        """计算复权因子的统计信息."""
        factors = [d["adj_factor"] for d in data if "adj_factor" in d]

        if not factors:
            return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0, "std": 0.0}

        import numpy as np

        return {
            "count": len(factors),
            "mean": float(np.mean(factors)),
            "min": float(np.min(factors)),
            "max": float(np.max(factors)),
            "std": float(np.std(factors)),
        }

    def _detect_missing_dates(
        self,
        symbol: str,
        data: list[dict[str, Any]],
        expected_dates: list[date],
    ) -> list[str]:
        """检测缺失的日期记录."""
        issues = []

        # 创建已有日期的集合
        existing_dates = set()
        for item in data:
            if "date" in item:
                if isinstance(item["date"], str):
                    try:
                        existing_dates.add(date.fromisoformat(item["date"]))
                    except ValueError:
                        continue
                elif isinstance(item["date"], date):
                    existing_dates.add(item["date"])

        # 检查哪些预期日期缺失
        for expected_date in expected_dates:
            if expected_date not in existing_dates:
                issues.append(f"Missing data for {symbol} on {expected_date}")

        return issues

    def _validate_date_sequence(self, data: list[dict[str, Any]]) -> list[str]:
        """验证日期序列的连续性."""
        issues = []

        if len(data) < 2:
            return issues

        # 按日期排序
        sorted_data = sorted(data, key=lambda x: x.get("date", ""))

        dates = []
        for item in sorted_data:
            d = item.get("date")
            if isinstance(d, str):
                try:
                    dates.append(date.fromisoformat(d))
                except ValueError:
                    continue
            elif isinstance(d, date):
                dates.append(d)

        # 检查日期间隔
        for i in range(1, len(dates)):
            date_diff = (dates[i] - dates[i - 1]).days
            if date_diff > 1:  # 超过1天可能是数据缺失(跳过周末)
                issues.append(
                    f"Date gap detected: {dates[i - 1]} to {dates[i]} "
                    f"({date_diff} days)"
                )

        return issues

    def _detect_missing_dividend_records(self, df: pl.DataFrame) -> list[str]:
        """检测缺失的分红单记录."""
        issues = []

        # 查找因子发生变化但没有对应事件记录的情况
        records = df.sort("date").iter_rows(named=True)

        prev_adj_type = None
        prev_factor = None

        for i, row in enumerate(records):
            curr_adj_type = row["adj_type"]
            curr_factor = row["adj_factor"]

            # 跳过第一条记录
            if i > 0 and prev_factor is not None:
                factor_change = abs(curr_factor - prev_factor)

                # 如果因子发生显著变化
                if factor_change > 0.001:
                    # 情况1: 前一条没有事件, 当前也没有事件, 但因子变了
                    if prev_adj_type is None and curr_adj_type is None:
                        issues.append(
                            f"Missing dividend record: factor changed from "
                            f"{prev_factor} to {curr_factor} without event"
                        )
                    # 情况2: 因子变化发生, 但事件记录在后面
                    elif curr_adj_type is not None and prev_adj_type is None:
                        # 检查是否是合理的因子变化(分红通常会导致因子变大)
                        if curr_factor > prev_factor:
                            issues.append(
                                f"Missing dividend record detected: "
                                f"factor increased from {prev_factor} to {curr_factor}"
                            )

            prev_adj_type = curr_adj_type
            prev_factor = curr_factor

        return issues

    def _validate_adjustment_types(self, df: pl.DataFrame) -> list[str]:
        """验证复权类型的一致性."""
        issues = []

        # 检查是否有adj_type但某些记录缺失
        has_type_column = "adj_type" in df.columns
        type_null_count = df.filter(pl.col("adj_type").is_null()).height

        if has_type_column and type_null_count > 0:
            # 如果adj_type列存在, 检查类型变化时的记录
            for row in df.iter_rows(named=True):
                if row["adj_type"] is not None:
                    # 这是一个有类型的记录, 检查之前是否应该有记录但缺失
                    break
            # 这里简化处理, 实际应该更严格地检查
        elif not has_type_column:
            # 没有adj_type列, 可能是历史数据
            pass

        return issues

    def _validate_cumulative_factors(self, df: pl.DataFrame) -> list[str]:
        """验证累积因子的一致性."""
        issues = []

        # 按日期排序
        sorted_df = df.sort("date")

        # 查找连续记录段, 这些记录之间的因子应该一致
        # 跳过事件记录
        continuation_records = []
        for row in sorted_df.iter_rows(named=True):
            if row["adj_type"] is None:
                # 这是连续记录
                continuation_records.append(row)
            else:
                # 遇到事件记录, 检查之前的连续记录是否一致
                if len(continuation_records) > 1:
                    factors = [r["adj_factor"] for r in continuation_records]
                    if len(set(factors)) > 1:
                        issues.append(
                            f"Inconsistent factors within continuation period: "
                            f"{set(factors)}"
                        )
                # 重置连续记录
                continuation_records = []

        # 检查最后一段连续记录
        if len(continuation_records) > 1:
            factors = [r["adj_factor"] for r in continuation_records]
            if len(set(factors)) > 1:
                issues.append(f"Inconsistent factors at end of data: {set(factors)}")

        return issues

    def _calculate_cumulative_factor(self, df: pl.DataFrame) -> float:
        """计算最终的累积复权因子."""
        if df.is_empty():
            return 1.0

        # 按日期排序
        sorted_df = df.sort("date")

        # 获取所有记录(包括事件和连续记录)
        # 累积因子应该是最后一条记录的 adj_factor
        if sorted_df.height > 0:
            last_record = sorted_df.row(sorted_df.height - 1, named=True)
            return float(last_record["adj_factor"])

        return 1.0

    def _detect_date_gaps(self, df: pl.DataFrame) -> list[str]:
        """检测日期间隔."""
        issues = []

        if df.height < 2:
            return issues

        # 转换日期字符串为date对象
        dates = []
        for d in df["date"].to_list():
            if isinstance(d, str):
                try:
                    dates.append(date.fromisoformat(d))
                except ValueError:
                    continue
            elif isinstance(d, date):
                dates.append(d)

        for i in range(1, len(dates)):
            prev_date = dates[i - 1]
            curr_date = dates[i]

            # 计算日期差
            date_diff = (curr_date - prev_date).days
            if date_diff > 1:
                # 跳过了非交易日
                issues.append(
                    f"Date gap detected: {prev_date} to {curr_date} ({date_diff} days)"
                )

        return issues
