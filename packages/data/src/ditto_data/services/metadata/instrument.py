"""
InstrumentService - 证券元数据子服务.

证券主数据查询、注册、行业分类、标识符解析等逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import polars as pl
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import ChecksumCompute, logger, traced

from ditto_data.config.dataset_checksum import dataset_sort_keys
from ditto_data.models.metadata import (
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
from ditto_data.storage.metadata.industry import (
    IndustryMappingReader,
    IndustryMappingWriter,
    IndustryReader,
    IndustryWriter,
)
from ditto_data.storage.metadata.instrument import (
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
        self._industry_reader = deps.industry_reader
        self._industry_writer = deps.industry_writer
        self._industry_mapping_reader = deps.industry_mapping_reader
        self._industry_mapping_writer = deps.industry_mapping_writer
        self._instrument_id_allocator = deps.instrument_id_allocator
        self._exchange_transformers = deps.exchange_transformers

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
    ) -> str | None:
        """
        根据 instrument_id 获取源代码.

        Args:
            instrument_id: instrument_id.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            源代码 或 None.

        """
        return self._instrument_reader.get_source_ticker(instrument_id, source, asof)

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

    # ============ 状态查询 (PIT) ============

    @traced("metadata.instrument.get_stock_status")
    def get_stock_status(
        self,
        instrument_id: int,
        asof: str,
    ) -> dict[str, Any]:
        """
        获取股票在指定时间点的状态（PIT 查询）.

        通过 SQLite 中的 instrument 表获取 is_st 字段，
        通过 instrument_stock 表获取 list_status。
        完整 PIT 实现将通过 Parquet 数据源提供。

        Args:
            instrument_id: 证券 ID.
            asof: 时间点日期 (YYYY-MM-DD).

        Returns:
            包含 is_st, list_status, is_suspended 的字典。
            无数据时返回默认值。

        """
        defaults: dict[str, Any] = {
            "is_st": False,
            "list_status": "L",
            "is_suspended": False,
        }

        # 从 instrument 表获取 is_st
        instrument = self._instrument_reader.get_by_instrument_id(instrument_id)
        if instrument:
            defaults["is_st"] = bool(instrument.get("is_st", False))

        # 从 instrument_stock 表获取 list_status
        stock_ext = self._instrument_reader.get_stock_extension(instrument_id)
        if stock_ext:
            list_status = stock_ext.get("list_status", "L")
            defaults["list_status"] = list_status
            # P = 暂停上市, D = 退市 → 视为 suspended
            defaults["is_suspended"] = list_status in ("P", "D")

        return defaults

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

        for row in df.to_dicts():
            source_ticker = row[source_ticker_col]

            # 检查是否已存在
            existing_instrument_id = self._instrument_reader.resolve_instrument_id(
                source_ticker, source, None
            )
            if existing_instrument_id is not None:
                skipped_count += 1
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
