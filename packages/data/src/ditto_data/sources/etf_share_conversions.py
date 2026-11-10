"""
维护者确认的 ETF 份额折算声明文件（#762）。

外部数据源没有 ETF 折算事件接口（tushare fund_div 明确不含折算），
发行人公告是唯一权威口径；本模块把维护者确认的声明式配置作为合法
来源（``Source.CONFIG``，仿 :mod:`ditto_data.sources.reference_config`）
读成可摄取的长表。声明不覆盖全域完整性：未声明的折算日仍被执行层
因子跳变守卫 fail-closed 拒绝，观察缺失不推断。
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
    "EtfShareConversionsConfigError",
    "EtfShareConversionsConfigSource",
    "get_default_etf_share_conversions_config_path",
]

_FRAME_COLUMNS: tuple[str, ...] = (
    "source_ticker",
    "ratio",
    "announcement_date",
    "effective_date",
    "basis",
    "rounding_note",
)

_FRAME_SCHEMA: dict[str, pl.DataType] = {
    "source_ticker": pl.String,
    "ratio": pl.Float64,
    "announcement_date": pl.String,
    "effective_date": pl.String,
    "basis": pl.String,
    "rounding_note": pl.String,
}


class EtfShareConversionsConfigError(ValueError):
    """声明文件结构或取值非法（fail closed，不静默丢弃）。"""


@dataclass(frozen=True)
class _DeclaredConversion:
    """一条已确认的份额折算声明。"""

    source_ticker: str
    ratio: float
    announcement_date: str
    effective_date: str
    basis: str
    rounding_note: str


def get_default_etf_share_conversions_config_path(config_root: Path) -> Path:
    """返回跨环境默认声明文件路径（config/default 层）。"""
    return config_root / "config" / "default" / "etf_share_conversions.json"


class EtfShareConversionsConfigSource:
    """读取并校验 ETF 份额折算声明文件，产出确定性长表。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """声明文件路径（证据记录用）。"""
        return self._path

    def fetch_etf_share_conversions(self) -> pl.DataFrame:
        """解析声明文件为 ``_FRAME_COLUMNS`` 列的确定性长表。"""
        conversions = self._load_declarations()
        frame = pl.DataFrame(
            {
                column: [getattr(item, column) for item in conversions]
                for column in _FRAME_COLUMNS
            },
            schema=_FRAME_SCHEMA,
        )
        logger.info(
            "ETF share conversions config loaded",
            event="etf_share_conversions_config_loaded",
            path=str(self._path),
            row_count=frame.height,
        )
        return frame

    def _load_declarations(self) -> list[_DeclaredConversion]:
        declarations: list[_DeclaredConversion] = []
        seen: set[tuple[str, str]] = set()
        for entry in self._load_entries():
            declared = _parse_conversion(entry)
            key = (declared.source_ticker, declared.effective_date)
            if key in seen:
                raise EtfShareConversionsConfigError(
                    f"ETF share conversions config declares {key[0]} at "
                    + f"{key[1]} twice"
                )
            seen.add(key)
            declarations.append(declared)
        # 同 (ticker, effective_date) 的第二次声明即拒绝——重复与冲突事实
        # 都不允许静默合并，声明文件必须保持策展状态。
        declarations.sort(key=lambda item: (item.source_ticker, item.effective_date))
        return declarations

    def _load_entries(self) -> list[object]:
        try:
            raw = self._path.read_bytes()
        except OSError as error:
            raise EtfShareConversionsConfigError(
                f"ETF share conversions config is unreadable: {self._path}"
            ) from error
        try:
            document: object = orjson.loads(raw)
        except orjson.JSONDecodeError as error:
            raise EtfShareConversionsConfigError(
                f"ETF share conversions config is not valid JSON: {self._path}"
            ) from error
        if not isinstance(document, dict):
            raise EtfShareConversionsConfigError(
                "ETF share conversions config must be an object"
            )
        typed = cast("dict[str, object]", document)
        conversions = typed.get("conversions")
        if not isinstance(conversions, list) or not conversions:
            raise EtfShareConversionsConfigError(
                "ETF share conversions config requires a non-empty conversions list"
            )
        confirmed_at = typed.get("confirmed_at")
        if not isinstance(confirmed_at, str):
            raise EtfShareConversionsConfigError(
                "ETF share conversions config requires a confirmed_at declaration date"
            )
        _require_iso_date("confirmed_at", confirmed_at)
        return cast("list[object]", conversions)


def _parse_conversion(entry: object) -> _DeclaredConversion:
    """解析并校验单条折算声明。"""
    if not isinstance(entry, dict):
        raise EtfShareConversionsConfigError(
            "ETF share conversions config entries must be objects"
        )
    typed = cast("dict[str, object]", entry)
    source_ticker = typed.get("source_ticker")
    if not isinstance(source_ticker, str) or "." not in source_ticker:
        raise EtfShareConversionsConfigError(
            "ETF share conversions config source_ticker requires "
            + "suffixed notation (e.g. 159941.SZ)"
        )
    ratio = typed.get("ratio")
    if (
        isinstance(ratio, bool)
        or not isinstance(ratio, (int, float))
        or not isfinite(float(ratio))
        or float(ratio) <= 0
        or float(ratio) == 1
    ):
        raise EtfShareConversionsConfigError(
            f"ETF share conversions config {source_ticker} requires a finite "
            + "ratio > 0 and != 1 (4.0 means one old share becomes four)"
        )
    announcement_date = typed.get("announcement_date")
    if not isinstance(announcement_date, str):
        raise EtfShareConversionsConfigError(
            f"ETF share conversions config {source_ticker} requires "
            + "announcement_date as the PIT-knowable declaration date"
        )
    _require_iso_date(f"{source_ticker}.announcement_date", announcement_date)
    effective_date = typed.get("effective_date")
    if not isinstance(effective_date, str):
        raise EtfShareConversionsConfigError(
            f"ETF share conversions config {source_ticker} requires "
            + "effective_date as the ex-rights session"
        )
    _require_iso_date(f"{source_ticker}.effective_date", effective_date)
    if announcement_date >= effective_date:
        raise EtfShareConversionsConfigError(
            f"ETF share conversions config {source_ticker} requires "
            + "announcement_date before effective_date"
        )
    basis = typed.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        raise EtfShareConversionsConfigError(
            f"ETF share conversions config {source_ticker} requires basis"
        )
    rounding_note = typed.get("rounding_note")
    if not isinstance(rounding_note, str) or not rounding_note.strip():
        raise EtfShareConversionsConfigError(
            f"ETF share conversions config {source_ticker} requires "
            + "rounding_note about fractional-share handling"
        )
    return _DeclaredConversion(
        source_ticker=source_ticker,
        ratio=float(ratio),
        announcement_date=announcement_date,
        effective_date=effective_date,
        basis=basis,
        rounding_note=rounding_note,
    )


def _require_iso_date(label: str, value: str) -> None:
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("date must use YYYY-MM-DD")
    except ValueError as error:
        raise EtfShareConversionsConfigError(
            f"ETF share conversions config {label} must be an ISO date"
        ) from error
