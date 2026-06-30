"""Resolution helpers — ticker / benchmark / display-map 统一解析."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_data.services.metadata_service import MetadataService
from ditto_kernel.identity import InstrumentId


@dataclass(frozen=True)
class ResolutionResult:
    """单次遍历 instrument_ids 产生的完整解析结果."""

    tickers: tuple[str, ...]
    id_map: dict[str, InstrumentId]
    display_map: dict[InstrumentId, str]


def resolve_instrument_display(
    instrument_ids: list[int],
    metadata_service: MetadataService,
    *,
    source: str | None = None,
    as_of: str | None = None,
) -> ResolutionResult:
    """将 instrument_id 列表解析为 provider tickers + id_map + display_map。"""
    tickers: list[str] = []
    id_map: dict[str, InstrumentId] = {}
    display_map: dict[InstrumentId, str] = {}

    for iid in instrument_ids:
        instrument_id = InstrumentId(iid)
        instrument = metadata_service.instrument.get_instrument(iid)
        if instrument is not None:
            ticker = instrument.get("ticker", str(iid))
            exchange = instrument.get("exchange", "")
            display_key = f"{ticker}.{exchange}" if exchange else str(iid)
        else:
            display_key = str(iid)
        source_ticker = (
            metadata_service.instrument.get_source_ticker(iid, source, as_of)
            if source is not None
            else None
        )
        key = source_ticker or display_key
        tickers.append(key)
        id_map[key] = instrument_id
        display_map[instrument_id] = display_key

    return ResolutionResult(
        tickers=tuple(tickers),
        id_map=id_map,
        display_map=display_map,
    )


def resolve_benchmark(
    spec_benchmark: str | None,
    metadata_service: MetadataService,
    source: str,
    as_of: str,
    config_benchmark: InstrumentId | None = None,
) -> InstrumentId | None:
    """解析 benchmark：优先使用 config 中的 InstrumentId，否则从 spec 解析。"""
    if config_benchmark is not None:
        return config_benchmark
    if spec_benchmark is None:
        return None
    iid = metadata_service.resolve_instrument_id(spec_benchmark, source, as_of)
    return InstrumentId(iid) if iid is not None else None
