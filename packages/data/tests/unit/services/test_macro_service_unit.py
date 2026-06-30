"""Unit tests for MacroService."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import polars as pl
import pytest
from ditto_data.models.macro import IndicatorMetadataSpec
from ditto_data.services.macro_service import MacroQuery, MacroService
from ditto_kernel.market import MacroCategory, MacroFrequency


@dataclass
class _IndicatorReadCall:
    indicator_ids: list[int]
    start_date: str | None
    end_date: str | None
    as_of_date: str | None


class _IndicatorReader:
    def __init__(self, frame: pl.DataFrame | None = None) -> None:
        self.frame = frame if frame is not None else pl.DataFrame()
        self.calls: list[_IndicatorReadCall] = []

    def get(
        self,
        *,
        indicator_ids: list[int],
        start_date: str | None = None,
        end_date: str | None = None,
        as_of_date: str | None = None,
    ) -> pl.DataFrame:
        self.calls.append(
            _IndicatorReadCall(
                indicator_ids=indicator_ids,
                start_date=start_date,
                end_date=end_date,
                as_of_date=as_of_date,
            )
        )
        return self.frame.filter(pl.col("indicator_id").is_in(indicator_ids))


class _IndicatorWriter:
    def __init__(self) -> None:
        self.frames: list[pl.DataFrame] = []

    def write(self, df: pl.DataFrame) -> int:
        self.frames.append(df)
        return df.height


class _MetadataReader:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame
        self.list_category_calls: list[str | None] = []
        self.code_calls: list[str] = []
        self.id_calls: list[int] = []

    def list_by_category(self, category: str | None = None) -> pl.DataFrame:
        self.list_category_calls.append(category)
        if category is None:
            return self.frame
        return self.frame.filter(pl.col("category") == category)

    def get_by_code(self, code: str) -> pl.DataFrame:
        self.code_calls.append(code)
        return self.frame.filter(pl.col("code") == code)

    def get_by_id(self, indicator_id: int) -> pl.DataFrame:
        self.id_calls.append(indicator_id)
        return self.frame.filter(pl.col("indicator_id") == indicator_id)


class _MetadataWriter:
    def __init__(self) -> None:
        self.specs: list[IndicatorMetadataSpec] = []
        self._ids: dict[str, int] = {}

    def upsert(self, spec: IndicatorMetadataSpec) -> int:
        self.specs.append(spec)
        if spec.code not in self._ids:
            self._ids[spec.code] = len(self._ids) + 100
        return self._ids[spec.code]


def _metadata_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "indicator_id": [1, 2, 3],
            "code": ["CPI", "M2", "GDP"],
            "name": ["Consumer Price Index", "Money Supply", "Gross Domestic"],
            "category": ["prices", "money_supply", "economic"],
            "frequency": ["monthly", "monthly", "quarterly"],
            "unit": ["pct", "cny", "cny"],
        }
    )


def _service(
    *,
    indicator_frame: pl.DataFrame | None = None,
    metadata_frame: pl.DataFrame | None = None,
) -> tuple[
    MacroService,
    _IndicatorReader,
    _IndicatorWriter,
    _MetadataReader,
    _MetadataWriter,
]:
    indicator_reader = _IndicatorReader(indicator_frame)
    indicator_writer = _IndicatorWriter()
    metadata_reader = _MetadataReader(
        metadata_frame if metadata_frame is not None else _metadata_frame()
    )
    metadata_writer = _MetadataWriter()
    return (
        MacroService(
            indicator_reader=indicator_reader,  # type: ignore[arg-type]
            indicator_writer=indicator_writer,  # type: ignore[arg-type]
            metadata_reader=metadata_reader,  # type: ignore[arg-type]
            metadata_writer=metadata_writer,  # type: ignore[arg-type]
        ),
        indicator_reader,
        indicator_writer,
        metadata_reader,
        metadata_writer,
    )


def _macro_write_frame(**extra: Any) -> pl.DataFrame:
    base: dict[str, list[Any]] = {
        "indicator_code": ["CPI", "CPI", "GDP"],
        "indicator_name": ["Consumer Price Index", "Consumer Price Index", "GDP"],
        "category": ["prices", "prices", "economic"],
        "frequency": ["monthly", "monthly", "quarterly"],
        "need_pit": [True, True, False],
        "date": [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)],
        "value": [1.2, 1.4, 5.0],
    }
    base.update(extra)
    return pl.DataFrame(base, strict=False)


class TestMacroServiceSaveIndicators:
    def test_rejects_missing_required_columns(self) -> None:
        service, _, _, _, _ = _service()

        with pytest.raises(ValueError, match="写入缺少必要列"):
            service.save_indicators(pl.DataFrame({"indicator_code": ["CPI"]}))

    def test_empty_frame_returns_zero_without_writing(self) -> None:
        service, _, writer, _, metadata_writer = _service()
        empty = pl.DataFrame(
            schema={
                "indicator_code": pl.String,
                "indicator_name": pl.String,
                "category": pl.String,
                "frequency": pl.String,
                "need_pit": pl.Boolean,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

        result = service.save_indicators(empty)

        assert result.records_written == 0
        assert writer.frames == []
        assert metadata_writer.specs == []

    def test_upserts_unique_metadata_and_writes_indicator_rows(self) -> None:
        service, _, writer, _, metadata_writer = _service()

        result = service.save_indicators(
            _macro_write_frame(
                source=[None, None, "stats"],
                unit=[date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1)],
                description=[42, 42, 42],
                knowledge_date=[
                    date(2026, 2, 1),
                    date(2026, 3, 1),
                    date(2026, 4, 1),
                ],
            )
        )

        assert result.records_written == 3
        assert [spec.code for spec in metadata_writer.specs] == ["CPI", "GDP"]
        assert metadata_writer.specs[0].source is None
        assert metadata_writer.specs[0].description == "42"
        assert metadata_writer.specs[1].unit == "2026-01-01"
        assert metadata_writer.specs[1].description == "42"
        written = writer.frames[0]
        assert written["indicator_id"].to_list() == [100, 100, 101]
        assert written["knowledge_date"].dtype == pl.Date

    def test_write_adds_missing_knowledge_date_column(self) -> None:
        service, _, writer, _, _ = _service()

        result = service.save_indicators(_macro_write_frame())

        assert result.records_written == 3
        written = writer.frames[0]
        assert "knowledge_date" in written.columns
        assert written["knowledge_date"].null_count() == 3


class TestMacroServiceFindIndicators:
    def test_returns_empty_when_metadata_filter_resolves_no_indicators(self) -> None:
        service, reader, _, metadata_reader, _ = _service()

        result = service.find_indicators(MacroQuery(category=MacroCategory.EMPLOYMENT))

        assert result.is_empty()
        assert reader.calls == []
        assert metadata_reader.list_category_calls == [MacroCategory.EMPLOYMENT]

    def test_resolves_codes_deduplicates_and_ignores_unknown_codes(self) -> None:
        indicator_frame = pl.DataFrame(
            {
                "indicator_id": [1],
                "date": [date(2026, 1, 31)],
                "value": [1.2],
                "knowledge_date": [date(2026, 2, 1)],
            }
        )
        service, reader, _, metadata_reader, _ = _service(
            indicator_frame=indicator_frame
        )

        result = service.find_indicators(
            MacroQuery(
                indicators=["CPI", "CPI", "UNKNOWN"],
                start="2026-01-01",
                end="2026-01-31",
                asof="2026-02-01",
            )
        )

        assert result.height == 1
        assert result["code"].to_list() == ["CPI"]
        assert reader.calls == [
            _IndicatorReadCall(
                indicator_ids=[1],
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-02-01",
            )
        ]
        assert set(metadata_reader.code_calls) == {"CPI", "UNKNOWN"}
        assert metadata_reader.id_calls == [1]

    def test_filters_numeric_ids_by_category_and_frequency(self) -> None:
        indicator_frame = pl.DataFrame(
            {
                "indicator_id": [2],
                "date": [date(2026, 1, 31)],
                "value": [100.0],
            }
        )
        service, reader, _, _, _ = _service(indicator_frame=indicator_frame)

        result = service.find_indicators(
            MacroQuery(
                indicators=[1, 2, 3, 2],
                category=MacroCategory.MONEY_SUPPLY,
                frequency=MacroFrequency.MONTHLY,
            )
        )

        assert result.height == 1
        assert result["indicator_id"].to_list() == [2]
        assert reader.calls[0].indicator_ids == [2]

    def test_returns_data_without_metadata_when_enrichment_metadata_is_missing(
        self,
    ) -> None:
        indicator_frame = pl.DataFrame(
            {
                "indicator_id": [99],
                "date": [date(2026, 1, 31)],
                "value": [1.0],
            }
        )
        service, _, _, _, _ = _service(
            indicator_frame=indicator_frame,
            metadata_frame=pl.DataFrame(
                {
                    "indicator_id": [99],
                    "code": ["UNLISTED"],
                    "name": ["Unlisted"],
                    "category": ["prices"],
                    "frequency": ["monthly"],
                    "unit": ["pct"],
                }
            ),
        )
        service._metadata_reader.frame = pl.DataFrame(  # type: ignore[attr-defined]
            schema={
                "indicator_id": pl.Int64,
                "code": pl.String,
                "name": pl.String,
                "category": pl.String,
                "frequency": pl.String,
                "unit": pl.String,
            }
        )

        result = service.find_indicators(MacroQuery(indicators=[99]))

        assert result.columns == ["indicator_id", "date", "value"]
        assert result.height == 1

    def test_list_indicators_delegates_to_find_with_date_range_and_category(
        self,
    ) -> None:
        indicator_frame = pl.DataFrame(
            {
                "indicator_id": [1],
                "date": [date(2026, 1, 31)],
                "value": [1.2],
            }
        )
        service, reader, _, metadata_reader, _ = _service(
            indicator_frame=indicator_frame
        )

        result = service.list_indicators(
            start="2026-01-01",
            end="2026-01-31",
            category=MacroCategory.PRICES,
        )

        assert result["code"].to_list() == ["CPI"]
        assert metadata_reader.list_category_calls == [MacroCategory.PRICES]
        assert reader.calls[0].start_date == "2026-01-01"
        assert reader.calls[0].end_date == "2026-01-31"
