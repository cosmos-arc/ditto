"""Tests for provider industry snapshots entering the metadata read model."""

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.services.metadata.instrument import (
    InstrumentService,
    InstrumentServiceDeps,
)


def _service() -> tuple[InstrumentService, dict[str, MagicMock]]:
    ports = {
        "instrument_reader": MagicMock(),
        "instrument_writer": MagicMock(),
        "name_history_reader": MagicMock(),
        "name_history_writer": MagicMock(),
        "industry_reader": MagicMock(),
        "industry_writer": MagicMock(),
        "industry_mapping_reader": MagicMock(),
        "industry_mapping_writer": MagicMock(),
        "instrument_id_allocator": MagicMock(),
        "exchange_transformers": MagicMock(),
    }
    return InstrumentService(InstrumentServiceDeps(**ports)), ports


@pytest.mark.unit
def test_save_industry_classification_normalizes_level_and_source() -> None:
    service, ports = _service()
    frame = pl.DataFrame(
        {
            "industry_id": ["801010.SI"],
            "industry_name": ["农林牧渔"],
            "industry_level": [1],
            "source": ["sw"],
            "classification_version": ["SW2021"],
            "knowledge_date": [date(2026, 9, 1)],
        }
    )

    assert service.save_industry_classification(frame, source="tushare") == 1

    industry = ports["industry_writer"].register.call_args.args[0]
    assert industry.industry_id == "801010.SI"
    assert industry.industry_level == "L1"
    assert industry.source == "sw"


@pytest.mark.unit
def test_save_industry_mapping_resolves_provider_ticker_and_preserves_interval() -> (
    None
):
    service, ports = _service()
    ports["instrument_reader"].resolve_instrument_ids_batch.return_value = {
        "000001.SZ": 1_000_001
    }
    frame = pl.DataFrame(
        {
            "instrument_id": ["000001.SZ"],
            "industry_id": ["801780.SI"],
            "industry_date": [date(2021, 12, 13)],
            "effective_to": [date(2024, 1, 2)],
            "classification_version": ["SW2021"],
            "source": ["sw"],
            "knowledge_date": [date(2026, 9, 1)],
        }
    )

    assert service.save_industry_mapping(frame, source="tushare") == 1

    ports["instrument_reader"].resolve_instrument_ids_batch.assert_called_once_with(
        ["000001.SZ"], "tushare", None
    )
    mapping = ports["industry_mapping_writer"].update_mapping.call_args.args[0]
    assert mapping.instrument_id == 1_000_001
    assert mapping.industry_id == "801780.SI"
    assert mapping.effective_from == "2021-12-13"
    assert mapping.effective_to == "2024-01-02"
    assert mapping.entry_reason == "SW2021"
    assert mapping.source == "sw"


@pytest.mark.unit
def test_save_industry_mapping_fails_closed_for_unresolved_ticker() -> None:
    service, ports = _service()
    ports["instrument_reader"].resolve_instrument_ids_batch.return_value = {}
    frame = pl.DataFrame(
        {
            "instrument_id": ["000001.SZ"],
            "industry_id": ["801780.SI"],
            "industry_date": [date(2021, 12, 13)],
        }
    )

    with pytest.raises(ValueError, match="unresolved instruments: 1"):
        service.save_industry_mapping(frame, source="tushare")

    ports["industry_mapping_writer"].update_mapping.assert_not_called()
