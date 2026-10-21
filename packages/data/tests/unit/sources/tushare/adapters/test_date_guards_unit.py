"""日期车道响应守卫单元测试（#585）。"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_data.sources.base import SourceFetchError
from ditto_data.sources.tushare.adapters._guards import assert_single_trade_date


def test_empty_response_passes_without_column_inspection() -> None:
    assert_single_trade_date(
        pl.DataFrame(), expected="20261020", dataset="stock_status.suspend_d"
    )
    assert_single_trade_date(
        pl.DataFrame(schema={"ts_code": pl.String}),
        expected="20261020",
        dataset="stock_status.suspend_d",
    )


def test_matching_dates_pass() -> None:
    frame = pl.DataFrame(
        {
            "ts_code": ["600000.SH", "000001.SZ"],
            "trade_date": ["20261020", "20261020"],
        }
    )

    assert_single_trade_date(
        frame, expected="20261020", dataset="stock_status.suspend_d"
    )


def test_foreign_dates_fail_closed_with_evidence() -> None:
    frame = pl.DataFrame(
        {
            "ts_code": ["600000.SH", "000001.SZ", "000002.SZ"],
            "trade_date": ["19990504", "19990504", "20261020"],
        }
    )

    with pytest.raises(SourceFetchError) as exc_info:
        assert_single_trade_date(
            frame, expected="20261020", dataset="stock_status.suspend_d"
        )

    details = exc_info.value.details
    assert details["expected_trade_date"] == "20261020"
    assert details["foreign_trade_dates"] == ["19990504"]
    assert details["foreign_row_count"] == 2


def test_missing_guard_column_fails_closed() -> None:
    frame = pl.DataFrame({"ts_code": ["600000.SH"]})

    with pytest.raises(SourceFetchError, match="trade_date"):
        assert_single_trade_date(
            frame, expected="20261020", dataset="stock_status.suspend_d"
        )


def test_null_guard_column_values_count_as_mismatched() -> None:
    # pl.col != expected 对 null 谓词返回 null 并被过滤——null 守卫列值
    # 必须经 ne_missing 计为失配（correctness review F1）。
    frame = pl.DataFrame(
        {
            "ts_code": ["600000.SH"],
            "trade_date": [None],
        }
    )

    with pytest.raises(SourceFetchError) as exc_info:
        assert_single_trade_date(
            frame, expected="20261020", dataset="stock_status.suspend_d"
        )

    assert exc_info.value.details["foreign_row_count"] == 1


def test_numeric_date_column_is_coerced_not_raised() -> None:
    # dtype 漂移（数值/预解析日期列）守卫内 cast 吸收，仍走 fail closed
    # 而非裸 polars 错误（correctness review F3）。
    frame = pl.DataFrame(
        {
            "ts_code": ["600000.SH"],
            "trade_date": [20261020],
        }
    )

    assert_single_trade_date(
        frame, expected="20261020", dataset="stock_status.suspend_d"
    )
    frame_foreign = pl.DataFrame(
        {
            "ts_code": ["600000.SH"],
            "trade_date": [19990504],
        }
    )
    with pytest.raises(SourceFetchError):
        assert_single_trade_date(
            frame_foreign, expected="20261020", dataset="stock_status.suspend_d"
        )
