"""
维护者确认的 ETF 参考事实声明文件（#408）。

Paper handoff/execution 需要的交易限制、币种与执行规则/费用在现有外部
数据源中没有结构化提供方；本模块把维护者确认的声明式配置作为合法
来源（``Source.CONFIG``）读成可摄取的长表。观察缺失不推断：未声明的
标的/字段在 Paper 读侧保持缺失并精确拒绝。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite
from pathlib import Path
from typing import cast

import orjson
import polars as pl
from ditto_platform.foundation import logger

__all__ = [
    "ETF_REFERENCE_CONFIG_FIELDS",
    "EtfReferenceConfigError",
    "EtfReferenceConfigSource",
    "get_default_etf_reference_config_path",
]

# 与应用层读侧合同（etf_paper_reference._INPUT_FIELDS["etf_reference"]）
# 保持一致的字段白名单；两侧一致性由集成测试锁定。
ETF_REFERENCE_CONFIG_FIELDS: frozenset[str] = frozenset(
    {
        "trading_currency",
        "trading_restriction",
        "lot_size",
        "tick_size",
        "settlement_cycle",
        "price_limit_pct",
        "commission_rate",
        "min_commission",
        "stamp_duty_rate",
        "transfer_fee_rate",
    }
)

_NUMERIC_FIELDS: frozenset[str] = frozenset(
    ETF_REFERENCE_CONFIG_FIELDS - {"trading_currency", "trading_restriction"}
)

_FRAME_COLUMNS: tuple[str, ...] = (
    "source_ticker",
    "field",
    "value",
    "unit",
    "effective_from",
    "basis",
)


class EtfReferenceConfigError(ValueError):
    """声明文件结构或取值非法（fail closed，不静默丢弃）。"""


@dataclass(frozen=True)
class _Fact:
    """一条已确认的参考事实声明。"""

    source_ticker: str
    field: str
    value: str
    unit: str
    effective_from: str
    basis: str


def get_default_etf_reference_config_path(config_root: Path) -> Path:
    """返回跨环境默认声明文件路径（config/default 层）。"""
    return config_root / "config" / "default" / "etf_reference.json"


class EtfReferenceConfigSource:
    """读取并校验 ETF 参考事实声明文件，产出确定性长表。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """声明文件路径（证据记录用）。"""
        return self._path

    def fetch_etf_reference(self) -> pl.DataFrame:
        """解析声明文件为 ``_FRAME_COLUMNS`` 列的全字符串长表。"""
        facts = self._load_facts()
        frame = pl.DataFrame(
            {
                column: [getattr(fact, column) for fact in facts]
                for column in _FRAME_COLUMNS
            },
            schema=dict.fromkeys(_FRAME_COLUMNS, pl.String),
        )
        logger.info(
            "ETF reference config loaded",
            event="etf_reference_config_loaded",
            path=str(self._path),
            row_count=frame.height,
        )
        return frame

    def _load_facts(self) -> list[_Fact]:
        facts: list[_Fact] = []
        seen: set[tuple[str, str]] = set()
        for instrument in self._load_instruments():
            facts.extend(_parse_instrument(instrument, seen))
        facts.sort(key=lambda fact: (fact.source_ticker, fact.field))
        return facts

    def _load_instruments(self) -> list[object]:
        try:
            raw = self._path.read_bytes()
        except OSError as error:
            raise EtfReferenceConfigError(
                f"ETF reference config is unreadable: {self._path}"
            ) from error
        try:
            document: object = orjson.loads(raw)
        except orjson.JSONDecodeError as error:
            raise EtfReferenceConfigError(
                f"ETF reference config is not valid JSON: {self._path}"
            ) from error
        if not isinstance(document, dict):
            raise EtfReferenceConfigError("ETF reference config must be an object")
        typed = cast("dict[str, object]", document)
        instruments = typed.get("instruments")
        confirmed_at = typed.get("confirmed_at")
        if not isinstance(instruments, list) or not instruments:
            raise EtfReferenceConfigError(
                "ETF reference config requires a non-empty instruments list"
            )
        if not isinstance(confirmed_at, str):
            raise EtfReferenceConfigError(
                "ETF reference config requires a confirmed_at declaration date"
            )
        _require_iso_date("confirmed_at", confirmed_at)
        return cast("list[object]", instruments)


def _parse_instrument(instrument: object, seen: set[tuple[str, str]]) -> list[_Fact]:
    """解析一个标的的全部事实声明；重复声明 fail closed。"""
    if not isinstance(instrument, dict):
        raise EtfReferenceConfigError(
            "ETF reference config instrument entries must be objects"
        )
    typed = cast("dict[str, object]", instrument)
    source_ticker = typed.get("source_ticker")
    if not isinstance(source_ticker, str) or "." not in source_ticker:
        raise EtfReferenceConfigError(
            "ETF reference config source_ticker requires "
            + "suffixed notation (e.g. 510300.SH)"
        )
    declared = typed.get("facts")
    if not isinstance(declared, dict) or not declared:
        raise EtfReferenceConfigError(
            f"ETF reference config {source_ticker} requires facts"
        )
    facts: list[_Fact] = []
    for field, entry in cast("dict[str, object]", declared).items():
        key = (source_ticker, field)
        if key in seen:
            raise EtfReferenceConfigError(
                f"ETF reference config declares {source_ticker}.{field} twice"
            )
        seen.add(key)
        facts.append(_parse_fact(source_ticker, field, entry))
    return facts


def _parse_fact(source_ticker: str, field: str, entry: object) -> _Fact:
    """解析并校验单条事实声明。"""
    if field not in ETF_REFERENCE_CONFIG_FIELDS:
        raise EtfReferenceConfigError(
            f"ETF reference config {source_ticker} declares "
            + f"unsupported field: {field}"
        )
    if not isinstance(entry, dict):
        raise EtfReferenceConfigError(
            f"ETF reference config {source_ticker}.{field} must be an object"
        )
    typed = cast("dict[str, object]", entry)
    value = _string_entry(source_ticker, field, typed, "value")
    unit = _string_entry(source_ticker, field, typed, "unit")
    effective_from = _string_entry(source_ticker, field, typed, "effective_from")
    basis = _string_entry(source_ticker, field, typed, "basis")
    _require_iso_date(f"{source_ticker}.{field}.effective_from", effective_from)
    if field in _NUMERIC_FIELDS:
        _require_non_negative_number(source_ticker, field, value)
    return _Fact(
        source_ticker=source_ticker,
        field=field,
        value=value,
        unit=unit,
        effective_from=effective_from,
        basis=basis,
    )


def _string_entry(
    source_ticker: str, field: str, entry: dict[str, object], key: str
) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EtfReferenceConfigError(
            f"ETF reference config {source_ticker}.{field} requires {key}"
        )
    return value


def _require_iso_date(label: str, value: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise EtfReferenceConfigError(
            f"ETF reference config {label} must be an ISO date"
        ) from error


def _require_non_negative_number(source_ticker: str, field: str, value: str) -> None:
    try:
        numeric = float(value)
    except ValueError as error:
        raise EtfReferenceConfigError(
            f"ETF reference config {source_ticker}.{field} must be numeric"
        ) from error
    if not isfinite(numeric) or numeric < 0:
        raise EtfReferenceConfigError(
            f"ETF reference config {source_ticker}.{field} "
            + "must be a finite non-negative number"
        )
