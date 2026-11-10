"""维护者确认的 ETF 份额折算声明读取器单元测试（#762）。"""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest
from ditto_data.sources.etf_share_conversions import (
    ETF_SHARE_CONVERSION_FRAME_COLUMNS,
    EtfShareConversionsConfigError,
    EtfShareConversionsConfigSource,
    get_default_etf_share_conversions_config_path,
)

_FRAME_COLUMNS = list(ETF_SHARE_CONVERSION_FRAME_COLUMNS)


def _document(
    *,
    conversion: dict[str, object] | None = None,
    overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    declared: dict[str, object] = {
        "source_ticker": "159941.SZ",
        "ratio": 4.0,
        "announcement_date": "2022-06-29",
        "effective_date": "2022-07-05",
        "basis": "广发纳斯达克100ETF 份额拆分结果公告 2022-07-05",
        "rounding_note": "1:4 整倍拆分、持有人份额恒整数、无碎份",
    }
    declared.update(conversion or {})
    document: dict[str, object] = {
        "confirmed_at": "2026-11-10",
        "confirmed_by": "recorded test",
        "conversions": [declared],
    }
    document.update(overrides or {})
    return document


def _source(tmp_path: Path, document: object) -> EtfShareConversionsConfigSource:
    path = tmp_path / "etf_share_conversions.json"
    path.write_bytes(orjson.dumps(document))
    return EtfShareConversionsConfigSource(path)


def test_valid_declaration_produces_deterministic_frame(tmp_path: Path) -> None:
    frame = _source(tmp_path, _document()).fetch_etf_share_conversions()
    assert frame.columns == _FRAME_COLUMNS
    assert frame.to_dicts() == [
        {
            "source_ticker": "159941.SZ",
            "ratio": 4.0,
            "announcement_date": "2022-06-29",
            "effective_date": "2022-07-05",
            "basis": "广发纳斯达克100ETF 份额拆分结果公告 2022-07-05",
            "rounding_note": "1:4 整倍拆分、持有人份额恒整数、无碎份",
        }
    ]


def test_default_config_file_is_loadable() -> None:
    source = EtfShareConversionsConfigSource(
        get_default_etf_share_conversions_config_path(
            Path(__file__).resolve().parents[5]
        )
    )
    frame = source.fetch_etf_share_conversions()
    assert frame.height >= 1
    split = frame.filter(
        (frame["source_ticker"] == "159941.SZ")
        & (frame["effective_date"] == "2022-07-05")
    ).to_dicts()
    assert len(split) == 1
    assert split[0]["ratio"] == 4.0
    assert split[0]["announcement_date"] == "2022-06-29"


def test_missing_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(EtfShareConversionsConfigError, match="unreadable"):
        EtfShareConversionsConfigSource(
            tmp_path / "absent.json"
        ).fetch_etf_share_conversions()


@pytest.mark.parametrize(
    ("conversion", "overrides", "match"),
    [
        (None, {"conversions": []}, "non-empty conversions"),
        (None, {"conversions": "nope"}, "non-empty conversions"),
        (None, {"confirmed_at": None}, "confirmed_at"),
        (None, {"confirmed_at": "2026/11/10"}, "ISO date"),
        ({"ratio": 1.0}, None, "ratio"),
        ({"ratio": 0.0}, None, "ratio"),
        ({"ratio": -4.0}, None, "ratio"),
        ({"ratio": "4.0"}, None, "ratio"),
        ({"announcement_date": "2022-07-05"}, None, "announcement_date before"),
        ({"announcement_date": "not-a-date"}, None, "ISO date"),
        ({"effective_date": "2022-06-29"}, None, "announcement_date before"),
        ({"source_ticker": "159941"}, None, "suffixed"),
        ({"basis": ""}, None, "basis"),
        ({"rounding_note": ""}, None, "rounding_note"),
    ],
)
def test_declaration_rejections(
    tmp_path: Path,
    conversion: dict[str, object] | None,
    overrides: dict[str, object] | None,
    match: str,
) -> None:
    with pytest.raises(EtfShareConversionsConfigError, match=match):
        _source(
            tmp_path, _document(conversion=conversion, overrides=overrides)
        ).fetch_etf_share_conversions()


def test_conflicting_identity_is_rejected(tmp_path: Path) -> None:
    document = _document()
    document["conversions"] = [  # type: ignore[index]
        document["conversions"][0],  # type: ignore[index]
        {**document["conversions"][0], "ratio": 2.0},  # type: ignore[index]
    ]
    with pytest.raises(EtfShareConversionsConfigError, match="twice"):
        _source(tmp_path, document).fetch_etf_share_conversions()


def test_identical_duplicate_declarations_are_rejected(tmp_path: Path) -> None:
    document = _document()
    document["conversions"] = [  # type: ignore[index]
        document["conversions"][0],  # type: ignore[index]
        document["conversions"][0],  # type: ignore[index]
    ]
    with pytest.raises(EtfShareConversionsConfigError, match="twice"):
        _source(tmp_path, document).fetch_etf_share_conversions()
