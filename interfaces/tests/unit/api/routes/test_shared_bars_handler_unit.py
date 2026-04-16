"""Tests for shared bars handler."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_interfaces.api.routes.shared_bars import handle_bars_post

pytestmark = pytest.mark.asyncio


def _make_facade(
    *,
    valid_codes: set[str] | None = None,
    code_to_id: dict[str, int] | None = None,
    id_to_code: dict[int, str] | None = None,
    bars_df: pl.DataFrame | None = None,
) -> MagicMock:
    """Build a mock facade satisfying InstrumentCodeQueryFacade interface."""
    valid = valid_codes or {"CODE_A", "CODE_B"}
    c2i = code_to_id or {"CODE_A": 1, "CODE_B": 2}
    i2c = id_to_code or {1: "CODE_A", 2: "CODE_B"}

    facade = MagicMock()
    facade.get_valid_codes.return_value = valid
    facade.code_to_instrument_id.side_effect = lambda c: c2i[c]
    facade.instrument_id_to_code.side_effect = i2c.get
    facade.get_all_instrument_ids.return_value = list(c2i.values())
    facade.list_bars.return_value = bars_df if bars_df is not None else pl.DataFrame()
    return facade


def _make_query(
    codes: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = 100,
) -> MagicMock:
    """Build a mock query with code list and date fields."""
    query = MagicMock()
    query.codes = codes
    query.start_date = start
    query.end_date = end
    query.limit = limit
    return query


def _converter(df: pl.DataFrame) -> list[dict[str, Any]]:
    """Simple converter for testing — returns list of row dicts."""
    return df.to_dicts()


@pytest.mark.unit
class TestHandleBarsPost:
    """Tests for the shared handle_bars_post function."""

    async def test_empty_data_returns_empty_list(self):
        """Empty DataFrame from facade returns empty data list."""
        facade = _make_facade()
        query = _make_query(codes=["CODE_A"])
        result = await handle_bars_post(
            facade=facade,
            codes=query.codes,
            start_date=query.start_date,
            end_date=query.end_date,
            limit=query.limit,
            alias="test_code",
            converter=_converter,
        )
        assert result.data == []

    async def test_invalid_code_raises_bad_request(self):
        """Invalid code raises BadRequestError with message listing valid codes."""
        from ditto_interfaces.api.errors import BadRequestError

        facade = _make_facade(valid_codes={"CODE_A"})
        query = _make_query(codes=["INVALID"])
        with pytest.raises(BadRequestError, match=r"Invalid.*INVALID"):
            await handle_bars_post(
                facade=facade,
                codes=query.codes,
                start_date=query.start_date,
                end_date=query.end_date,
                limit=query.limit,
                alias="test_code",
                converter=_converter,
            )

    async def test_no_codes_returns_all_instruments(self):
        """When codes is None, all instrument IDs are queried."""
        df = pl.DataFrame(
            {
                "instrument_id": pl.Series([1], dtype=pl.Int64),
                "trade_date_utc": ["2024-01-01"],
                "open": [1.0],
                "high": [2.0],
                "low": [0.5],
                "close": [1.5],
            }
        )
        facade = _make_facade(bars_df=df)
        query = _make_query(codes=None)
        result = await handle_bars_post(
            facade=facade,
            codes=query.codes,
            start_date=query.start_date,
            end_date=query.end_date,
            limit=query.limit,
            alias="test_code",
            converter=_converter,
        )
        facade.get_all_instrument_ids.assert_called_once()
        assert len(result.data) == 1
        assert result.data[0]["test_code"] == "CODE_A"

    async def test_date_range_passed_correctly(self):
        """Start/end dates are converted to ISO strings for facade."""
        facade = _make_facade()
        query = _make_query(
            codes=["CODE_A"],
            start=date(2024, 1, 1),
            end=date(2024, 6, 30),
        )
        await handle_bars_post(
            facade=facade,
            codes=query.codes,
            start_date=query.start_date,
            end_date=query.end_date,
            limit=query.limit,
            alias="test_code",
            converter=_converter,
        )
        facade.list_bars.assert_called_once_with(
            instrument_ids=[1],
            start="2024-01-01",
            end="2024-06-30",
            limit=100,
        )

    async def test_converter_is_called(self):
        """Custom converter receives the DataFrame and returns its output."""
        df = pl.DataFrame(
            {
                "instrument_id": pl.Series([1], dtype=pl.Int64),
                "trade_date_utc": ["2024-01-01"],
                "open": [1.0],
                "high": [2.0],
                "low": [0.5],
                "close": [1.5],
            }
        )
        facade = _make_facade(bars_df=df)

        sentinel = object()
        custom_converter = MagicMock(return_value=sentinel)

        query = _make_query(codes=["CODE_A"])
        result = await handle_bars_post(
            facade=facade,
            codes=query.codes,
            start_date=query.start_date,
            end_date=query.end_date,
            limit=query.limit,
            alias="test_code",
            converter=custom_converter,
        )
        custom_converter.assert_called_once()
        assert result.data is sentinel
