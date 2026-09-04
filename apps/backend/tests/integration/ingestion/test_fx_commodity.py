# 测试文件允许函数内导入

"""FX 和 Commodity 摄取流程集成测试。"""

import pytest


@pytest.mark.integration
class TestFxCommodityIngestion:
    """Tests for FX and Commodity ingestion with UTC timestamp."""

    def test_fx_daily_schema_has_utc_timestamp(self) -> None:
        """测试 FX 数据包含 UTC 时间戳.

        验证 FX_SOURCE_SCHEMA 定义中包含 trade_date_utc 字段，
        且类型为 UTC 午夜的 Datetime。
        """
        from ditto_data.sources.schemas.fx_schemas import FX_SOURCE_SCHEMA

        schema = FX_SOURCE_SCHEMA.schema

        # 验证 trade_date_utc 字段存在
        assert "trade_date_utc" in schema, "trade_date_utc 字段必须存在于 FX schema 中"

        # 验证类型为 Datetime（UTC）
        import polars as pl

        field_dtype = schema["trade_date_utc"]
        assert isinstance(field_dtype, pl.Datetime), (
            f"trade_date_utc must be Datetime type, got {field_dtype}"
        )

    def test_commodity_daily_schema_has_utc_timestamp(self) -> None:
        """测试 Commodity 数据包含 UTC 时间戳.

        验证 COMMODITY_SOURCE_SCHEMA 定义中包含 trade_date_utc 字段，
        且类型为 UTC 午夜的 Datetime。
        """
        from ditto_data.sources.schemas.commodity_schemas import (
            COMMODITY_SOURCE_SCHEMA,
        )

        schema = COMMODITY_SOURCE_SCHEMA.schema

        # 验证 trade_date_utc 字段存在
        assert "trade_date_utc" in schema, (
            "trade_date_utc 字段必须存在于 Commodity schema 中"
        )

        # 验证类型为 Datetime（UTC）
        import polars as pl

        field_dtype = schema["trade_date_utc"]
        assert isinstance(field_dtype, pl.Datetime), (
            f"trade_date_utc must be Datetime type, got {field_dtype}"
        )

    def test_fx_bar_model_has_trade_date_utc(self) -> None:
        """测试 FxBar 响应模型包含 trade_date_utc 字段."""
        from ditto_apps.models.fx import FxBar

        # 验证模型字段
        model_fields = FxBar.model_fields
        assert "trade_date_utc" in model_fields, (
            "FxBar 模型必须包含 trade_date_utc 字段"
        )

    def test_commodity_bar_model_has_trade_date_utc(self) -> None:
        """测试 CommodityBar 响应模型包含 trade_date_utc 字段."""
        from ditto_apps.models.commodity import CommodityBar

        # 验证模型字段
        model_fields = CommodityBar.model_fields
        assert "trade_date_utc" in model_fields, (
            "CommodityBar 模型必须包含 trade_date_utc 字段"
        )

    # TODO: 添加端到端摄取测试
    # - test_fx_ingestion_end_to_end: 完整摄取链路测试
    # - test_commodity_ingestion_end_to_end: 完整摄取链路测试
    # - test_fx_data_writer_creates_parquet: 验证写入 Parquet 文件
    # - test_commodity_data_writer_creates_parquet: 验证写入 Parquet 文件
