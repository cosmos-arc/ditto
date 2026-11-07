"""Tushare API client with rate limiting and retry."""

from __future__ import annotations

from dataclasses import dataclass, replace

import httpx
import polars as pl
from ditto_platform.foundation import logger
from tenacity import (
    retry,
    retry_if_exception,
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
# 去重合并模式下连续「整页零新行」的回显上限：达到即判定服务端忽略
# offset（整页回显无法收敛），fail-closed（#672）。
_PAGINATION_ZERO_NEW_ECHO_LIMIT = 2


def _page_fingerprint(
    page: pl.DataFrame,
    page_hash_list: list[int],
    current: int | None,
) -> int | None:
    """首页首行指纹：续探时区分「越界回显首页」（#431）与其他回显。"""
    if current is None and page_hash_list:
        return page_hash_list[0]
    return current


@dataclass(frozen=True, slots=True)
class _PageDuplicateContext:
    """一页重复记账的定位上下文（去重合并辅助方法的参数载体，#672）。"""

    api_name: str
    offset: int
    in_page_duplicates: int
    cross_page_duplicates: int


def _append_empty_first_page(pages: list[pl.DataFrame], page: pl.DataFrame) -> None:
    """首页为空时保留原样（含 fields schema 的零行帧，不经过 concat 路径）。"""
    if not pages:
        pages.append(page)


def _warn_in_page_duplicates(
    page: pl.DataFrame,
    page_rows: set[int],
    *,
    api_name: str,
    offset: int,
) -> int:
    """
    页内整行重复记账（返回重复行数）.

    事件型数据集（dividend 等）存在字段全同的真实业务冗余行，区间层
    有 .unique() 兜底——降级告警放行（#196 回补实测单页 2 行真实重复
    被误伤，整 chunk fail-closed）。
    """
    in_page_duplicates = page.height - len(page_rows)
    if in_page_duplicates:
        logger.warning(
            "page contained in-page duplicates; passing through (redundancy)",
            event="tushare_pagination_in_page_duplicates",
            api_name=api_name,
            offset=offset,
            duplicate_rows=in_page_duplicates,
        )
    return in_page_duplicates


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
        fund_portfolio）与 #627 前十股东两榜（top10_holders/
        top10_floatholders）按官方口径归 SPECIAL（最严格档）：
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(
            lambda error: (
                isinstance(error, SourceFetchError)
                and error.details.get("retryable") is not False
            )
        ),
    )
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
                    # 换档几何（第二 attempts）降级为去重合并：边界重叠
                    # （服务端排序不稳定）自愈，零新行回显仍硬拦（#672）。
                    dedup_merge=page_size != primary_page_size,
                    **params,
                )
            except PaginationCorruptionError:
                if page_size != primary_page_size:
                    raise
                shifted = max(page_size - _PAGINATION_RETRY_PAGE_SHIFT, 500)
                if shifted == page_size:
                    raise
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
        dedup_merge: bool = False,
        **params: str | int,
    ) -> pl.DataFrame:
        """
        按显式页宽做 offset 翻页，短页截断续探自愈.

        跨页重复默认 fail-closed 硬拦；``dedup_merge``（换档重试几何）下
        降级为去重合并——丢弃已见行继续翻页（服务端排序不稳定的边界重叠
        自愈，#672），连续两次整页零新行（服务端忽略 offset 的整页回显）
        仍硬拦。
        """
        pages: list[pl.DataFrame] = []
        seen_rows: set[int] = set()
        first_row_hash: int | None = None
        offset = 0
        active_page_size = page_size
        echo_probes = 0
        raw_rows_fetched = 0
        dedup_merge_events = 0
        while True:
            data = self._query(
                api_name, fields, limit=active_page_size, offset=offset, **params
            )
            raw_page = response_to_dataframe(data)
            raw_rows_fetched += raw_page.height
            # 空尾页即取尽；真实服务端越界页返回 fields=[]（零列 schema），
            # 参与后续 concat 会抛 "schema lengths differ"。首页空保留原样
            # 返回（含 fields schema 的零行帧，不经过 concat 路径）。
            if raw_page.height == 0:
                _append_empty_first_page(pages, raw_page)
                break
            page_hash_list = [hash(row) for row in raw_page.iter_rows()]
            page_rows = set(page_hash_list)
            first_row_hash = _page_fingerprint(raw_page, page_hash_list, first_row_hash)
            in_page_duplicates = _warn_in_page_duplicates(
                raw_page, page_rows, api_name=api_name, offset=offset
            )
            # 跨页重复（服务端忽略 offset、排序不稳定、翻页期间源端变更）
            # 是 offset 损坏的直接指纹，默认 fail-closed 硬拦；换档几何上
            # 降级去重合并（#672：etf_nav fund_nav / forecast 端点的边界
            # 重叠换档后仍确定性复发，force 通道被完全阻断）。
            cross_page_duplicates = len(page_rows & seen_rows)
            page = raw_page
            if cross_page_duplicates:
                if dedup_merge:
                    dedup_merge_events += 1
                page, echo_probes = self._merge_cross_duplicate_page(
                    raw_page,
                    page_hash_list,
                    seen_rows,
                    _PageDuplicateContext(
                        api_name=api_name,
                        offset=offset,
                        in_page_duplicates=in_page_duplicates,
                        cross_page_duplicates=cross_page_duplicates,
                    ),
                    dedup_merge=dedup_merge,
                    echo_probes=echo_probes,
                )
                if page is None:
                    # 整页零新行：按回显探测推进一页，由回显连续计数
                    # 决定是否收敛/硬拦。
                    offset += len(raw_page)
                    continue
            else:
                # 无跨页重复的干净页同样解除回显连续计数（correctness F1：
                # 交替「干净页/整页回显」形态下，隔页回显不应累加成连续）。
                echo_probes = 0
            seen_rows |= page_rows
            pages.append(page)
            if len(raw_page) < active_page_size:
                # 短页在「页宽 ≤ 服务端单次上限」时证明取尽；页宽超上限时
                # 是静默截断。续探区分两者并收窄回显语义（#658 批次1），
                # 细节见 _short_page_next_geometry。
                geometry = self._short_page_next_geometry(
                    api_name,
                    fields,
                    page=raw_page,
                    offset=offset,
                    active_page_size=active_page_size,
                    seen_rows=seen_rows,
                    first_row_hash=first_row_hash,
                    **params,
                )
                if geometry is None:
                    break
                active_page_size, offset = geometry
                continue
            offset += len(raw_page)

        if len(pages) == 1:
            result = pages[0]
        else:
            result = pl.concat(pages, how="vertical_relaxed")
        if dedup_merge and dedup_merge_events:
            # correctness F2 终态信号：raw−返回 的差值=被丢弃的跨页重复行；
            # 排序不稳定同时跳行时该机制不感知（offset 翻页的固有盲区，
            # 与旧代码同级），ops 以此事件区分「重叠自愈」与异常放大。
            logger.warning(
                "pagination dedup-merge summary",
                event="tushare_pagination_dedup_merge_summary",
                api_name=api_name,
                dedup_events=dedup_merge_events,
                raw_rows_fetched=raw_rows_fetched,
                rows_returned=result.height,
                dropped_rows=raw_rows_fetched - result.height,
            )
        return result

    @staticmethod
    def _merge_cross_duplicate_page(
        raw_page: pl.DataFrame,
        page_hash_list: list[int],
        seen_rows: set[int],
        page_ctx: _PageDuplicateContext,
        *,
        dedup_merge: bool,
        echo_probes: int,
    ) -> tuple[pl.DataFrame | None, int]:
        """
        处理一页的跨页重复（#672）.

        主几何（``dedup_merge=False``）维持 fail-closed 硬拦——跨页重复
        是 offset 损坏的直接指纹；换档重试几何降级为去重合并：丢弃已见
        行继续翻页（服务端排序不稳定的边界重叠自愈），整页零新行连续
        :data:`_PAGINATION_ZERO_NEW_ECHO_LIMIT` 次（服务端忽略 offset 的
        整页回显）仍硬拦。返回 (追加页, echo_probes 新值)；追加页为
        None 表示整页零新行（调用方推进一页续探）。
        """
        if not dedup_merge:
            raise PaginationCorruptionError(
                message=(
                    f"Tushare {page_ctx.api_name} pagination returned "
                    f"duplicate rows at offset={page_ctx.offset} "
                    f"(in-page={page_ctx.in_page_duplicates}, "
                    f"cross-page={page_ctx.cross_page_duplicates}): "
                    "服务端忽略 offset、排序不稳定或翻页期间源数据变更"
                ),
                source="tushare",
            )
        new_mask = pl.Series(
            [row_hash not in seen_rows for row_hash in page_hash_list],
            dtype=pl.Boolean,
        )
        new_count = int(new_mask.sum())
        logger.warning(
            "pagination cross-page overlap; dedup-merging and continuing",
            event="tushare_pagination_dedup_merge",
            api_name=page_ctx.api_name,
            offset=page_ctx.offset,
            cross_page_duplicates=page_ctx.cross_page_duplicates,
            # correctness F3：以 mask 实数为准（页内重复行不虚增 new_rows）。
            new_rows=new_count,
        )
        if new_count:
            return raw_page.filter(new_mask), 0
        if echo_probes + 1 >= _PAGINATION_ZERO_NEW_ECHO_LIMIT:
            raise PaginationCorruptionError(
                message=(
                    f"Tushare {page_ctx.api_name} pagination returned "
                    f"duplicate rows at offset={page_ctx.offset} "
                    "(dedup-merge echo, consecutive zero-new pages): "
                    "服务端忽略 offset, 整页回显无法收敛"
                ),
                source="tushare",
            )
        return None, echo_probes + 1

    def _short_page_next_geometry(
        self,
        api_name: str,
        fields: str,
        *,
        page: pl.DataFrame,
        offset: int,
        active_page_size: int,
        seen_rows: set[int],
        first_row_hash: int | None,
        **params: str | int,
    ) -> tuple[int, int] | None:
        """
        短页后的取数几何：None=取尽；(页宽, offset)=按观测上限续拉。

        短页在「页宽 ≤ 服务端单次上限」时证明取尽；页宽超上限时是静默
        截断（离线复现：2501 行源、cap 2000、limit 9000 仅取回 2000）。
        续探一行区分两者：offset 处出现未见过的行 = 截断实锤，按观测到
        的服务端上限降页宽续拉（#625 可检测条款）。探针为首页首行回显 =
        越界回显形态（#431 实测），按取尽处理；已见非首行回显 = offset
        失效证据不足，不以模糊探针判取尽（#658 批次1）。续拉整页仍经
        现有跨页重复拒绝/换档去重及连续回显守卫（#708）。
        """
        try:
            more = self._probe_unseen_row_beyond(
                api_name,
                fields,
                offset=offset + len(page),
                seen_rows=seen_rows,
                first_row_hash=first_row_hash,
                **params,
            )
        except PaginationCorruptionError:
            # A one-row probe can repeat a boundary row while a full page
            # still contains new data. Only the guarded continuation can
            # establish exhaustion; the probe itself cannot.
            logger.warning(
                "ambiguous tail probe; continuing with guarded full page",
                event="tushare_pagination_probe_continuation",
                api_name=api_name,
                offset=offset + len(page),
            )
            return active_page_size, offset + len(page)
        if not more:
            return None
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
        return len(page), offset + len(page)

    def _probe_unseen_row_beyond(
        self,
        api_name: str,
        fields: str,
        *,
        offset: int,
        seen_rows: set[int],
        first_row_hash: int | None,
        **params: str | int,
    ) -> bool:
        """
        短页之后的续探：offset 处再取一行，区分三种形态。

        - 空页 / 首行回显（#431 实测的越界回显首页形态）：取尽，返回
          False。回显判定的独立完整性依据＝此前各页跨页无重复已证明
          服务端在已走区间尊重 offset，而越界回显恰好从首页首行开始；
          真截断的续探行不可能与已取回行重叠（一致 offset 分页无重叠）。
        - 未见行：仍有后续数据（服务端截断），返回 True 交由调用方
          按观测上限降页宽续拉。
        - 已见行但不含首页首行：offset 失效且不构成越界回显证据，
          抛 PaginationCorruptionError——不能仅凭「行已见过」判取尽并
          发布 COMPLETE（#658 批次1 / #653 反例）。

        探测请求自身失败不再吞掉（#653）：SourceFetchError 沿 query()
        的既有 tenacity 重试传播——一次瞬态失败重试后完整取回，持续
        失败最终以 RetryError 失败，不发布 COMPLETE。
        """
        data = self._query(api_name, fields, limit=1, offset=offset, **params)
        probe = response_to_dataframe(data)
        if probe.height == 0:
            return False
        probe_rows = {hash(row) for row in probe.iter_rows()}
        if probe_rows <= seen_rows:
            if first_row_hash is not None and first_row_hash in probe_rows:
                return False
            raise PaginationCorruptionError(
                message=(
                    f"Tushare {api_name} truncation probe at offset={offset} "
                    "returned already-seen rows that are not the documented "
                    "out-of-bounds first-page echo (#431): cannot prove "
                    "exhaustion, refusing to publish truncated data as "
                    "complete"
                ),
                source="tushare",
            )
        return True

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
