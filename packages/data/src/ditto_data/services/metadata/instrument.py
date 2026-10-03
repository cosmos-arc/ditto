"""
InstrumentService - 证券元数据子服务.

证券主数据查询、注册、行业分类、标识符解析等逻辑。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, ClassVar, Literal

import polars as pl
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import ChecksumCompute, logger, traced

from ditto_data.config.dataset_checksum import dataset_sort_keys
from ditto_data.models.metadata import (
    ETFExtension,
    IndexExtension,
    IndustryBasic,
    IndustryMapping,
    InstrumentExtension,
    InstrumentRegistration,
    StockExtension,
)
from ditto_data.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_data.services.metadata._identity import (
    IdentityResolutionRequest,
    IdentityResolverContext,
)
from ditto_data.services.metadata._identity import (
    resolve_instrument_identifier as _resolve_instrument_identifier,
)
from ditto_data.services.metadata._identity import (
    resolve_source_ticker as _resolve_source_ticker,
)
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.fuyao.source import to_thscode
from ditto_data.storage.market.stock.status import (
    StChangeHistoryReader,
    StChangeHistoryWriter,
)
from ditto_data.storage.metadata.industry import (
    IndustryMappingReader,
    IndustryMappingWriter,
    IndustryReader,
    IndustryWriter,
)
from ditto_data.storage.metadata.instrument import (
    EtfReferenceObservationWriter,
    InstrumentReader,
    InstrumentWriter,
    NameHistoryReader,
    NameHistoryWriter,
    SecurityQuery,
)


@dataclass(frozen=True)
class InstrumentServiceDeps:
    """InstrumentService 依赖聚合 — 减少构造参数数量."""

    instrument_reader: InstrumentReader
    instrument_writer: InstrumentWriter
    name_history_reader: NameHistoryReader
    name_history_writer: NameHistoryWriter
    industry_reader: IndustryReader
    industry_writer: IndustryWriter
    industry_mapping_reader: IndustryMappingReader
    industry_mapping_writer: IndustryMappingWriter
    instrument_id_allocator: InstrumentIdAllocator
    exchange_transformers: ExchangeTransformers
    # #395：ST 历史 reader/writer 后进 DI；未接线时使用 fail-closed 占位
    # （读=无证据、写=拒绝），生产装配（di/metadata.py）始终提供真实实现。
    st_change_history_reader: StChangeHistoryReader | None = None
    st_change_history_writer: StChangeHistoryWriter | None = None
    etf_reference_writer: EtfReferenceObservationWriter | None = None


class _NoEvidenceStChangeHistoryReader(StChangeHistoryReader):
    """未接线时的 fail-closed 读占位：永远返回无证据。"""

    def __init__(self) -> None:
        pass

    def get_st_status(
        self,
        instrument_id: int,
        as_of_date: str,
        *,
        cutoff: str | None = None,
    ) -> dict[str, Any] | None:
        """无证据。"""
        return None

    def get_st_status_batch(
        self,
        instrument_ids: list[int],
        as_of_date: str,
        *,
        cutoff: str | None = None,
    ) -> dict[int, dict[str, Any]]:
        """无证据。"""
        return {}


class _UnwiredStChangeHistoryWriter(StChangeHistoryWriter):
    """未接线时的 fail-closed 写占位：任何写入请求都显式拒绝。"""

    def __init__(self) -> None:
        pass

    def save_history_rows(self, rows: list[dict[str, object]]) -> int:
        """拒绝写入（未接线）。"""
        raise RuntimeError(
            "st_change_history_writer is not wired; refusing history write"
        )


class InstrumentService:
    """证券元数据子服务."""

    def __init__(self, deps: InstrumentServiceDeps) -> None:
        """
        初始化 InstrumentService.

        Args:
            deps: 证券元数据服务依赖聚合.

        """
        self._instrument_reader = deps.instrument_reader
        self._instrument_writer = deps.instrument_writer
        self._name_history_reader = deps.name_history_reader
        self._name_history_writer = deps.name_history_writer
        self._st_change_history_reader: StChangeHistoryReader = (
            deps.st_change_history_reader or _NoEvidenceStChangeHistoryReader()
        )
        self._st_change_history_writer: StChangeHistoryWriter = (
            deps.st_change_history_writer or _UnwiredStChangeHistoryWriter()
        )
        self._etf_reference_writer: EtfReferenceObservationWriter | None = (
            deps.etf_reference_writer
        )
        self._industry_reader = deps.industry_reader
        self._industry_writer = deps.industry_writer
        self._industry_mapping_reader = deps.industry_mapping_reader
        self._industry_mapping_writer = deps.industry_mapping_writer
        self._instrument_id_allocator = deps.instrument_id_allocator
        self._exchange_transformers = deps.exchange_transformers

    def list_etf_reference_snapshots(self, *, cutoff: str) -> list[str]:
        """List published ETF reference snapshot identities."""
        return self._instrument_reader.list_etf_reference_snapshots(cutoff=cutoff)

    def find_etf_reference(
        self,
        *,
        asof: str,
        cutoff: str,
        source_snapshot_id: str,
        observed_since: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Read ETF identities and exact-snapshot reference observations."""
        return self._instrument_reader.find_etf_reference(
            asof=asof,
            cutoff=cutoff,
            source_snapshot_id=source_snapshot_id,
            observed_since=observed_since,
        )

    # ============ Identity 解析 ============

    @traced("metadata.identity.resolve_instrument_id")
    def resolve_instrument_id(
        self,
        identifier: str,
        source: str,
        asof: str | None,
    ) -> int | None:
        """
        解析标识符到 instrument_id.

        Args:
            identifier: 数据源代码 (source_ticker).
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            instrument_id 或 None.

        """
        return self._instrument_reader.resolve_instrument_id(identifier, source, asof)

    @traced("metadata.identity.resolve_instrument_ids_batch")
    def resolve_instrument_ids_batch(
        self,
        identifiers: list[str],
        source: str,
        asof: str | None,
    ) -> dict[str, int]:
        """
        批量解析标识符到 instrument_id.

        Args:
            identifiers: 数据源代码列表.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            {identifier: instrument_id} 映射字典.

        """
        return self._instrument_reader.resolve_instrument_ids_batch(
            identifiers, source, asof
        )

    # fuyao 源代码后缀 → 注册证券 exchange（与 fuyao source 的 ticker 前缀规则一致）
    _FUYAO_SUFFIX_EXCHANGE: ClassVar[Mapping[str, str]] = {
        "SH": "SSE",
        "SZ": "SZSE",
        "BJ": "BSE",
    }

    @traced("metadata.identity.resolve_fuyao_instrument_ids")
    def resolve_fuyao_instrument_ids(
        self,
        source_tickers: list[str],
        *,
        evidence_dates: Mapping[str, str] | None = None,
        observed_at: str | None = None,
        register_missing: bool = False,
    ) -> dict[str, int]:
        """
        解析 fuyao thscode（或裸码）到 instrument_id（可选登记证据锚定映射）。

        规则（#395）：
        1. 裸码输入先按 fuyao ticker 前缀规则（6/5→SH、0/3/1→SZ、8/4→BJ）
           转为 thscode；返回键与输入形式一致。
        2. 先读既有 ``instrument_mapping(source='fuyao')``。
        3. 未命中的 thscode 按裸码匹配已注册 instrument：裸码唯一命中且
           后缀推导交易所与注册交易所一致才视为匹配。
        4. ``register_missing=True``（摄取路径）时为匹配项写入
           ``instrument_mapping(source='fuyao', effective_from=有证据日期,
           created_at=观察时间)``；evidence_dates 以输入键给出；
           同键重叠区间映射到不同 instrument_id 时拒绝（行保持未解析）；
           已存在同向映射幂等不重写。
        5. 无法唯一匹配 → 不解析（调用方拒绝该行），记录未知映射计数。

        Args:
            source_tickers: fuyao thscode（如 "600000.SH"）或裸码列表.
            evidence_dates: {输入键: 有证据的最早日期}；register_missing 时必需.
            observed_at: 观察时间（created_at）；register_missing 时必需.
            register_missing: 是否写入缺失映射（摄取 True / 对账只读 False）.

        Returns:
            {输入键: instrument_id} 映射字典（仅包含可解析项）.

        """
        if not source_tickers:
            return {}
        # 输入键 → thscode（含裸码前缀规则转换），单一事实源在 fuyao source
        thscode_by_input = {
            str(ticker): (
                str(ticker) if "." in str(ticker) else to_thscode(str(ticker))
            )
            for ticker in source_tickers
        }
        thscodes = sorted(set(thscode_by_input.values()))
        evidence_by_thscode = {
            thscode_by_input[key]: value
            for key, value in (evidence_dates or {}).items()
            if key in thscode_by_input
        }
        resolved_thscode = self._resolve_fuyao_thscodes(
            thscodes,
            evidence_dates=evidence_by_thscode,
            observed_at=observed_at,
            register_missing=register_missing,
        )
        return {
            key: instrument_id
            for key, thscode in thscode_by_input.items()
            if (instrument_id := resolved_thscode.get(thscode)) is not None
        }

    def _resolve_fuyao_thscodes(
        self,
        thscodes: list[str],
        *,
        evidence_dates: Mapping[str, str],
        observed_at: str | None,
        register_missing: bool,
    ) -> dict[str, int]:
        """Thscode → instrument_id（读取映射 + 前缀规则唯一匹配 + 可选登记）。"""
        resolved = self._instrument_reader.resolve_instrument_ids_batch(
            thscodes, "fuyao", None
        )
        unresolved = [ticker for ticker in thscodes if ticker not in resolved]
        if not unresolved:
            return resolved

        bare_by_ticker: dict[str, str] = {}
        suffix_by_ticker: dict[str, str] = {}
        for ticker in unresolved:
            bare, _, suffix = str(ticker).partition(".")
            bare_by_ticker[ticker] = bare
            suffix_by_ticker[ticker] = suffix.upper()
        matches = self._instrument_reader.map_bare_tickers_to_instrument_ids(
            sorted(set(bare_by_ticker.values()))
        )

        unknown: list[str] = []
        for ticker in unresolved:
            candidates = matches.get(bare_by_ticker[ticker], [])
            suffix_exchange = self._FUYAO_SUFFIX_EXCHANGE.get(suffix_by_ticker[ticker])
            # 唯一命中且交易所与前缀规则一致才复用；多命中/未命中/交易所
            # 不一致都保持未解析（fail closed，不得整批视为匹配）。
            compatible = [
                instrument_id
                for instrument_id in candidates
                if suffix_exchange is not None
                and self._exchange_of(instrument_id) == suffix_exchange
            ]
            if len(compatible) != 1:
                unknown.append(ticker)
                continue
            instrument_id = compatible[0]
            if register_missing:
                effective_from = evidence_dates.get(ticker)
                if effective_from is None or observed_at is None:
                    raise ValueError(
                        "fuyao mapping registration requires an evidence date "
                        "and observation time"
                    )
                registered = self._instrument_writer.register_source_mapping(
                    instrument_id=instrument_id,
                    source="fuyao",
                    source_ticker=str(ticker),
                    effective_from=str(effective_from),
                    observed_at=observed_at,
                )
                if not registered:
                    unknown.append(ticker)  # 重复映射冲突 → 拒绝
                    continue
            resolved[str(ticker)] = instrument_id

        if unknown:
            logger.warning(
                "fuyao identity resolution left unknown mappings",
                event="fuyao_identity_unknown_mappings",
                unknown_count=len(unknown),
                sample=sorted(unknown)[:10],
                register_missing=register_missing,
            )
        return resolved

    def _exchange_of(self, instrument_id: int) -> str | None:
        instrument = self._instrument_reader.get_by_instrument_id(instrument_id)
        if instrument is None:
            return None
        exchange = instrument.get("exchange")
        return str(exchange) if exchange is not None else None

    # ============ 证券查询 ============

    @traced("metadata.instrument.get_instrument")
    def get_instrument(self, instrument_id: int) -> dict[str, Any] | None:
        """
        获取单个证券信息.

        Args:
            instrument_id: 证券 ID.

        Returns:
            证券信息字典，未找到时返回 None.

        """
        return self._instrument_reader.get_by_instrument_id(instrument_id)

    @traced("metadata.instrument.find_securities")
    def find_securities(self, query: SecurityQuery) -> pl.DataFrame:
        """
        多维查询证券数据.

        Args:
            query: SecurityQuery 查询参数对象。

        Returns:
            证券数据 DataFrame.

        """
        return self._instrument_reader.find_securities(query)

    @traced("metadata.instrument.list_instrument_ids")
    def list_instrument_ids(
        self,
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
    ) -> list[int]:
        """
        列出所有 instrument_id（可选过滤）.

        Args:
            asset_class: 按资产类别过滤.
            exchange: 按交易所过滤.
            is_active: 按活跃状态过滤.

        Returns:
            instrument_id 列表.

        """
        return self._instrument_reader.list_instrument_ids(
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
        )

    @traced("metadata.instrument.get_ticker")
    def get_ticker(self, instrument_id: int) -> str | None:
        """
        根据 instrument_id 获取裸代码.

        Args:
            instrument_id: instrument_id.

        Returns:
            裸代码 或 None.

        """
        return self._instrument_reader.get_ticker(instrument_id)

    @traced("metadata.instrument.get_source_ticker")
    def get_source_ticker(
        self,
        instrument_id: int,
        source: str = "tushare",
        asof: str | None = None,
        *,
        cutoff: str | None = None,
    ) -> str | None:
        """
        根据 instrument_id 获取源代码.

        Args:
            instrument_id: instrument_id.
            source: 数据源标识.
            asof: 时间点日期.
            cutoff: 知识截止时刻；隐藏该时刻之后记录的映射行.

        Returns:
            源代码 或 None.

        """
        return self._instrument_reader.get_source_ticker(
            instrument_id, source, asof, cutoff=cutoff
        )

    def get_source_tickers(
        self,
        instrument_id: int,
        *,
        source: str,
        asofs: list[str],
        cutoff: str,
    ) -> dict[str, str | None]:
        """Resolve PIT-visible provider identities for multiple dates in one query."""
        return self._instrument_reader.get_source_tickers(
            instrument_id, source=source, asofs=asofs, cutoff=cutoff
        )

    # ============ 行业查询 ============

    @traced("metadata.industry.find_industries")
    def find_industries(
        self,
        is_active: bool = True,
        industry_level: str | None = None,
    ) -> pl.DataFrame:
        """
        多维查询行业数据.

        Args:
            is_active: 是否只返回活跃行业.
            industry_level: 行业级别过滤.

        Returns:
            行业数据 DataFrame.

        """
        return self._industry_reader.get_all(is_active, industry_level)

    @traced("metadata.industry.list_industry_stocks")
    def list_industry_stocks(
        self,
        industry_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        查询行业成分股.

        Args:
            industry_id: 行业 ID.
            asof: 时间点日期.

        Returns:
            Instrument ID 列表.

        """
        return self._industry_mapping_reader.get_stocks(industry_id, asof)

    @traced("metadata.industry.get_stock_industry")
    def get_stock_industry(
        self,
        instrument_id: int,
        asof: str | None = None,
    ) -> dict[str, Any] | None:
        """
        查询股票所属行业.

        Args:
            instrument_id: 证券 ID.
            asof: 时间点日期.

        Returns:
            行业映射信息 或 None.

        """
        return self._industry_mapping_reader.get_stock_industry(instrument_id, asof)

    @traced("metadata.industry.save_classification")
    def save_industry_classification(
        self,
        df: pl.DataFrame,
        *,
        source: str,
    ) -> int:
        """Persist a provider classification snapshot into the current read model."""
        required = {"industry_id", "industry_name", "industry_level"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(
                f"industry classification missing columns: {sorted(missing)}"
            )
        for row in df.to_dicts():
            raw_level = row["industry_level"]
            level = (
                str(raw_level)
                if str(raw_level).startswith("L")
                else f"L{int(raw_level)}"
            )
            self._industry_writer.register(
                IndustryBasic(
                    industry_id=str(row["industry_id"]),
                    industry_name=str(row["industry_name"]),
                    industry_level=level,
                    source=str(row.get("source") or source),
                )
            )
        return len(df)

    @traced("metadata.industry.save_mapping")
    def save_industry_mapping(
        self,
        df: pl.DataFrame,
        *,
        source: str,
    ) -> int:
        """Resolve provider tickers and persist effective-dated current mappings."""
        required = {"instrument_id", "industry_id", "industry_date"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"industry mapping missing columns: {sorted(missing)}")
        identifiers = [str(value) for value in df["instrument_id"].unique().to_list()]
        resolved = self.resolve_instrument_ids_batch(identifiers, source, None)
        unresolved = sorted(set(identifiers) - resolved.keys())
        if unresolved:
            raise ValueError(
                f"industry mapping contains unresolved instruments: {len(unresolved)}"
            )
        rows = sorted(
            df.to_dicts(),
            key=lambda row: (str(row["instrument_id"]), str(row["industry_date"])),
        )
        for row in rows:
            effective_from = row["industry_date"]
            effective_to = row.get("effective_to")
            self._industry_mapping_writer.update_mapping(
                IndustryMapping(
                    instrument_id=resolved[str(row["instrument_id"])],
                    industry_id=str(row["industry_id"]),
                    source=str(row.get("source") or source),
                    effective_from=(
                        effective_from.isoformat()
                        if isinstance(effective_from, date)
                        else str(effective_from)
                    ),
                    effective_to=(
                        effective_to.isoformat()
                        if isinstance(effective_to, date)
                        else str(effective_to)
                        if effective_to is not None
                        else None
                    ),
                    entry_reason=str(row.get("classification_version") or "provider"),
                )
            )
        return len(rows)

    # ============ 状态查询 (PIT) ============

    @traced("metadata.instrument.get_stock_status")
    def get_stock_status(
        self,
        instrument_id: int,
        asof: str,
    ) -> dict[str, Any]:
        """
        获取股票在指定时间点的状态（PIT 查询）.

        #395 默认正常收紧：无历史证据时不再默认 ``{is_st: False, ...}``，
        而是返回显式未知状态 —— ``has_evidence=False`` 且字段为 None。
        消费方必须 fail closed（拒绝/排除）或显式选择回退路径，
        不得把未知当正常。

        证据来源：
        - is_st: ``st_change_history`` PIT 区间（asof 覆盖）
        - list_status/is_suspended: ``instrument_stock`` 当前读模型

        Args:
            instrument_id: 证券 ID.
            asof: 时间点日期 (YYYY-MM-DD).

        Returns:
            {is_st, st_type, list_status, is_suspended, has_evidence}；
            无证据时 is_st/list_status/is_suspended 均为 None.

        """
        status: dict[str, Any] = {
            "is_st": None,
            "st_type": None,
            "list_status": None,
            "is_suspended": None,
            "has_evidence": False,
        }

        # ST 证据：PIT 区间覆盖才可知
        st_evidence = self._st_change_history_reader.get_st_status(instrument_id, asof)
        if st_evidence is not None:
            status["is_st"] = st_evidence["is_st"]
            status["st_type"] = st_evidence.get("st_type")
            status["has_evidence"] = True

        # 上市状态证据：instrument_stock 当前读模型
        stock_ext = self._instrument_reader.get_stock_extension(instrument_id)
        if stock_ext:
            list_status = stock_ext.get("list_status")
            if list_status:
                status["list_status"] = list_status
                # P = 暂停上市, D = 退市 → 视为 suspended
                status["is_suspended"] = list_status in ("P", "D")
                status["has_evidence"] = True

        if not status["has_evidence"]:
            logger.info(
                "Stock status unknown: no PIT evidence",
                event="stock_status_unknown",
                instrument_id=instrument_id,
                asof=asof,
            )
        return status

    def get_st_status_batch(
        self,
        instrument_ids: list[int],
        asof: str,
        *,
        cutoff: str | None = None,
    ) -> dict[int, dict[str, Any]]:
        """
        批量 PIT 查询 ST 状态（st_change_history 证据）。

        只返回有证据的证券；无证据不返回键（调用方按受限回退处理）。
        """
        return self._st_change_history_reader.get_st_status_batch(
            instrument_ids, asof, cutoff=cutoff
        )

    # ============ 证券注册 ============

    @traced("metadata.instrument.register_instrument")
    def register_instrument(self, registration: InstrumentRegistration) -> int:
        """
        注册新证券.

        Args:
            registration: 证券注册信息.

        Returns:
            分配的 instrument_id.

        """
        # 分配 instrument_id
        instrument_id = self._instrument_id_allocator.allocate(registration.asset_class)

        # 注册到 instrument_writer
        registered_id = self._instrument_writer.register(instrument_id, registration)

        logger.info(
            "Instrument registered via MetadataService",
            event="metadata_instrument_registered",
            instrument_id=registered_id,
            ticker=registration.ticker,
            source_ticker=registration.source_ticker,
        )

        return registered_id

    @staticmethod
    def _build_extension(
        row: dict[str, Any], asset_class: str
    ) -> InstrumentExtension | None:
        """
        根据资产类型和行数据构建扩展信息.

        Args:
            row: 包含证券元数据的字典
            asset_class: 资产类别

        Returns:
            对应类型的 InstrumentExtension，如果不需要扩展信息则返回 None

        """
        if asset_class == "stock":
            # 股票扩展信息：list_status
            list_status = row.get("list_status")
            if list_status:
                return StockExtension(
                    instrument_id=0,  # 占位，实际值由 register_instrument 设置
                    list_status=list_status,
                    industry_id=None,
                )
        elif asset_class == "etf":
            # ETF 扩展：帧列缺省时保持 NULL（不虚构参考事实），
            # 扩展表行本身接通（etf_basic 帧列见 tushare etf 适配器）。
            return ETFExtension(
                instrument_id=0,  # 占位，实际值由 register_instrument 设置
                fund_type=row.get("fund_type"),
                fund_manager=row.get("fund_manager"),
                establish_date=row.get("establish_date"),
                tracking_index=row.get("tracking_index"),
            )
        elif asset_class == "index":
            # 指数扩展：同上（index_basic 帧列见 tushare index 适配器）。
            return IndexExtension(
                instrument_id=0,  # 占位，实际值由 register_instrument 设置
                base_date=row.get("base_date"),
                base_point=row.get("base_point"),
                num_constituents=row.get("num_constituents"),
            )
        return None

    @traced("metadata.instrument.register_instruments_batch")
    def register_instruments_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf", "index"],
        source_ticker_col: str = "source_ticker",
    ) -> tuple[str, str]:
        """
        批量注册证券（跳过已存在的）。

        Args:
            df: 包含证券元数据的 DataFrame。必须包含以下列：
                - source_ticker_col: 源代码列名
                - ticker: 裸代码
                - name: 证券名称
                - exchange: 交易所代码
                - list_date: 上市日期
            source: 数据源标识符
            asset_class: 资产类别
            source_ticker_col: DataFrame 中源代码的列名

        Returns:
            (file_path, checksum) 元组

        """
        logger.info(
            "Starting batch instrument registration",
            event="instrument_batch_register_start",
            source=source,
            asset_class=asset_class,
            row_count=len(df),
        )

        registered_count = 0
        skipped_count = 0
        # 退市更新仅针对此前已注册的证券；同批新注册的证券在注册时
        # 直接落 delist_date/is_active，不走退市 UPDATE 重写。
        delisted_updates = 0

        for row in df.to_dicts():
            source_ticker = row[source_ticker_col]

            # 检查是否已存在
            existing_instrument_id = self._instrument_reader.resolve_instrument_id(
                source_ticker, source, None
            )
            if existing_instrument_id is not None:
                skipped_count += 1
                # 退市发生时更新已注册证券（不删除历史池成员）
                if asset_class == "stock" and row.get("list_status") == "D":
                    delist_date = row.get("delist_date")
                    if delist_date is not None and str(delist_date).strip():
                        self._instrument_writer.apply_delisting(
                            existing_instrument_id, str(delist_date)
                        )
                        delisted_updates += 1
                continue

            # 注册新证券
            self.register_instrument(
                InstrumentRegistration(
                    source_ticker=source_ticker,
                    ticker=row["ticker"],
                    name=row["name"],
                    exchange=row["exchange"],
                    asset_class=asset_class,
                    list_date=row["list_date"],
                    delist_date=row.get("delist_date"),
                    source=source,
                    board=row.get("board"),
                    extension=self._build_extension(row, asset_class),
                )
            )
            registered_count += 1

        # 计算 checksum
        dataset_name = f"{asset_class}_basic"
        df_with_source = df.with_columns(pl.lit(source).alias("source"))
        checksum = ChecksumCompute.from_dataframe(
            df_with_source, dataset_sort_keys(dataset_name)
        )

        file_path = f"instrument_reader:{asset_class}_basic"

        logger.info(
            "Batch instrument registration completed",
            event="instrument_batch_register_complete",
            registered=registered_count,
            skipped=skipped_count,
            delisted_updates=delisted_updates,
            checksum=checksum,
        )

        return file_path, checksum

    @traced("metadata.instrument.resolve_or_create_instruments_batch")
    def resolve_or_create_instruments_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf", "index"],
        source_ticker_col: str = "source_ticker",
    ) -> dict[str, int]:
        """
        批量解析 source_ticker，不存在则自动创建证券。

        Args:
            df: 包含证券元数据的 DataFrame。必须包含以下列：
                - source_ticker_col: 源代码列名
                - ticker: 裸代码
                - name: 证券名称
                - exchange: 交易所代码
                - list_date: 上市日期
            source: 数据源标识符
            asset_class: 资产类别
            source_ticker_col: DataFrame 中源代码的列名

        Returns:
            {source_ticker: instrument_id} 映射字典

        """
        logger.debug(
            "Resolving or creating instruments in batch",
            event="instrument_resolve_or_create_start",
            source=source,
            asset_class=asset_class,
            row_count=len(df),
        )

        result: dict[str, int] = {}
        created_count = 0

        # 处理空 DataFrame
        if len(df) == 0:
            return result

        # 验证必需列
        required_cols = [
            source_ticker_col,
            "ticker",
            "name",
            "exchange",
            "list_date",
        ]
        for col in required_cols:
            if col not in df.columns:
                msg = f"DataFrame 缺少必需列: {col}"
                raise KeyError(msg)

        # 批量查询已存在的证券
        source_tickers = df[source_ticker_col].to_list()
        existing_mappings = self._instrument_reader.resolve_instrument_ids_batch(
            source_tickers, source, None
        )

        # 处理每一行
        for row in df.to_dicts():
            source_ticker = row[source_ticker_col]

            # 如果已存在，使用已有的 instrument_id
            if source_ticker in existing_mappings:
                result[source_ticker] = existing_mappings[source_ticker]
                continue

            # 不存在则创建新证券
            instrument_id = self.register_instrument(
                InstrumentRegistration(
                    source_ticker=source_ticker,
                    ticker=row["ticker"],
                    name=row["name"],
                    exchange=row["exchange"],
                    asset_class=asset_class,
                    list_date=row["list_date"],
                    delist_date=row.get("delist_date"),
                    source=source,
                )
            )
            result[source_ticker] = instrument_id
            created_count += 1

        logger.debug(
            "Batch resolve or create completed",
            event="instrument_resolve_or_create_complete",
            total_count=len(result),
            created_count=created_count,
        )

        return result

    # ============ 标识符解析（委托给 _identity 模块） ============

    @traced("metadata.identity.resolve_instrument_identifier")
    def resolve_instrument_identifier(
        self,
        *,
        instrument_id: int | None = None,
        standard_ticker: str | None = None,
        ticker: str | None = None,
        asset_class: str | None = None,
        source: str,
        asof: str | None = None,
    ) -> InstrumentId | None:
        """统一标识符解析入口（委托给 _identity 模块）."""
        return _resolve_instrument_identifier(
            IdentityResolverContext(
                instrument_reader=self._instrument_reader,
                exchange_transformers=self._exchange_transformers,
            ),
            IdentityResolutionRequest(
                instrument_id=instrument_id,
                standard_ticker=standard_ticker,
                ticker=ticker,
                asset_class=asset_class,
                source=source,
                asof=asof,
            ),
        )

    @traced("metadata.identity.resolve_source_ticker")
    def resolve_source_ticker(
        self,
        ticker: str | None = None,
        standard_ticker: str | None = None,
        instrument_id: int | None = None,
        asset_class: str = "stock",
        source: str = "tushare",
        asof: str | None = None,
    ) -> str:
        """将任意标识符解析为 source_ticker（委托给 _identity 模块）."""
        return _resolve_source_ticker(
            IdentityResolverContext(
                instrument_reader=self._instrument_reader,
                exchange_transformers=self._exchange_transformers,
            ),
            IdentityResolutionRequest(
                ticker=ticker,
                standard_ticker=standard_ticker,
                instrument_id=instrument_id,
                asset_class=asset_class,
                source=source,
                asof=asof,
            ),
        )

    # ============ list_date 更新 ============

    @traced("metadata.instrument.update_list_date")
    def update_list_date(
        self, instrument_id: int, list_date: date | str | None
    ) -> None:
        """
        更新证券的上市日期.

        用于从行情数据推断上市日期的场景。

        Args:
            instrument_id: 证券 ID
            list_date: 上市日期

        """
        self._instrument_writer.update_list_date(instrument_id, list_date)

    @traced("metadata.instrument.find_instruments_without_list_date")
    def find_instruments_without_list_date(
        self,
        asset_class: str | None = None,
    ) -> pl.DataFrame:
        """
        查找没有上市日期的证券.

        Args:
            asset_class: 资产类别过滤（可选）

        Returns:
            包含 instrument_id, source_ticker, asset_class 的 DataFrame

        """
        return self._instrument_reader.find_securities(
            SecurityQuery(asset_class=asset_class, is_active=True),
        ).filter(pl.col("list_date").is_null())

    # ============ 证券名称查询 ============

    def save_name_history(
        self,
        df: pl.DataFrame,
        *,
        source: str,
        observed_at: str,
    ) -> int:
        """
        写入带证据的名称变更历史（namechange 摄取路径）。

        行要求：source_ticker、new_name、changed_date（真实生效日期）；
        published_at（provider 可知时间）缺省时退回观察时间。
        缺真实生效日期的行拒绝（不写、计数日志），未知证券拒绝。

        Args:
            df: namechange 帧.
            source: 来源标识.
            observed_at: 观察时间（写入 observed_at 的缺省）.

        Returns:
            写入行数.

        """
        return self._save_history_rows(
            df,
            source=source,
            observed_at=observed_at,
            row_builder=self._name_history_row,
            writer=self._name_history_writer.save_history_rows,
            reject_log_event="name_history_rows_rejected",
        )

    def save_st_change_history(
        self,
        df: pl.DataFrame,
        *,
        source: str,
        observed_at: str,
    ) -> int:
        """
        写入带证据的 ST 变更历史（st_history 摄取路径）。

        行要求：source_ticker、change_date（真实生效日期）；
        change_reason 推导 is_st/st_type（含"撤销"→ 非 ST 闭合区间）。
        缺真实生效日期的行拒绝，未知证券拒绝。

        Args:
            df: st_history 帧.
            source: 来源标识.
            observed_at: 观察时间.

        Returns:
            写入行数.

        """
        return self._save_history_rows(
            df,
            source=source,
            observed_at=observed_at,
            row_builder=self._st_history_row,
            writer=self._st_change_history_writer.save_history_rows,
            reject_log_event="st_history_rows_rejected",
        )

    def save_etf_reference_observations(
        self,
        rows: list[dict[str, object]],
    ) -> int:
        """
        写入 ETF 参考事实观察行（etf_basic 摄取生成，绑定来源快照）。

        行要求：source_ticker（解析身份）、field/value/unit、observed_on、
        published_at、effective_from、source_snapshot_id。未解析身份的行拒绝。

        Args:
            rows: 观察行字典列表.

        Returns:
            写入行数.

        """
        if not rows:
            return 0
        if self._etf_reference_writer is None:
            raise RuntimeError(
                "etf_reference_writer is not wired; refusing observation write"
            )
        identifiers = sorted({str(row["source_ticker"]) for row in rows})
        resolved = self._instrument_reader.resolve_instrument_ids_batch(
            identifiers, str(rows[0]["source"]), None
        )
        writable: list[dict[str, object]] = []
        rejected = 0
        for row in rows:
            instrument_id = resolved.get(str(row["source_ticker"]))
            if instrument_id is None:
                rejected += 1
                continue
            entry = dict(row)
            entry["instrument_id"] = instrument_id
            writable.append(entry)
        if rejected:
            logger.warning(
                "etf reference observations rejected (unresolved identity)",
                event="etf_reference_rows_rejected",
                rejected=rejected,
                accepted=len(writable),
            )
        return self._etf_reference_writer.save_observations(writable)

    def _save_history_rows(
        self,
        df: pl.DataFrame,
        *,
        source: str,
        observed_at: str,
        row_builder: Callable[[dict[str, Any], str, str], dict[str, Any] | None],
        writer: Callable[[list[dict[str, object]]], int],
        reject_log_event: str,
    ) -> int:
        """共享写路径：解析身份 → 逐行构建 → 缺证据拒绝 → 幂等写入。"""
        if df.is_empty():
            return 0
        identifiers = [str(v) for v in df["source_ticker"].unique().to_list()]
        resolved = self._instrument_reader.resolve_instrument_ids_batch(
            identifiers, source, None
        )
        rows: list[dict[str, object]] = []
        rejected = 0
        for raw in df.to_dicts():
            instrument_id = resolved.get(str(raw["source_ticker"]))
            if instrument_id is None:
                rejected += 1
                continue
            built = row_builder(raw, source, observed_at)
            if built is None:
                rejected += 1
                continue
            built["instrument_id"] = instrument_id
            rows.append(built)
        if rejected:
            logger.warning(
                "history rows rejected (unknown identity or missing real dates)",
                event=reject_log_event,
                rejected=rejected,
                accepted=len(rows),
                source=source,
            )
        return writer(rows) if rows else 0

    @staticmethod
    def _name_history_row(
        raw: dict[str, Any], source: str, observed_at: str
    ) -> dict[str, Any] | None:
        """Namechange 原始行 → 历史行；缺真实生效日期拒绝。"""
        changed_date = _to_iso_date(raw.get("changed_date"))
        if changed_date is None:
            return None
        published = _to_iso_datetime(raw.get("published_at"))
        return {
            "old_name": raw.get("old_name"),
            "new_name": raw.get("new_name"),
            "changed_date": changed_date,
            "effective_to": _to_iso_date(raw.get("effective_to")),
            "source": str(raw.get("source") or source),
            "observed_at": published or observed_at,
        }

    @staticmethod
    def _st_history_row(
        raw: dict[str, Any], source: str, observed_at: str
    ) -> dict[str, Any] | None:
        """st_history 原始行 → 历史行；缺真实生效日期拒绝；原因推导状态。"""
        effective_from = _to_iso_date(raw.get("change_date"))
        if effective_from is None:
            return None
        reason = str(raw.get("change_reason") or "")
        is_st = "ST" in reason.upper() and "撤销" not in reason
        st_type = None
        if is_st:
            st_type = "*ST" if "*ST" in reason else "ST"
        published = _to_iso_datetime(raw.get("published_at"))
        return {
            "effective_from": effective_from,
            "effective_to": _to_iso_date(raw.get("end_date")),
            "is_st": is_st,
            "st_type": st_type,
            "source": str(raw.get("source") or source),
            "observed_at": published or observed_at,
        }

    @traced("metadata.instrument.get_stock_names")
    def get_stock_names(
        self,
        instrument_ids: list[int],
        asof: str | None = None,
    ) -> dict[int, str]:
        """
        批量获取证券名称（PIT，单次查询）.

        只返回名称变更历史命中的证券；调用方以当前注册表作回退.

        Args:
            instrument_ids: 证券 ID 列表.
            asof: Point-in-Time 日期 (YYYY-MM-DD).

        Returns:
            {instrument_id: name} 映射.

        """
        if asof is None:
            return {}
        return self._name_history_reader.get_names_batch(instrument_ids, asof)

    @traced("metadata.instrument.get_stock_name")
    def get_stock_name(
        self,
        instrument_id: int,
        asof: str | None = None,
    ) -> str | None:
        """
        获取证券名称（支持 PIT 查询）.

        如果指定 asof 日期，优先从名称变更历史中查找，
        若未找到则 fallback 到 instrument 表中的当前名称。

        Args:
            instrument_id: 证券 ID.
            asof: Point-in-Time 日期 (YYYY-MM-DD)，None 表示当前名称.

        Returns:
            证券名称或 None（未找到时）.

        """
        if asof is not None:
            name = self._name_history_reader.get_name(instrument_id, asof)
            if name is not None:
                return name
        # Fallback: 当前名称
        instrument = self._instrument_reader.get_by_instrument_id(instrument_id)
        return instrument.get("name") if instrument else None

    # ============ 行业多级查询 ============

    @traced("metadata.industry.get_stock_industries_all_levels")
    def get_stock_industries_all_levels(
        self,
        instrument_id: int,
        asof: str | None = None,
        source: str = "sw",
    ) -> list[dict[str, Any]]:
        """
        获取股票所有级别的行业分类.

        JOIN industry_basic 获取 industry_level，按 level 排序。

        Args:
            instrument_id: 证券 ID.
            asof: Point-in-Time 日期，None 表示查询当前.
            source: 行业分类来源（sw=申万, csrc=证监会）.

        Returns:
            行业分类列表（按 industry_level 排序）.

        """
        return self._industry_mapping_reader.get_stock_industries_all_levels(
            instrument_id, asof, source
        )


_ISO_DATE_COMPACT_LENGTH = 8


def _to_iso_date(value: object) -> str | None:
    """date/str → YYYY-MM-DD；None/空返回 None。"""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    compact = text.replace("-", "")
    if len(compact) != _ISO_DATE_COMPACT_LENGTH or not compact.isdigit():
        return None
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def _to_iso_datetime(value: object) -> str | None:
    """datetime/str → 'YYYY-MM-DD HH:MM:SS'；None 返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    text = str(value).strip().replace("T", " ")
    if not text:
        return None
    return text[:19]
