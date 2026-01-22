"""Tushare 数据源错误处理模块."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from ditto_foundation import logger

from ditto_datahub.sources.base import (
    SourceAuthenticationError,
    SourceFetchError,
    SourceRateLimitError,
)


@contextmanager
def tushare_fetch_error_handler(
    dataset: str,
    api_name: str,
) -> Generator[None, None, None]:
    """
    统一的 Tushare fetch 错误处理上下文管理器。

    将 TushareSource 中的错误处理逻辑提取为独立函数，可复用于其他场景。

    异常处理策略：
    - SourceAuthenticationError: 认证错误直接重新抛出
    - SourceRateLimitError: 限流错误直接重新抛出
    - 其他异常: 包装为 SourceFetchError 并记录日志

    Args:
        dataset: 数据集名称（用于日志和错误消息）
        api_name: API 名称（用于错误消息）

    Yields:
        None

    Raises:
        SourceAuthenticationError: 认证错误直接抛出
        SourceRateLimitError: 限流错误直接抛出
        SourceFetchError: 其他异常包装为 SourceFetchError

    Examples:
        ```python
        with tushare_fetch_error_handler("calendar", "trade_cal"):
            response = client.query(api_name="trade_cal", ...)
            # 处理响应
        ```

    """
    try:
        yield
    except SourceAuthenticationError:
        raise
    except SourceRateLimitError:
        raise
    except Exception as e:
        logger.error(
            f"Tushare {dataset} fetch failed",
            event=f"tushare_{dataset}_fetch_error",
            error=str(e),
            api_name=api_name,
        )
        raise SourceFetchError(
            message=f"Failed to fetch {dataset} from Tushare",
            source="tushare",
            dataset=api_name,
            original_error=str(e),
        ) from e
