"""维护者确认的 ETF 参考事实声明读取器单元测试（#408）。"""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest
from ditto_data.sources.reference_config import (
    ETF_REFERENCE_CONFIG_FIELDS,
    EtfReferenceConfigError,
    EtfReferenceConfigSource,
    get_default_etf_reference_config_path,
)


def _declaration(**overrides: object) -> dict[str, object]:
    fact: dict[str, object] = {
        "value": "CNY",
        "unit": "text",
        "effective_from": "2026-09-01",
        "basis": "recorded basis",
    }
    fact.update(overrides)
    return {
        "confirmed_at": "2026-09-30",
        "confirmed_by": "recorded test",
        "instruments": [
            {"source_ticker": "510300.SH", "facts": {"trading_currency": fact}}
        ],
    }


def _source(tmp_path: Path, document: object) -> EtfReferenceConfigSource:
    path = tmp_path / "etf_reference.json"
    path.write_bytes(orjson.dumps(document))
    return EtfReferenceConfigSource(path)


def test_valid_declaration_produces_deterministic_long_frame(tmp_path: Path) -> None:
    frame = _source(tmp_path, _declaration()).fetch_etf_reference()
    assert frame.columns == [
        "source_ticker",
        "field",
        "value",
        "unit",
        "effective_from",
        "basis",
    ]
    assert frame.height == 1
    row = frame.to_dicts()[0]
    assert row == {
        "source_ticker": "510300.SH",
        "field": "trading_currency",
        "value": "CNY",
        "unit": "text",
        "effective_from": "2026-09-01",
        "basis": "recorded basis",
    }


def test_missing_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(EtfReferenceConfigError, match="unreadable"):
        EtfReferenceConfigSource(tmp_path / "absent.json").fetch_etf_reference()


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"instruments": []}, "non-empty instruments"),
        ({"confirmed_at": None}, "confirmed_at"),
        ({"instruments": [{"facts": {}}]}, "source_ticker"),
        ({"instruments": [{"source_ticker": "510300"}]}, "suffixed"),
    ],
)
def test_document_shape_rejections(
    tmp_path: Path, mutation: dict[str, object], match: str
) -> None:
    document = _declaration()
    document.update(mutation)
    with pytest.raises(EtfReferenceConfigError, match=match):
        _source(tmp_path, document).fetch_etf_reference()


def test_unknown_field_rejected(tmp_path: Path) -> None:
    document = _declaration()
    document["instruments"][0]["facts"]["nav_unit"] = {  # type: ignore[index]
        "value": "1",
        "unit": "text",
        "effective_from": "2026-09-01",
        "basis": "recorded",
    }
    with pytest.raises(EtfReferenceConfigError, match="unsupported field"):
        _source(tmp_path, document).fetch_etf_reference()


def test_non_numeric_rule_value_rejected(tmp_path: Path) -> None:
    document = _declaration()
    document["instruments"][0]["facts"]["lot_size"] = {  # type: ignore[index]
        "value": "hundred",
        "unit": "count",
        "effective_from": "2026-09-01",
        "basis": "recorded",
    }
    with pytest.raises(EtfReferenceConfigError, match="numeric"):
        _source(tmp_path, document).fetch_etf_reference()


def test_negative_rule_value_rejected(tmp_path: Path) -> None:
    document = _declaration()
    document["instruments"][0]["facts"]["lot_size"] = {  # type: ignore[index]
        "value": "-100",
        "unit": "count",
        "effective_from": "2026-09-01",
        "basis": "recorded",
    }
    with pytest.raises(EtfReferenceConfigError, match="non-negative"):
        _source(tmp_path, document).fetch_etf_reference()


def test_non_iso_effective_date_rejected(tmp_path: Path) -> None:
    document = _declaration()
    document["instruments"][0]["facts"]["trading_currency"][  # type: ignore[index]
        "effective_from"
    ] = "2026-13-99"
    with pytest.raises(EtfReferenceConfigError, match="ISO date"):
        _source(tmp_path, document).fetch_etf_reference()


def test_duplicate_fact_rejected(tmp_path: Path) -> None:
    document = _declaration()
    instruments = document["instruments"]
    assert isinstance(instruments, list)
    instruments.append(instruments[0])
    with pytest.raises(EtfReferenceConfigError, match="twice"):
        _source(tmp_path, document).fetch_etf_reference()


def test_fields_match_application_read_contract() -> None:
    """写侧白名单与应用层 etf_reference 补充字段合同一致。"""
    from ditto_application.queries.etf_paper_reference import _INPUT_FIELDS

    assert set(_INPUT_FIELDS["etf_reference"]) == ETF_REFERENCE_CONFIG_FIELDS


def test_default_path_under_config_default(tmp_path: Path) -> None:
    assert get_default_etf_reference_config_path(tmp_path) == (
        tmp_path / "config" / "default" / "etf_reference.json"
    )


def test_frame_is_stable_across_reads(tmp_path: Path) -> None:
    source = _source(tmp_path, _declaration())
    assert source.fetch_etf_reference().equals(source.fetch_etf_reference())
