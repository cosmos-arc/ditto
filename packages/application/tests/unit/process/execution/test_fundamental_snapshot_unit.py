"""fundamental_snapshot 单元测试 — 基本面快照闭包（PIT 查询 + 因子列预计算）."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.processes.execution.fundamental_snapshot import (
    build_fundamental_snapshot_fn,
)
from ditto_kernel.identity import InstrumentId


class TestFundamentalSnapshotFn:
    """build_fundamental_snapshot_fn — PIT 查询 + 预计算 roe/net_margin/eps."""

    def test_empty_instrument_ids_returns_empty_with_schema(self) -> None:
        """空标的列表返回空 DataFrame（含正确 schema），不调用 facade."""
        facade = MagicMock()
        fn = build_fundamental_snapshot_fn(facade, allow_experimental_data=True)

        df = fn([], date(2024, 1, 2))

        assert df.is_empty()
        assert set(df.columns) == {"instrument_id", "roe", "net_margin", "eps"}
        facade.get_balance_sheet.assert_not_called()

    def test_computes_roe_and_net_margin_correctly(self) -> None:
        """roe = net_profit/net_assets，net_margin = net_profit/revenue，eps 透传."""
        facade = MagicMock()
        facade.get_balance_sheet.return_value = pl.DataFrame(
            {"net_assets": [1_000_000.0], "total_assets": [2_000_000.0]},
        )
        facade.get_income_statement.return_value = pl.DataFrame(
            {"net_profit": [150_000.0], "eps": [1.5], "revenue": [1_000_000.0]},
        )
        fn = build_fundamental_snapshot_fn(facade, allow_experimental_data=True)

        df = fn([InstrumentId(1)], date(2024, 1, 2))

        assert df.height == 1
        assert df["roe"][0] == pytest.approx(0.15)
        assert df["net_margin"][0] == pytest.approx(0.15)
        assert df["eps"][0] == pytest.approx(1.5)

    def test_uses_as_of_date_for_pit_query(self) -> None:
        """PIT as_of 透传给 facade（调用方传 knowledge_date，非 trade_date）."""
        facade = MagicMock()
        facade.get_balance_sheet.return_value = pl.DataFrame()
        facade.get_income_statement.return_value = pl.DataFrame()
        fn = build_fundamental_snapshot_fn(facade, allow_experimental_data=True)

        knowledge = date(2024, 1, 1)
        fn([InstrumentId(1)], knowledge)

        bs_call = facade.get_balance_sheet.call_args
        # 签名 (instrument_id, as_of_date, *, allow_experimental_data)
        assert bs_call.args[1] == knowledge
        assert bs_call.kwargs["allow_experimental_data"] is True
        inc_call = facade.get_income_statement.call_args
        assert inc_call.args[1] == knowledge

    def test_propagates_allow_experimental_data(self) -> None:
        """allow_experimental_data 透传到 facade 的 maturity gate opt-in."""
        facade = MagicMock()
        facade.get_balance_sheet.return_value = pl.DataFrame()
        facade.get_income_statement.return_value = pl.DataFrame()
        fn = build_fundamental_snapshot_fn(facade, allow_experimental_data=False)

        fn([InstrumentId(1)], date(2024, 1, 2))

        assert (
            facade.get_balance_sheet.call_args.kwargs["allow_experimental_data"]
            is False
        )
        assert (
            facade.get_income_statement.call_args.kwargs["allow_experimental_data"]
            is False
        )

    def test_zero_net_assets_yields_null_roe(self) -> None:
        """net_assets=0 时 roe=null（除零保护）；net_margin 仍可算."""
        facade = MagicMock()
        facade.get_balance_sheet.return_value = pl.DataFrame(
            {"net_assets": [0.0], "total_assets": [0.0]},
        )
        facade.get_income_statement.return_value = pl.DataFrame(
            {"net_profit": [100.0], "eps": [1.0], "revenue": [500.0]},
        )
        fn = build_fundamental_snapshot_fn(facade, allow_experimental_data=True)

        df = fn([InstrumentId(1)], date(2024, 1, 2))

        assert df["roe"][0] is None
        assert df["net_margin"][0] == pytest.approx(0.2)

    def test_missing_balance_sheet_yields_null_roe(self) -> None:
        """balance_sheet 无数据（None）时 roe=null，eps 仍可从 income 取."""
        facade = MagicMock()
        facade.get_balance_sheet.return_value = None
        facade.get_income_statement.return_value = pl.DataFrame(
            {"net_profit": [100.0], "eps": [2.0], "revenue": [500.0]},
        )
        fn = build_fundamental_snapshot_fn(facade, allow_experimental_data=True)

        df = fn([InstrumentId(1)], date(2024, 1, 2))

        assert df["roe"][0] is None
        assert df["eps"][0] == pytest.approx(2.0)

    def test_missing_income_yields_null_factors(self) -> None:
        """income 无数据时 roe/net_margin/eps 均 null."""
        facade = MagicMock()
        facade.get_balance_sheet.return_value = pl.DataFrame(
            {"net_assets": [1_000_000.0], "total_assets": [2_000_000.0]},
        )
        facade.get_income_statement.return_value = None
        fn = build_fundamental_snapshot_fn(facade, allow_experimental_data=True)

        df = fn([InstrumentId(1)], date(2024, 1, 2))

        assert df["roe"][0] is None
        assert df["net_margin"][0] is None
        assert df["eps"][0] is None

    def test_multiple_instruments_each_queried(self) -> None:
        """多标的：每个独立 PIT 查询，返回行数 = 标的数."""
        facade = MagicMock()
        facade.get_balance_sheet.return_value = pl.DataFrame(
            {"net_assets": [500_000.0], "total_assets": [1_000_000.0]},
        )
        facade.get_income_statement.return_value = pl.DataFrame(
            {"net_profit": [50_000.0], "eps": [1.0], "revenue": [500_000.0]},
        )
        fn = build_fundamental_snapshot_fn(facade, allow_experimental_data=True)

        df = fn(
            [InstrumentId(1), InstrumentId(2), InstrumentId(3)],
            date(2024, 1, 2),
        )

        assert df.height == 3
        assert set(df["instrument_id"].to_list()) == {1, 2, 3}
        # 每标的查 balance + income = 6 次 facade 调用
        assert facade.get_balance_sheet.call_count == 3
        assert facade.get_income_statement.call_count == 3

    def test_dtype_is_float64_for_factor_columns(self) -> None:
        """因子列 dtype 为 Float64（即使全 null 也保持 Float64）."""
        facade = MagicMock()
        facade.get_balance_sheet.return_value = None
        facade.get_income_statement.return_value = None
        fn = build_fundamental_snapshot_fn(facade, allow_experimental_data=True)

        df = fn([InstrumentId(1)], date(2024, 1, 2))

        assert df.schema["roe"] == pl.Float64
        assert df.schema["net_margin"] == pl.Float64
        assert df.schema["eps"] == pl.Float64
        assert df.schema["instrument_id"] == pl.Int64
