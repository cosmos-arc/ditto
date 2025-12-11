"""涨跌停识别准确率验证模块."""

from dataclasses import dataclass
from datetime import date
from typing import Any

import polars as pl


@dataclass
class AccuracyMetrics:
    """准确率指标."""

    total_samples: int
    true_positives: int  # 正确识别的涨跌停
    false_positives: int  # 错误识别为涨跌停
    true_negatives: int  # 正确识别为非涨跌停
    false_negatives: int  # 漏掉的涨跌停

    precision: float | None = None  # 精确率 = TP / (TP + FP)
    recall: float | None = None  # 召回率 = TP / (TP + FN)
    f1_score: float | None = None  # F1分数: harmonic mean of precision and recall
    accuracy: float | None = None  # 准确率 = (TP + TN) / (TP + TN + FP + FN)

    def __post_init__(self) -> None:
        """自动计算指标."""
        total = (
            self.true_positives
            + self.false_positives
            + self.true_negatives
            + self.false_negatives
        )
        if total != self.total_samples:
            self.total_samples = total

        self.precision = (
            self.true_positives / (self.true_positives + self.false_positives)
            if (self.true_positives + self.false_positives) > 0
            else 0.0
        )
        self.recall = (
            self.true_positives / (self.true_positives + self.false_negatives)
            if (self.true_positives + self.false_negatives) > 0
            else 0.0
        )
        self.f1_score = (
            2 * (self.precision * self.recall) / (self.precision + self.recall)
            if (self.precision + self.recall) > 0
            else 0.0
        )
        self.accuracy = (
            (self.true_positives + self.true_negatives) / self.total_samples
            if self.total_samples > 0
            else 0.0
        )


@dataclass
class AccuracyReport:
    """准确率报告."""

    symbol: str
    date_range: tuple[date, date]
    limit_up_metrics: AccuracyMetrics
    limit_down_metrics: AccuracyMetrics
    overall_metrics: AccuracyMetrics
    detailed_results: list[dict[str, Any]]


class LimitAccuracyValidator:
    """涨跌停识别准确率验证器."""

    def __init__(self) -> None:
        """初始化验证器."""
        self.tolerance = 0.001  # 浮点数比较容差

    def validate_accuracy(
        self,
        symbol: str,
        predicted_data: list[dict[str, Any]],
        actual_data: list[dict[str, Any]],
    ) -> AccuracyReport:
        """
        验证涨跌停识别的准确率.

        Args:
            symbol: 股票代码
            predicted_data: 预测的涨跌停数据(包含 is_limit_up, is_limit_down 字段)
            actual_data: 实际的涨跌停数据(包含 actual_limit_up, actual_limit_down 字段)

        Returns:
            AccuracyReport: 准确率报告

        """
        # 转换为DataFrame
        pred_df = pl.DataFrame(predicted_data)
        actual_df = pl.DataFrame(actual_data)

        # 合并数据
        merged_df = self._merge_data(pred_df, actual_df)

        # 计算指标
        limit_up_metrics = self._calculate_metrics(
            merged_df, "is_limit_up", "actual_limit_up"
        )

        limit_down_metrics = self._calculate_metrics(
            merged_df, "is_limit_down", "actual_limit_down"
        )

        # 计算总体指标
        overall_metrics = self._calculate_overall_metrics(
            limit_up_metrics, limit_down_metrics
        )

        # 获取日期范围
        if merged_df.height > 0:
            dates = [d for d in merged_df["date"].to_list() if d is not None]
            if dates:
                date_range = (min(dates), max(dates))
            else:
                date_range = (date.min, date.max)
        else:
            date_range = (date.min, date.max)

        # 生成详细结果
        detailed_results = self._generate_detailed_results(merged_df)

        return AccuracyReport(
            symbol=symbol,
            date_range=date_range,
            limit_up_metrics=limit_up_metrics,
            limit_down_metrics=limit_down_metrics,
            overall_metrics=overall_metrics,
            detailed_results=detailed_results,
        )

    def batch_validate_accuracy(
        self,
        symbols_data: dict[str, dict[str, list[dict[str, Any]]]],
    ) -> dict[str, AccuracyReport]:
        """
        批量验证多个股票的涨跌停识别准确率.

        Args:
            symbols_data: 格式为 {symbol: {"predicted": [...], "actual": [...]}}

        Returns:
            dict[str, AccuracyReport]: 每个股票的准确率报告

        """
        reports = {}

        for symbol, data in symbols_data.items():
            predicted = data.get("predicted", [])
            actual = data.get("actual", [])

            report = self.validate_accuracy(symbol, predicted, actual)
            reports[symbol] = report

        return reports

    def _merge_data(
        self, pred_df: pl.DataFrame, actual_df: pl.DataFrame
    ) -> pl.DataFrame:
        """合并预测数据和实际数据."""
        # 处理空数据情况
        if pred_df.height == 0 and actual_df.height == 0:
            return pl.DataFrame(
                schema={
                    "date": pl.Date,
                    "is_limit_up": pl.Boolean,
                    "is_limit_down": pl.Boolean,
                    "actual_limit_up": pl.Boolean,
                    "actual_limit_down": pl.Boolean,
                }
            )

        # 按日期连接
        merged = pred_df.join(actual_df, on="date", how="outer", suffix="_actual")

        # 填充缺失值
        merged = merged.with_columns(
            [
                pl.col("is_limit_up").fill_null(False),
                pl.col("is_limit_down").fill_null(False),
                pl.col("actual_limit_up").fill_null(False),
                pl.col("actual_limit_down").fill_null(False),
            ]
        )

        return merged.sort("date")

    def _calculate_metrics(
        self, df: pl.DataFrame, pred_col: str, actual_col: str
    ) -> AccuracyMetrics:
        """计算涨跌停识别的准确率指标."""
        # 获取预测和实际的布尔值
        predicted = df[pred_col].to_list()
        actual = df[actual_col].to_list()

        # 计算混淆矩阵
        tp = sum(p and a for p, a in zip(predicted, actual, strict=False))
        fp = sum(p and not a for p, a in zip(predicted, actual, strict=False))
        tn = sum(not p and not a for p, a in zip(predicted, actual, strict=False))
        fn = sum(not p and a for p, a in zip(predicted, actual, strict=False))

        total = tp + fp + tn + fn

        return AccuracyMetrics(
            total_samples=total,
            true_positives=tp,
            false_positives=fp,
            true_negatives=tn,
            false_negatives=fn,
        )

    def _calculate_overall_metrics(
        self, limit_up: AccuracyMetrics, limit_down: AccuracyMetrics
    ) -> AccuracyMetrics:
        """计算总体指标."""
        # 合并涨停和跌停的指标
        total_samples = limit_up.total_samples + limit_down.total_samples
        true_positives = limit_up.true_positives + limit_down.true_positives
        false_positives = limit_up.false_positives + limit_down.false_positives
        true_negatives = limit_up.true_negatives + limit_down.true_negatives
        false_negatives = limit_up.false_negatives + limit_down.false_negatives

        return AccuracyMetrics(
            total_samples=total_samples,
            true_positives=true_positives,
            false_positives=false_positives,
            true_negatives=true_negatives,
            false_negatives=false_negatives,
        )

    def _generate_detailed_results(self, df: pl.DataFrame) -> list[dict[str, Any]]:
        """生成详细的结果列表."""
        results = []

        for row in df.iter_rows(named=True):
            result = {
                "date": row["date"],
                "predicted_limit_up": row["is_limit_up"],
                "predicted_limit_down": row["is_limit_down"],
                "actual_limit_up": row["actual_limit_up"],
                "actual_limit_down": row["actual_limit_down"],
                "is_correct_limit_up": (row["is_limit_up"] == row["actual_limit_up"]),
                "is_correct_limit_down": (
                    row["is_limit_down"] == row["actual_limit_down"]
                ),
            }
            results.append(result)

        return results

    def generate_summary_report(
        self, reports: dict[str, AccuracyReport]
    ) -> dict[str, Any]:
        """生成汇总报告."""
        if not reports:
            return {"message": "No reports available"}

        # 计算平均指标
        total_samples = sum(r.overall_metrics.total_samples for r in reports.values())
        total_tp = sum(r.overall_metrics.true_positives for r in reports.values())
        total_fp = sum(r.overall_metrics.false_positives for r in reports.values())
        total_tn = sum(r.overall_metrics.true_negatives for r in reports.values())
        total_fn = sum(r.overall_metrics.false_negatives for r in reports.values())

        # 计算平均指标
        avg_precision = (
            sum(r.overall_metrics.precision for r in reports.values()) / len(reports)
            if reports
            else 0.0
        )
        avg_recall = (
            sum(r.overall_metrics.recall for r in reports.values()) / len(reports)
            if reports
            else 0.0
        )
        avg_f1 = (
            sum(r.overall_metrics.f1_score for r in reports.values()) / len(reports)
            if reports
            else 0.0
        )
        avg_accuracy = (
            sum(r.overall_metrics.accuracy for r in reports.values()) / len(reports)
            if reports
            else 0.0
        )

        # 找出表现最好和最差的股票
        best_accuracy = max(
            reports.items(), key=lambda x: x[1].overall_metrics.accuracy
        )
        worst_accuracy = min(
            reports.items(), key=lambda x: x[1].overall_metrics.accuracy
        )

        return {
            "total_symbols": len(reports),
            "total_samples": total_samples,
            "average_precision": avg_precision,
            "average_recall": avg_recall,
            "average_f1_score": avg_f1,
            "average_accuracy": avg_accuracy,
            "best_performing_symbol": {
                "symbol": best_accuracy[0],
                "accuracy": best_accuracy[1].overall_metrics.accuracy,
            },
            "worst_performing_symbol": {
                "symbol": worst_accuracy[0],
                "accuracy": worst_accuracy[1].overall_metrics.accuracy,
            },
            "detailed_reports": reports,
        }
