"""#592 北交所新旧代码别名登记单元测试."""

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


def _mappings() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "name": ["星昊医药", "诺思兰德", "无此新码"],
            "o_code": ["430017.BJ", "430047.BJ", "830001.BJ"],
            "n_code": ["920017.BJ", "920047.BJ", "929999.BJ"],
            "list_date": ["20230531", None, None],
        }
    )


@pytest.mark.unit
def test_register_bse_code_aliases_registers_resolved_and_skips_unknown() -> None:
    service, ports = _service()
    ports["instrument_reader"].resolve_instrument_ids_batch.return_value = {
        "920017.BJ": 1000001,
        "920047.BJ": 1000002,
    }
    ports["instrument_writer"].register_source_mapping.return_value = True

    summary = service.register_bse_code_aliases(
        _mappings(), observed_at="2026-10-23 12:00:00"
    )

    assert summary == {
        "total": 3,
        "available": 2,
        "unresolved_n_code": 1,
        "conflict": 0,
    }
    calls = ports["instrument_writer"].register_source_mapping.call_args_list
    assert [c.kwargs["source_ticker"] for c in calls] == [
        "430017.BJ",
        "430047.BJ",
    ]
    assert calls[0].kwargs["instrument_id"] == 1000001
    # correctness F1：恒取保守前史起点，与主映射（同上市日）并列会
    # 炸 get_source_tickers tie 守卫/裸码枚举 fan-out
    assert all(c.kwargs["effective_from"] == "1990-01-01" for c in calls)
    assert all(c.kwargs["source"] == "tushare" for c in calls)


@pytest.mark.unit
def test_register_bse_code_aliases_counts_conflicts() -> None:
    service, ports = _service()
    ports["instrument_reader"].resolve_instrument_ids_batch.return_value = {
        "920017.BJ": 1000001,
    }
    ports["instrument_writer"].register_source_mapping.return_value = False

    summary = service.register_bse_code_aliases(
        _mappings(), observed_at="2026-10-23 12:00:00"
    )

    assert summary["conflict"] == 1
    assert summary["available"] == 0
    assert summary["unresolved_n_code"] == 2


@pytest.mark.unit
def test_register_bse_code_aliases_empty_frame() -> None:
    service, ports = _service()
    empty = pl.DataFrame(
        schema={
            "name": pl.String,
            "o_code": pl.String,
            "n_code": pl.String,
            "list_date": pl.String,
        }
    )
    summary = service.register_bse_code_aliases(
        empty, observed_at="2026-10-23 12:00:00"
    )
    assert summary == {
        "total": 0,
        "available": 0,
        "unresolved_n_code": 0,
        "conflict": 0,
    }
    ports["instrument_writer"].register_source_mapping.assert_not_called()
