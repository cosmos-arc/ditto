"""Resolution helpers — ticker / benchmark / display-map 统一解析."""

from __future__ import annotations

from ditto_data.services.metadata_service import MetadataService
from ditto_kernel.identity import InstrumentId


def resolve_tickers(
    instrument_ids: list[int],
    metadata_service: MetadataService,
) -> tuple[tuple[str, ...], dict[str, InstrumentId]]:
    """将 instrument_id 列表解析为 tickers 和 id_map。"""
    tickers: list[str] = []
    id_map: dict[str, InstrumentId] = {}
    for iid in instrument_ids:
        instrument_id = InstrumentId(iid)
        instrument = metadata_service.get_instrument(iid)
        if instrument is not None:
            ticker = instrument.get("ticker", str(iid))
            exchange = instrument.get("exchange", "")
            key = f"{ticker}.{exchange}" if exchange else str(iid)
        else:
            key = str(iid)
        tickers.append(key)
        id_map[key] = instrument_id
    return tuple(tickers), id_map


def resolve_display_map(
    instrument_ids: list[int],
    metadata_service: MetadataService,
) -> dict[InstrumentId, str]:
    """构建 InstrumentId → standard_ticker 映射。"""
    display_map: dict[InstrumentId, str] = {}
    for iid in instrument_ids:
        instrument_id = InstrumentId(iid)
        instrument = metadata_service.get_instrument(iid)
        if instrument is not None:
            ticker = instrument.get("ticker", str(iid))
            exchange = instrument.get("exchange", "")
            key = f"{ticker}.{exchange}" if exchange else str(iid)
            display_map[instrument_id] = key
        else:
            display_map[instrument_id] = str(iid)
    return display_map


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
