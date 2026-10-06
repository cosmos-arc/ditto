"""L3 Statistical checker."""

from typing import Any

import polars as pl
import polars.exceptions as pl_exceptions
from ditto_platform.foundation import logger

from ditto_data.quality.quality_types import DQIssue, DQLevel, DQSeverity


class StatisticalChecker:
    """L3 statistical anomaly checker (pure functional)."""

    def check(
        self,
        current: pl.DataFrame,
        historical: pl.DataFrame | None = None,
        calendar: pl.DataFrame | None = None,
        rules: list[dict[str, Any]] | None = None,
        reference: pl.DataFrame | None = None,
    ) -> list[DQIssue]:
        """
        Execute L3 statistical checks.

        Args:
            current: Current data to check
            historical: Historical data for statistical calculations
                (optional, for zscore)
            calendar: Trading calendar (optional, for completeness check)
            rules: List of L3 rule configurations
            reference: Companion-dataset frame for cross-dataset
                consistency rules (optional, e.g. stock_status for
                suspension_contradiction)

        Returns:
            List of DQIssue (ALERT severity)

        """
        if not rules:
            return []

        issues: list[DQIssue] = []

        for rule in rules:
            issue = self._check_rule(current, historical, calendar, rule, reference)
            if issue:
                issues.append(issue)

        return issues

    def _check_rule(
        self,
        current: pl.DataFrame,
        historical: pl.DataFrame | None,
        calendar: pl.DataFrame | None,
        rule: dict[str, Any],
        reference: pl.DataFrame | None = None,
    ) -> DQIssue | None:
        """
        Check a single rule.

        Args:
            current: Current data to check
            historical: Historical data for statistical calculations
            calendar: Trading calendar
            rule: Rule configuration
            reference: Companion-dataset frame (consistency rules)

        Returns:
            DQIssue if rule violated, None otherwise

        """
        rule_type = rule.get("rule")

        if rule_type == "zscore":
            return self._check_zscore(current, historical, rule)
        elif rule_type == "completeness":
            return self._check_completeness(current, historical, calendar, rule)
        elif rule_type == "suspension_contradiction":
            return self._check_suspension_contradiction(current, reference)

        return None

    def _check_zscore(
        self,
        current: pl.DataFrame,
        historical: pl.DataFrame | None,
        rule: dict[str, Any],
    ) -> DQIssue | None:
        """
        Check Z-score anomaly.

        Args:
            current: Current data to check (must contain columns to analyze)
            historical: Historical data for calculating statistics
                (must include same columns)
            rule: Rule config with column, window, threshold, group_by

        Returns:
            DQIssue if anomaly detected, None otherwise

        """
        column = rule.get("column")
        threshold = rule.get("threshold", 3.0)
        group_by = rule.get("group_by")

        if not column:
            return None

        if historical is None or historical.is_empty():
            logger.debug(
                "dq_zscore_no_historical",
                event="dq_check",
                column=column,
            )
            return None

        if current.is_empty() or column not in current.columns:
            return None

        try:
            # Prepare working data
            df = current.clone()

            # Calculate statistics by group or overall
            if group_by:
                stats = historical.group_by(group_by).agg(
                    pl.col(column).mean().alias("mean"),
                    pl.col(column).std().alias("std"),
                )
                # Join stats to current data
                df = df.join(stats, on=group_by, how="left")
            else:
                mean_val = historical[column].mean()
                std_val = historical[column].std()
                df = df.with_columns(
                    pl.lit(mean_val).alias("mean"),
                    pl.lit(std_val).alias("std"),
                )

            # Calculate Z-score
            df = df.with_columns(
                ((pl.col(column) - pl.col("mean")) / pl.col("std")).alias("zscore")
            )

            # Find anomalies
            anomalies = df.filter(
                pl.col("zscore").is_finite() & (pl.col("zscore").abs() > threshold)
            )

            if anomalies.height > 0:
                logger.warning(
                    "dq_rule_zscore_anomaly",
                    event="dq_check",
                    column=column,
                    anomaly_count=anomalies.height,
                    threshold=threshold,
                )
                msg = (
                    f"Found {anomalies.height} Z-score anomalies in "
                    f"'{column}' (threshold: {threshold})"
                )
                return DQIssue(
                    level=DQLevel.STATISTICAL,
                    severity=DQSeverity.ALERT,
                    rule_name="zscore",
                    message=msg,
                    affected_rows=anomalies.height,
                    sample_data=anomalies.select(["instrument_id", column, "zscore"])
                    .head(10)
                    .to_dicts(),
                )

        except (
            pl_exceptions.ComputeError,
            pl_exceptions.SchemaError,
            pl_exceptions.ColumnNotFoundError,
        ) as e:
            # Polars 相关错误 - ALERT 级别
            logger.exception(
                "dq_zscore_computation_failed",
                error_type=type(e).__name__,
                column=column,
                rule_type="zscore",
            )
            exc_type = type(e).__name__
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="zscore",
                message=f"Z-score check failed for column '{column}': {exc_type}",
                affected_rows=0,
                sample_data=[],
            )
        except ValueError as e:
            # 数值错误（如除零）- WARNING 级别
            logger.warning(
                "dq_zscore_invalid_value",
                error=str(e),
                column=column,
                rule_type="zscore",
            )
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.WARNING,
                rule_name="zscore",
                message=f"Invalid statistical value for '{column}': {e}",
                affected_rows=0,
                sample_data=[],
            )

    @staticmethod
    def _instrument_date_gaps(
        frame: pl.DataFrame,
        expected_set: set[str],
    ) -> dict[str, list[str]]:
        """
        Per-instrument date-coverage gaps（#511）.

        期望集 = 该标的首见日期之后的开市日（避免上市前/窗口前段误报）。
        帧内完全缺席的标的不在检测面内（需要 universe 期望清单接线）。
        """
        gaps: dict[str, list[str]] = {}
        per_instrument = frame.group_by("instrument_id").agg(
            pl.col("trade_date").cast(str).unique().sort()
        )
        for instrument_id, inst_dates in per_instrument.iter_rows():
            inst_set = set(inst_dates)
            first_seen = min(inst_set)
            expected_for_inst = {d for d in expected_set if d >= first_seen}
            instrument_gaps = sorted(expected_for_inst - inst_set)
            if instrument_gaps:
                gaps[str(instrument_id)] = instrument_gaps
        return gaps

    def _check_suspension_contradiction(
        self,
        current: pl.DataFrame,
        reference: pl.DataFrame | None,
    ) -> DQIssue | None:
        """
        Check daily×stock_status contradiction（#507 C1，#1797 实测形态）.

        矛盾行 = 同 (instrument_id, trade_date) 上 ``is_suspended=True`` 但
        日线 ``volume > 0``（停牌却成交）。上游两接口独立更新、无裁决字段，
        本检查只告警不裁决（哪侧正确需人工判定）。

        ``reference`` 缺失/为空时跳过（stock_status 未摄取的日子无法检查，
        不视为通过也不告警）；``is_suspended`` 为 null 的行不参与
        （suspend_d 空响应≠无停牌，null 不是 False 的证明）。

        Args:
            current: 当日 stock_daily 行（patrol 单日 current 帧）
            reference: 同日 stock_status 行（is_suspended 列）

        Returns:
            DQIssue if contradiction rows detected, None otherwise

        """
        if reference is None or reference.is_empty():
            logger.debug(
                "dq_suspension_contradiction_no_reference",
                event="dq_check",
            )
            return None
        required_reference = {"instrument_id", "trade_date", "is_suspended"}
        if (
            not required_reference.issubset(reference.columns)
            or "volume" not in current.columns
            or current.is_empty()
        ):
            logger.debug(
                "dq_suspension_contradiction_schema_mismatch",
                event="dq_check",
            )
            return None

        try:
            # 两侧键先去重：伴生帧重复键会把行数按笛卡尔积放大告警计数
            # （stock_status 无 unique L1 断言，不能假设键唯一）。
            contradictions = (
                current.select("instrument_id", "trade_date", "volume")
                .with_columns(pl.col("trade_date").cast(pl.String))
                .unique(subset=["instrument_id", "trade_date"])
                .join(
                    reference.select("instrument_id", "trade_date", "is_suspended")
                    .with_columns(pl.col("trade_date").cast(pl.String))
                    .unique(subset=["instrument_id", "trade_date"]),
                    on=["instrument_id", "trade_date"],
                    how="inner",
                )
                .filter(pl.col("is_suspended") & (pl.col("volume") > 0))
            )
        # PolarsError 基类：dtype 漂移（如 is_suspended 变 String）抛
        # InvalidOperationError，与 ComputeError/SchemaError 是兄弟类——
        # 围栏必须兜住全部 polars 计算错误，否则击穿到 patrol 会拖垮当日
        # stock_daily 的其他 L3 规则（#515 correctness F2）。
        except pl_exceptions.PolarsError as e:
            logger.exception(
                "dq_suspension_contradiction_check_failed",
                error_type=type(e).__name__,
                rule_type="suspension_contradiction",
            )
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="suspension_contradiction",
                message=(f"Suspension contradiction check failed: {type(e).__name__}"),
                affected_rows=0,
                sample_data=[],
            )

        if contradictions.is_empty():
            return None

        sample = sorted(
            f"{inst}@{day}"
            for inst, day in contradictions.select(
                "instrument_id", "trade_date"
            ).iter_rows()
        )
        logger.warning(
            "dq_rule_suspension_contradiction",
            event="dq_check",
            contradiction_count=contradictions.height,
            sample=sample[:10],
        )
        msg = (
            f"Suspension contradiction: {contradictions.height} row(s) with "
            + "is_suspended=True but volume>0 (daily vs suspend_d, #1797); "
            + f"sample: {sample[:5]}"
        )
        return DQIssue(
            level=DQLevel.STATISTICAL,
            severity=DQSeverity.ALERT,
            rule_name="suspension_contradiction",
            message=msg,
            affected_rows=contradictions.height,
            sample_data=contradictions.head(10).to_dicts(),
        )

    def _check_completeness(
        self,
        current: pl.DataFrame,
        historical: pl.DataFrame | None,
        calendar: pl.DataFrame | None,
        rule: dict[str, Any],
    ) -> DQIssue | None:
        """
        Check data completeness.

        规则键（#511）：

        - ``frame: historical`` —— 用存量窗口帧（patrol 的 historical，
          ~120 交易日）替代单日 ``current`` 做日期比对。此前 patrol 只喂
          单日 current 却对 ~10 个交易日历求差，结构性常误报；存量窗口
          才是 completeness 的正确语义（覆盖缺口 vs 已存数据）。
        - ``group_by_instrument: true`` —— 增加 per-instrument 维度：
          对帧内每个标的，以其首见日期起的开市日为期望集，检测单标的
          缺行（#1861 单指数缺口形态）。帧内完全缺席的标的不在检测面
          内（需要 universe 期望清单接线，见 #511 票评论边界）。

        规则键 ``lookback_days`` 本检查器不消费（遗留键）：期望集窗口
        由调用方传入的 calendar 帧决定（patrol 取 ~10 个开市日）。

        Args:
            current: Current data (must contain 'trade_date' column)
            historical: Stored window frame (patrol ~120 trade days)
            calendar: Trading calendar (must contain 'trade_date' and 'is_open' columns)
            rule: Rule config with lookback_days / frame / group_by_instrument

        Returns:
            DQIssue if missing data detected, None otherwise

        """
        if calendar is None or calendar.is_empty():
            logger.debug(
                "dq_completeness_no_calendar",
                event="dq_check",
            )
            return None

        frame = historical if rule.get("frame") == "historical" else current
        if frame is None or frame.is_empty():
            msg = "No data found for completeness check"
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="completeness",
                message=msg,
                affected_rows=0,
            )

        try:
            # Get expected trading days (open days only)
            expected_set = set(
                calendar.filter(pl.col("is_open"))["trade_date"].cast(str).to_list()
            )

            # Get actual data dates
            actual_dates = set(frame["trade_date"].cast(str).unique().to_list())

            # Check for missing dates
            missing_dates = expected_set - actual_dates

            # Per-instrument date coverage (group_by_instrument, #511)
            instrument_gaps: dict[str, list[str]] = {}
            if rule.get("group_by_instrument") and "instrument_id" in frame.columns:
                instrument_gaps = self._instrument_date_gaps(frame, expected_set)

            if missing_dates or instrument_gaps:
                parts: list[str] = []
                affected = len(missing_dates)
                if missing_dates:
                    sorted_missing = sorted(missing_dates)
                    logger.warning(
                        "dq_rule_completeness_gap",
                        event="dq_check",
                        missing_count=len(missing_dates),
                        missing_dates=sorted_missing,
                    )
                    parts.append(
                        f"missing data for {len(missing_dates)} trading days: "
                        + f"{sorted_missing}"
                    )
                if instrument_gaps:
                    total_gap_rows = sum(len(g) for g in instrument_gaps.values())
                    affected += total_gap_rows
                    sample = {
                        inst: g[:5] for inst, g in sorted(instrument_gaps.items())[:5]
                    }
                    logger.warning(
                        "dq_rule_completeness_instrument_gap",
                        event="dq_check",
                        instruments=len(instrument_gaps),
                        gaps=sample,
                    )
                    parts.append(
                        f"{len(instrument_gaps)} instrument(s) with per-date "
                        + f"gaps ({total_gap_rows} instrument-day rows): {sample}"
                    )
                msg = "Completeness: " + "; ".join(parts)
                return DQIssue(
                    level=DQLevel.STATISTICAL,
                    severity=DQSeverity.ALERT,
                    rule_name="completeness",
                    message=msg,
                    affected_rows=affected,
                )

        except (
            pl_exceptions.ComputeError,
            pl_exceptions.SchemaError,
            pl_exceptions.ColumnNotFoundError,
        ) as e:
            # Polars 相关错误 - ALERT 级别
            logger.exception(
                "dq_completeness_check_failed",
                error_type=type(e).__name__,
                rule_type="completeness",
            )
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="completeness",
                message=f"Completeness check failed: {type(e).__name__}",
                affected_rows=0,
                sample_data=[],
            )
        except ValueError as e:
            # 数值错误 - WARNING 级别
            logger.warning(
                "dq_completeness_invalid_value",
                error=str(e),
                rule_type="completeness",
            )
            return DQIssue(
                level=DQLevel.STATISTICAL,
                severity=DQSeverity.WARNING,
                rule_name="completeness",
                message=f"Invalid value in completeness check: {e}",
                affected_rows=0,
                sample_data=[],
            )
