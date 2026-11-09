"""维护者确认的 ETF 参考事实声明读取器单元测试（#408）。"""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest
from ditto_data.sources.reference_config import (
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
        "effective_to",
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
        "effective_to": None,
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


def test_default_path_under_config_default(tmp_path: Path) -> None:
    assert get_default_etf_reference_config_path(tmp_path) == (
        tmp_path / "config" / "default" / "etf_reference.json"
    )


def test_frame_is_stable_across_reads(tmp_path: Path) -> None:
    source = _source(tmp_path, _declaration())
    assert source.fetch_etf_reference().equals(source.fetch_etf_reference())


def test_declaration_preserves_dated_rules_across_the_cross_border_switch(
    tmp_path: Path,
) -> None:
    document = {
        "confirmed_at": "2026-11-09",
        "instruments": [
            {
                "source_ticker": "510900.SH",
                "facts": {
                    "settlement_cycle": {
                        "value": value,
                        "unit": "days",
                        "effective_from": first,
                        "effective_to": last,
                        "basis": basis,
                    }
                },
            }
            for value, first, last, basis in [
                ("1", "2012-08-09", "2015-01-19", "original listing rules"),
                ("0", "2015-01-19", None, "SSE notice 2015-6"),
            ]
        ],
    }
    frame = _source(tmp_path, document).fetch_etf_reference()
    assert frame.select("value", "effective_from", "effective_to").rows() == [
        ("1", "2012-08-09", "2015-01-19"),
        ("0", "2015-01-19", None),
    ]
    assert frame["basis"].to_list() == ["original listing rules", "SSE notice 2015-6"]


@pytest.mark.parametrize(
    "end", ["2026-08-31", "2026-09-01", "invalid", 1, "20260902", "2026-W37-1"]
)
def test_invalid_fact_interval_is_rejected(tmp_path: Path, end: object) -> None:
    with pytest.raises(EtfReferenceConfigError):
        _source(tmp_path, _declaration(effective_to=end)).fetch_etf_reference()


def test_overlapping_fact_versions_are_rejected(tmp_path: Path) -> None:
    document = _declaration()
    instruments = document["instruments"]
    assert isinstance(instruments, list)
    instruments.append(
        {
            "source_ticker": "510300.SH",
            "facts": {
                "trading_currency": {
                    "value": "USD",
                    "unit": "text",
                    "effective_from": "2026-09-02",
                    "basis": "conflicting version",
                }
            },
        }
    )
    with pytest.raises(EtfReferenceConfigError, match="overlapping"):
        _source(tmp_path, document).fetch_etf_reference()
