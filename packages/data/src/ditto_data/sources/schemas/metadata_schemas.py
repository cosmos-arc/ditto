"""
Metadata SourceSchema definitions.

定义 Metadata 域的 SourceSchema，作为数据源输出的标准协议。
"""

import polars as pl

from ditto_data.sources.source_schema import SourceSchema

__all__ = [
    "INDEX_MEMBER_SOURCE_SCHEMA",
    "INDUSTRY_SOURCE_SCHEMA",
    "INSTRUMENT_SOURCE_SCHEMA",
]


INSTRUMENT_SOURCE_SCHEMA = SourceSchema(
    dataset="instrument",
    key_columns=("instrument_id",),
    schema={
        "instrument_id": pl.String,
        "source_ticker": pl.String,
        "name": pl.String,
        "exchange": pl.String,  # Exchange enum value
        "list_date": pl.Date,
        "delist_date": pl.Date,
        "instrument_type": pl.String,  # InstrumentType enum value
    },
)

INDUSTRY_SOURCE_SCHEMA = SourceSchema(
    dataset="industry",
    key_columns=("instrument_id", "industry_date"),
    schema={
        "instrument_id": pl.String,
        "industry_name": pl.String,
        "industry_level": pl.Int32,  # 1=一级行业, 2=二级行业
        "industry_date": pl.Date,
        "knowledge_date": pl.Date,
    },
)

INDEX_MEMBER_SOURCE_SCHEMA = SourceSchema(
    dataset="index_member",
    key_columns=("index_id", "instrument_id", "effective_from"),
    schema={
        "index_id": pl.String,
        "instrument_id": pl.String,
        "weight": pl.Float64,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
    },
    pit_columns=("effective_from", "effective_to"),
)
