"""Tests for data normalization enumerations and configuration."""

import pytest
from ditto_datahub.sources.normalization import (
    Currency,
    Exchange,
    InstrumentType,
    NormalizationConfig,
)


@pytest.mark.unit
class TestExchange:
    """测试 Exchange 枚举."""

    def test_should_have_all_exchanges(self) -> None:
        """应该包含所有中国交易所."""
        assert Exchange.SSE.value == "SSE"
        assert Exchange.SZSE.value == "SZSE"
        assert Exchange.BSE.value == "BSE"
        assert Exchange.CFFEX.value == "CFFEX"
        assert Exchange.SHFE.value == "SHFE"
        assert Exchange.DCE.value == "DCE"
        assert Exchange.CZCE.value == "CZCE"

    def test_should_be_string_enum(self) -> None:
        """应该是字符串枚举."""
        assert isinstance(Exchange.SSE.value, str)
        assert Exchange.SSE == "SSE"

    def test_should_have_seven_members(self) -> None:
        """应该有七个交易所成员."""
        assert len(Exchange) == 7


@pytest.mark.unit
class TestInstrumentType:
    """测试 InstrumentType 枚举."""

    def test_should_have_all_instrument_types(self) -> None:
        """应该包含所有标的类型."""
        assert InstrumentType.STOCK.value == "stock"
        assert InstrumentType.ETF.value == "etf"
        assert InstrumentType.INDEX.value == "index"
        assert InstrumentType.FUTURE.value == "future"
        assert InstrumentType.OPTION.value == "option"
        assert InstrumentType.BOND.value == "bond"
        assert InstrumentType.FUND.value == "fund"

    def test_should_be_string_enum(self) -> None:
        """应该是字符串枚举."""
        assert isinstance(InstrumentType.STOCK.value, str)
        assert InstrumentType.STOCK == "stock"

    def test_should_have_seven_members(self) -> None:
        """应该有七个标的类型成员."""
        assert len(InstrumentType) == 7


@pytest.mark.unit
class TestCurrency:
    """测试 Currency 枚举."""

    def test_should_have_all_currencies(self) -> None:
        """应该包含所有货币代码."""
        assert Currency.CNY.value == "CNY"
        assert Currency.USD.value == "USD"
        assert Currency.HKD.value == "HKD"
        assert Currency.EUR.value == "EUR"

    def test_should_be_string_enum(self) -> None:
        """应该是字符串枚举."""
        assert isinstance(Currency.CNY.value, str)
        assert Currency.CNY == "CNY"

    def test_should_have_four_members(self) -> None:
        """应该有四个货币成员."""
        assert len(Currency) == 4


@pytest.mark.unit
class TestNormalizationConfig:
    """测试 NormalizationConfig 配置."""

    def test_should_create_with_defaults(self) -> None:
        """应该能够使用默认值创建配置."""
        config = NormalizationConfig()

        assert config.amount_multiplier == 1.0
        assert config.volume_multiplier == 1.0
        assert config.percentage_as_decimal is True
        assert config.default_currency == Currency.CNY

    def test_should_have_default_exchange_map(self) -> None:
        """应该有默认的交易所映射."""
        config = NormalizationConfig()

        assert config.exchange_map["SH"] == Exchange.SSE
        assert config.exchange_map["SZ"] == Exchange.SZSE
        assert config.exchange_map["BJ"] == Exchange.BSE

    def test_should_have_default_asset_class_map(self) -> None:
        """应该有默认的资产类别映射."""
        config = NormalizationConfig()

        assert config.asset_class_map["E"] == InstrumentType.STOCK
        assert config.asset_class_map["ETF"] == InstrumentType.ETF
        assert config.asset_class_map["I"] == InstrumentType.INDEX
        assert config.asset_class_map["FD"] == InstrumentType.FUND

    def test_should_create_with_custom_values(self) -> None:
        """应该能够创建自定义配置."""
        config = NormalizationConfig(
            amount_multiplier=10000.0,
            volume_multiplier=100.0,
            percentage_as_decimal=False,
            default_currency=Currency.USD,
        )

        assert config.amount_multiplier == 10000.0
        assert config.volume_multiplier == 100.0
        assert config.percentage_as_decimal is False
        assert config.default_currency == Currency.USD

    def test_should_be_frozen_dataclass(self) -> None:
        """应该是不可变的数据类."""
        from dataclasses import FrozenInstanceError

        config = NormalizationConfig()

        # frozen dataclass 会抛出 FrozenInstanceError
        # 注意: basedpyright 会在这里报错，但这是预期的测试行为
        try:
            config.amount_multiplier = 2.0  # type: ignore[misc]
            pytest.fail("Expected FrozenInstanceError")
        except FrozenInstanceError:
            pass  # 预期的异常

    def test_should_support_custom_exchange_map(self) -> None:
        """应该支持自定义交易所映射."""
        custom_map = {"CN": Exchange.SSE, "US": Exchange.SZSE}
        config = NormalizationConfig(exchange_map=custom_map)

        assert config.exchange_map["CN"] == Exchange.SSE
        assert config.exchange_map["US"] == Exchange.SZSE

    def test_should_support_custom_asset_class_map(self) -> None:
        """应该支持自定义资产类别映射."""
        custom_map = {"STOCK": InstrumentType.STOCK, "IDX": InstrumentType.INDEX}
        config = NormalizationConfig(asset_class_map=custom_map)

        assert config.asset_class_map["STOCK"] == InstrumentType.STOCK
        assert config.asset_class_map["IDX"] == InstrumentType.INDEX

    def test_should_maintain_separate_instances(self) -> None:
        """不同实例应该有独立的映射字典."""
        config1 = NormalizationConfig()
        config2 = NormalizationConfig()

        # 修改 config1 的默认映射不应该影响 config2
        # (但由于使用 default_factory，每个实例都有独立的副本)
        assert config1.exchange_map is not config2.exchange_map
        assert config1.asset_class_map is not config2.asset_class_map
