"""摄取后置处理 — list_date 推断、游标更新、冻结点创建、错误处理."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, cast

import httpx
import polars as pl
from ditto_data.errors import (
    NetworkError,
    SourceFetchError,
)
from ditto_data.ingestion.freeze_service import FreezeService
from ditto_data.ingestion.ingestion_cursor_service import IngestionCursorService
from ditto_data.models.ingestion import IngestionResult
from ditto_platform.foundation import OnDuplicate, WriteResult, logger

from ditto_application.contracts import CheckDataQualityCommand
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.list_date_inference import (
    ListDateInferenceService,
)
from ditto_application.processes.ingestion.ports import QualityCheckerProtocol
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler

__all__ = [
    "create_freeze_point",
    "handle_fetch_error",
    "process_fetched_data",
    "run_list_date_inference",
    "run_post_ingest_hooks",
    "safe_side_effect",
    "update_ingestion_cursor",
    "write_data_safe",
]


def run_list_date_inference(
    list_date_inference: ListDateInferenceService,
    dataset: str,
) -> None:
    """
    在 basic 数据摄取后执行 list_date 推断补偿。

    针对 list_date 为 NULL 的证券，从历史行情数据推断上市日期。
    """
    asset_class_map = {
        "stock_basic": "stock",
        "etf_basic": "etf",
        "index_basic": "index",
    }

    asset_class = asset_class_map.get(dataset)
    if asset_class is None:
        return

    try:
        logger.info(
            "Running list_date inference after basic ingestion",
            event="list_date_inference_start",
            dataset=dataset,
            asset_class=asset_class,
        )
        count = list_date_inference.infer_for_asset_class(
            cast('Literal["stock", "etf", "index"]', asset_class)
        )
        logger.info(
            "Completed list_date inference",
            event="list_date_inference_complete",
            dataset=dataset,
            asset_class=asset_class,
            inferred_count=count,
        )
    except (
        pl.exceptions.ComputeError,
        pl.exceptions.SchemaError,
        ValueError,
        KeyError,
        TypeError,
        httpx.NetworkError,
        httpx.TimeoutException,
    ) as e:
        logger.warning(
            f"list_date inference failed for {asset_class}",
            event="list_date_inference_error",
            dataset=dataset,
            asset_class=asset_class,
            error=str(e),
        )
    except Exception:
        logger.exception(
            "Unexpected error in list_date inference",
            event="list_date_inference_error",
            dataset=dataset,
            asset_class=asset_class,
        )


def process_fetched_data(  # noqa: PLR0913 — 编排函数：DI 服务分散在各字段，引入 dataclass 需改动 coordinator + 测试
    df: pl.DataFrame,
    dataset: str,
    trade_date: str,
    force: bool,
    *,
    result_handler: IngestionResultHandler,
    data_writer: IngestionDataWriter,
    quality_checker: QualityCheckerProtocol | None,
    list_date_inference: ListDateInferenceService,
    cursor_service: IngestionCursorService | None,
    freeze_service: FreezeService | None,
    source_name: str,
) -> IngestionResult:
    """处理获取的数据：DQ 检查 + 写入 + 后置钩子."""
    if df.is_empty():
        return result_handler.handle_empty_data(dataset, trade_date)

    if quality_checker is not None:
        checked_df, should_block = quality_checker.handle(
            CheckDataQualityCommand(
                df=df,
                dataset=dataset,
                context={"trade_date": trade_date},
            ),
        )
        if should_block:
            return result_handler.handle_dq_blocked(
                dataset,
                trade_date,
                WriteResult(
                    file_path="",
                    checksum="",
                    rows_written=0,
                    rows_total=df.height,
                    blocked=True,
                ),
            )
        df = checked_df

    on_duplicate = OnDuplicate.KEEP_LAST if force else OnDuplicate.ERROR

    write_result = write_data_safe(
        dataset,
        df,
        trade_date,
        on_duplicate,
        result_handler=result_handler,
        data_writer=data_writer,
    )
    if isinstance(write_result, IngestionResult):
        return write_result

    if write_result.blocked:
        return result_handler.handle_dq_blocked(dataset, trade_date, write_result)

    run_list_date_inference(list_date_inference, dataset)
    run_post_ingest_hooks(
        dataset,
        trade_date,
        cursor_service=cursor_service,
        freeze_service=freeze_service,
        source_name=source_name,
    )

    return result_handler.handle_success(dataset, trade_date, df, write_result)


def run_post_ingest_hooks(
    dataset: str,
    trade_date: str,
    *,
    cursor_service: IngestionCursorService | None,
    freeze_service: FreezeService | None,
    source_name: str,
) -> None:
    """执行摄取后的副作用：游标更新、冻结点创建。"""
    update_ingestion_cursor(
        dataset,
        trade_date,
        cursor_service=cursor_service,
        source_name=source_name,
    )
    create_freeze_point(
        dataset,
        trade_date,
        freeze_service=freeze_service,
    )


def safe_side_effect(
    action: Callable[[], object],
    *,
    log_tag: str,
    event: str,
    dataset: str,
    trade_date: str,
) -> None:
    """执行副作用操作，失败仅记录警告，不影响主流程。"""
    try:
        action()
    except (ValueError, KeyError, TypeError, OSError) as e:
        logger.warning(
            log_tag,
            event=event,
            dataset=dataset,
            trade_date=trade_date,
            error_type=type(e).__name__,
            error=str(e),
        )
    except Exception:
        logger.exception(
            f"{log_tag}_unexpected",
            event=event,
            dataset=dataset,
            trade_date=trade_date,
        )


def update_ingestion_cursor(
    dataset: str,
    trade_date: str,
    *,
    cursor_service: IngestionCursorService | None,
    source_name: str,
) -> None:
    """更新摄入游标（失败仅记录警告，不影响主流程）。"""
    if cursor_service is None:
        return
    svc = cursor_service
    safe_side_effect(
        lambda: svc.update_cursor(
            dataset=dataset,
            source=source_name,
            last_success=trade_date,
            last_attempted=trade_date,
        ),
        log_tag="cursor_update_failed",
        event="cursor_update_error",
        dataset=dataset,
        trade_date=trade_date,
    )


def create_freeze_point(
    dataset: str,
    trade_date: str,
    *,
    freeze_service: FreezeService | None,
) -> None:
    """创建冻结点 — 轻量级版本追踪（失败仅记录警告，不影响主流程）。"""
    if freeze_service is None:
        return
    svc = freeze_service
    safe_side_effect(
        lambda: svc.create_freeze(
            freeze_id=f"{dataset}_{trade_date}",
            description=f"Auto-freeze: {dataset} @ {trade_date}",
            datasets=[dataset],
        ),
        log_tag="freeze_create_failed",
        event="freeze_create_error",
        dataset=dataset,
        trade_date=trade_date,
    )


def write_data_safe(  # noqa: PLR0913 — 统一写入入口：result_handler + data_writer 为 DI 服务，无法进一步收敛
    dataset: str,
    df: pl.DataFrame,
    trade_date: str,
    on_duplicate: OnDuplicate,
    *,
    result_handler: IngestionResultHandler,
    data_writer: IngestionDataWriter,
    source_ticker: str | None = None,
    event_suffix: str = "",
) -> WriteResult | IngestionResult:
    """安全写入数据，统一异常处理。"""
    try:
        return data_writer.write_data(dataset, df, trade_date, on_duplicate)
    except (
        pl.exceptions.ComputeError,
        pl.exceptions.SchemaError,
        ValueError,
        KeyError,
        TypeError,
        OSError,
    ) as e:
        logger.warning(
            f"write_data_failed{event_suffix}",
            event="write_data_error",
            dataset=dataset,
            trade_date=trade_date,
            **({"source_ticker": source_ticker} if source_ticker else {}),
            error_type=type(e).__name__,
            error=str(e),
        )
        return result_handler.handle_unknown_error(dataset, trade_date, e)
    except Exception as e:
        logger.exception(
            f"write_data_failed{event_suffix}_unexpected",
            event="write_data_error",
            dataset=dataset,
            trade_date=trade_date,
            **({"source_ticker": source_ticker} if source_ticker else {}),
            error_type=type(e).__name__,
        )
        return result_handler.handle_unknown_error(dataset, trade_date, e)


def handle_fetch_error(
    error: Exception,
    *,
    dataset: str,
    date_identifier: str,
    context: str,
    log_tag: str,
    source_name: str,
    result_handler: IngestionResultHandler,
) -> IngestionResult:
    """统一的 fetch 错误处理。"""
    if isinstance(error, (httpx.NetworkError, httpx.TimeoutException)):
        logger.exception(
            f"network_error_{log_tag}",
            dataset=dataset,
            error_type=type(error).__name__,
        )
        network_error = NetworkError.from_httpx(
            error=error,
            source=source_name,
            context=context,
        )
        fetch_error = SourceFetchError(
            message=str(network_error),
            source=source_name,
            cause=network_error,
        )
        return result_handler.handle_fetch_error(dataset, date_identifier, fetch_error)

    if isinstance(error, SourceFetchError):
        normalized = _normalize_source_fetch_error(error)
        return result_handler.handle_fetch_error(dataset, date_identifier, normalized)

    logger.exception(
        f"unexpected_error_{log_tag}",
        dataset=dataset,
        error_type=type(error).__name__,
    )
    return result_handler.handle_unknown_error(dataset, date_identifier, error)


def _normalize_source_fetch_error(error: Exception) -> SourceFetchError:
    """Normalize external fetch error into app-level SourceFetchError."""
    source_name = getattr(error, "source", "unknown")
    return SourceFetchError(message=str(error), source=str(source_name))
