"""Tushare API client with rate limiting and retry."""

from __future__ import annotations

from dataclasses import replace

import httpx
import polars as pl
from ditto_platform.foundation import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ditto_data.config import DataSourceSettings
from ditto_data.sources.base import (
    PaginationCorruptionError,
    SourceConfigurationError,
    SourceFetchError,
)
from ditto_data.sources.tushare.utils.http_utils import (
    map_http_error,
    response_to_dataframe,
    validate_tushare_response,
)
from ditto_data.sources.tushare.utils.pagination import resolve_page_size
from ditto_data.sources.tushare.utils.rate_limiter import (
    TushareAPIGroup,
    TushareRateLimitConfig,
    TushareRateLimiter,
)

# 跨页重复换几何重试的页宽位移；下限 500 防止默认 2000 页宽端点被移到
# 过小页宽（页数增多、每页 offset 损坏暴露面反而变大）。
_PAGINATION_RETRY_PAGE_SHIFT = 1000

# 截断自愈的页宽下限：服务端单次上限低于此值时无已知端点先例，降页宽
# 循环不再收敛，fail-closed 拒收。
_PAGINATION_MIN_PAGE_SIZE = 500


def _get_tushare_token(token: str | None) -> str:
    """Resolve Tushare token from explicit input/settings."""
    if token:
        logger.debug(
            "Token loaded from parameter",
            event="token_loaded",
            source="parameter",
        )
        return token

    raise SourceConfigurationError(
        message=(
            "Tushare token not configured. Provide token via settings or parameter."
        )
    )


def _rate_limit_config(settings: DataSourceSettings) -> TushareRateLimitConfig:
    """
    Resolve the declared transport tier without changing defaults.

    档位区分 transport 权益（#431）：``free``/``paid`` 是代理 transport
    （t.xiaodefa.top）承诺的档位，不是官方账号积分档；官方直连账号应选
    ``official_120``（50/分）或 ``official_15000``（500/分）。
    """
    profile = settings.rate_limit_profile.strip().lower()
    if profile in {"free", "proxy_free"}:
        config = TushareRateLimitConfig.free()
    elif profile in {"paid", "premium", "proxy_paid"}:
        config = TushareRateLimitConfig.paid()
    elif profile == "conservative":
        config = TushareRateLimitConfig.conservative()
    elif profile == "official_120":
        config = TushareRateLimitConfig.official_120()
    elif profile == "official_15000":
        config = TushareRateLimitConfig.official_15000()
    else:
        raise SourceConfigurationError(
            message=f"Unsupported Tushare rate limit profile: {profile!r}"
        )
    return replace(
        config,
        global_rate=(settings.rate_limit_global_rate or config.global_rate),
        daily_rate=(settings.rate_limit_daily_rate or config.daily_rate),
        # 日配额覆盖（#507 G1）：显式设置优先，None 沿用档位默认
        # （官方档 100000/天，代理档 None 无约束）
        daily_quota=(
            settings.rate_limit_daily_quota
            if settings.rate_limit_daily_quota is not None
            else config.daily_quota
        ),
    )


class TushareClient:
    """
    Tushare Pro API client.

    Features:
    - Token authentication from settings or explicit parameter
    - Multi-level rate limiting using limits library
    - Retry with exponential backoff (Tenacity)
    - Error handling and logging
    - Configurable via DataSourceSettings

    Attributes:
        _token: Tushare API token.
        _limiter: Rate limiter instance.
        _settings: Data source configuration.

    """

    def __init__(
        self,
        settings: DataSourceSettings,
        token: str | None = None,
        rate_config: TushareRateLimitConfig | None = None,
    ) -> None:
        """
        Initialize Tushare client.

        Args:
            settings: 数据源配置，包含 URL/timeout 等参数.
            token: API token（可选，优先于 settings 中的 token）。
            rate_config: 限流配置(默认免费账户).

        Raises:
            SourceConfigurationError: If token not found.

        """
        # 存储 settings
        self._settings = settings

        # Get token with fallback chain
        # 优先使用 settings 中的 token（如果设置）
        token_to_use = token or self._settings.tushare_token or None
        self._token = _get_tushare_token(token_to_use if token_to_use else None)

        # 配置限流器(默认免费账户)
        config = rate_config or _rate_limit_config(settings)
        self._limiter = TushareRateLimiter(config)

        # Initialize HTTP client with settings
        self._client = httpx.Client(
            base_url=self._settings.http_base_url,
            timeout=self._settings.http_timeout,
            headers={"Content-Type": "application/json"},
        )

        logger.debug(
            "TushareClient initialized",
            event="tushare_client_init",
            base_url=self._settings.http_base_url,
            timeout=self._settings.http_timeout,
            rate_config=config,
        )

    def _get_api_group(self, api_name: str) -> TushareAPIGroup:
        """
        根据 API 名称返回分组.

        #518-#523 增补端点（moneyflow/cyq_perf/hk_hold/hsgt_top10/
        limit_list_d/top_list/top_inst/fina_indicator/fund_share/
        fund_portfolio）按官方口径归 SPECIAL（最严格档）：
        - cyq_perf 是 15000 积分档特色数据（无总量限制、按分钟限频）；
        - 其余端点官方文档均为单一限频档，未核实更宽配额前不放宽。
        """
        if api_name in ["daily", "weekly", "monthly"]:
            return TushareAPIGroup.DAILY
        elif api_name.startswith("f_") or api_name.startswith("adj"):
            return TushareAPIGroup.DERIVED
        elif api_name in ["trade_cal", "pro_bar", "stock_basic"]:
            return TushareAPIGroup.BASIC
        else:
            return TushareAPIGroup.SPECIAL

    def _query(
        self,
        api_name: str,
        fields: str,
        **params: str | int,
    ) -> dict[str, object]:
        """
        执行 HTTP 查询并返回原始 JSON。

        Args:
            api_name: API 名称
            fields: 逗号分隔的字段名
            **params: API 参数

        Returns:
            Tushare API 响应的 data 字段

        Raises:
            SourceAuthenticationError: 认证失败
            SourceRateLimitError: 限流
            SourceFetchError: 其他错误

        """
        # 确定分组并进行限流检查
        group = self._get_api_group(api_name)
        self._limiter.wait_if_needed(group)

        try:
            logger.debug(
                "Tushare HTTP request",
                event="tushare_http_request",
                api_name=api_name,
            )

            # 构建请求体
            request_body = {
                "api_name": api_name,
                "token": self._token,
                "params": params,
                "fields": fields,
            }

            # 发送 HTTP POST 请求
            response = self._client.post("/", json=request_body)

            # 检查 HTTP 状态码 (会针对 4xx/5xx 抛出 HTTPStatusError)
            response.raise_for_status()

            # 解析 JSON
            response_json = response.json()

            # 验证响应并返回 data 字段
            data = validate_tushare_response(response_json)

            logger.debug(
                "Tushare HTTP request success",
                event="tushare_http_success",
                api_name=api_name,
            )

            return data

        except httpx.HTTPStatusError as e:
            # HTTP 状态码错误,映射到相应异常
            map_http_error(e, api_name)

        except (httpx.NetworkError, httpx.TimeoutException) as e:
            # 网络错误和超时,映射到 SourceFetchError
            map_http_error(e, api_name)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(SourceFetchError),
    )
    def query(
        self,
        api_name: str,
        fields: str,
        **params: str | int,
    ) -> pl.DataFrame:
        """
        Query Tushare API with rate limiting, retry and offset pagination.

        按端点契约页宽（utils/pagination.py）翻页；页宽不超过服务端
        单次上限时，短页才可作为取尽条件，避免大结果集被静默截断。
        短页后追加一行续探（#625 分页截断可检测）：offset 之后仍有行
        即截断实锤，按观测到的服务端上限降页宽续拉，不静默丢弃。

        Args:
            api_name: API name (e.g., "trade_cal", "daily").
            fields: Comma-separated field names.
            **params: API parameters.

        Returns:
            polars DataFrame

        Raises:
            SourceRateLimitError: If rate limit exceeded after retries.
            SourceAuthenticationError: If authentication fails.
            SourceFetchError: If query fails after retries, or pagination
                returns cross-page duplicate rows（服务端忽略 offset / 排序不稳定 /
                翻页期间源端变更，拒绝静默截断或无限翻页），或服务端单次
                上限低于页宽下限导致截断无法自愈。页内整行重复是
                事件型数据集的真实业务冗余，放行并告警。

        """
        if "limit" in params or "offset" in params:
            # 调用方自管分页时保持单页语义
            data = self._query(api_name, fields, **params)
            return response_to_dataframe(data)

        # 跨页重复是 offset 损坏的指纹，fail-closed 硬拦；但排序不稳定在
        # 特定边界位置可确定性复发（#196 实测 balancesheet_vip 2020Q4 期
        # 在 offset=9000 恒重 1 行、offset=8000 干净）。换页宽几何重试一次
        # ——守卫在第二几何上同样生效，真 offset 损坏（整页重发）仍拒收。
        primary_page_size = resolve_page_size(api_name)
        page_size = primary_page_size
        while True:
            try:
                return self._query_with_offset_pagination(
                    api_name,
                    fields,
                    page_size=page_size,
                    **params,
                )
            except PaginationCorruptionError:
                if page_size != primary_page_size:
                    raise
                shifted = max(page_size - _PAGINATION_RETRY_PAGE_SHIFT, 500)
                logger.warning(
                    "pagination cross-page duplicates; retrying with shifted page size",
                    event="tushare_pagination_shifted_page_retry",
                    api_name=api_name,
                    primary_page_size=primary_page_size,
                    retry_page_size=shifted,
                )
                page_size = shifted

    def _query_with_offset_pagination(
        self,
        api_name: str,
        fields: str,
        *,
        page_size: int,
        **params: str | int,
    ) -> pl.DataFrame:
        """按显式页宽做 offset 翻页，跨页重复行 fail-closed，短页截断续探自愈。"""
        pages: list[pl.DataFrame] = []
        seen_rows: set[int] = set()
        offset = 0
        active_page_size = page_size
        while True:
            data = self._query(
                api_name, fields, limit=active_page_size, offset=offset, **params
            )
            page = response_to_dataframe(data)
            # 空尾页即取尽；真实服务端越界页返回 fields=[]（零列 schema），
            # 参与后续 concat 会抛 "schema lengths differ"。首页空保留原样
            # 返回（含 fields schema 的零行帧，不经过 concat 路径）。
            if page.height == 0:
                if not pages:
                    pages.append(page)
                break
            page_rows = {hash(row) for row in page.iter_rows()}
            # 页内整行重复：事件型数据集（dividend 等）存在字段全同的真实
            # 业务冗余行，区间层有 .unique() 兜底——降级告警放行（#196 回补
            # 实测单页 2 行真实重复被误伤，整 chunk fail-closed）。
            in_page_duplicates = page.height - len(page_rows)
            if in_page_duplicates:
                logger.warning(
                    "page contained in-page duplicates; passing through (redundancy)",
                    event="tushare_pagination_in_page_duplicates",
                    api_name=api_name,
                    offset=offset,
                    duplicate_rows=in_page_duplicates,
                )
            # 跨页重复（服务端忽略 offset、排序不稳定、翻页期间源端变更）
            # 是 offset 损坏的直接指纹，维持 fail-closed 硬拦。
            cross_page_duplicates = len(page_rows & seen_rows)
            if cross_page_duplicates:
                raise PaginationCorruptionError(
                    message=(
                        f"Tushare {api_name} pagination returned duplicate rows "
                        f"at offset={offset} "
                        f"(in-page={in_page_duplicates}, "
                        f"cross-page={cross_page_duplicates}): "
                        "服务端忽略 offset、排序不稳定或翻页期间源数据变更"
                    ),
                    source="tushare",
                )
            seen_rows |= page_rows
            pages.append(page)
            if len(page) < active_page_size:
                # 短页在「页宽 ≤ 服务端单次上限」时证明取尽；页宽超上限时
                # 是静默截断（离线复现：2501 行源、cap 2000、limit 9000 仅
                # 取回 2000）。续探一行区分两者：offset 处出现未见过的行 =
                # 截断实锤，按观测到的服务端上限降页宽续拉（#625 可检测
                # 条款）。探针行已见于已见集合 = 越界回显首页形态
                # （#431 offset 损坏），按取尽处理，交由既有跨页重复守卫。
                if self._probe_unseen_row_beyond(
                    api_name,
                    fields,
                    offset=offset + len(page),
                    seen_rows=seen_rows,
                    **params,
                ):
                    if len(page) < _PAGINATION_MIN_PAGE_SIZE:
                        raise SourceFetchError(
                            message=(
                                f"Tushare {api_name} pagination truncated below "
                                f"floor: page={len(page)} at offset={offset} "
                                f"but more rows exist (server cap < "
                                f"{_PAGINATION_MIN_PAGE_SIZE})"
                            ),
                            source="tushare",
                        )
                    logger.warning(
                        "pagination truncated by server cap; shrinking page size",
                        event="tushare_pagination_truncation_detected",
                        api_name=api_name,
                        requested_page_size=active_page_size,
                        server_cap=len(page),
                        offset=offset,
                    )
                    active_page_size = len(page)
                    offset += len(page)
                    continue
                break
            offset += len(page)

        if len(pages) == 1:
            return pages[0]
        return pl.concat(pages, how="vertical_relaxed")

    def _probe_unseen_row_beyond(
        self,
        api_name: str,
        fields: str,
        *,
        offset: int,
        seen_rows: set[int],
        **params: str | int,
    ) -> bool:
        """
        短页之后的续探：offset 处再取一行，判断是否存在未见过的后续行。

        探测请求自身失败时按取尽处理（告警可见）：探测是检测增益，不让
        一次额外请求的瞬态失败否决已经取回的数据。
        """
        try:
            data = self._query(api_name, fields, limit=1, offset=offset, **params)
        except SourceFetchError:
            logger.warning(
                "truncation probe failed; assuming exhausted",
                event="tushare_pagination_probe_failed",
                api_name=api_name,
                offset=offset,
            )
            return False
        probe = response_to_dataframe(data)
        if probe.height == 0:
            return False
        probe_rows = {hash(row) for row in probe.iter_rows()}
        return not probe_rows.issubset(seen_rows)

    def close(self) -> None:
        """
        显式关闭 HTTP 客户端.

        释放网络资源，推荐在 with 语句中使用或手动调用。
        """
        if hasattr(self, "_client"):
            self._client.close()

    def __enter__(self) -> TushareClient:
        """支持上下文管理器协议（with 语句）。"""
        return self

    def __exit__(self, *args: object) -> None:
        """退出上下文时关闭 HTTP 客户端."""
        self.close()

    def __del__(self) -> None:
        """清理 HTTP 客户端."""
        if hasattr(self, "_client"):
            self._client.close()
