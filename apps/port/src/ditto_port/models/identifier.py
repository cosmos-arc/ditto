"""共享标识符解析工具。"""

from ditto_datahub.services.metadata_service import MetadataService

__all__ = ["resolve_instrument_identifier"]


def resolve_instrument_identifier(
    metadata_service: MetadataService,
    *,
    instrument_id: int | None,
    standard_ticker: str | None,
    ticker: str | None,
    source: str = "tushare",
    asset_class: str = "stock",
) -> int | None:
    """
    解析标识符为 canonical instrument_id.

    统一入口，供 API 路由和 CLI 命令共用。
    调用方负责验证至少提供一个标识符。

    Returns:
        解析后的 canonical instrument_id (int)，查不到返回 None.

    """
    return metadata_service.resolve_instrument_identifier(
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        source=source,
        asset_class=asset_class,
    )
