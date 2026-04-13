"""ditto_kernel.enums 单元测试."""

from ditto_kernel.enums import (
    AssetClass,
    Exchange,
    ImpactModel,
    OrderSide,
    RiskScope,
    RunStatus,
)


class TestAssetClass:
    """AssetClass 枚举测试."""

    def test_members(self) -> None:
        """应包含 6 个成员."""
        assert len(AssetClass) == 6

    def test_values(self) -> None:
        """验证所有成员值."""
        assert AssetClass.STOCK == "stock"
        assert AssetClass.ETF == "etf"
        assert AssetClass.INDEX == "index"
        assert AssetClass.FUTURE == "future"
        assert AssetClass.BOND == "bond"
        assert AssetClass.FUND == "fund"

    def test_is_strenum(self) -> None:
        """应为 StrEnum，支持直接字符串比较."""
        assert AssetClass.STOCK == "stock"


class TestExchange:
    """Exchange 枚举测试（MIC 风格）."""

    def test_members(self) -> None:
        """应包含 3 个 A 股交易所."""
        assert len(Exchange) == 3

    def test_values(self) -> None:
        """验证 MIC 风格值."""
        assert Exchange.XSHE == "XSHE"
        assert Exchange.XSHG == "XSHG"
        assert Exchange.XBSE == "XBSE"


class TestOrderSide:
    """OrderSide 枚举测试."""

    def test_members(self) -> None:
        """应包含 2 个成员."""
        assert len(OrderSide) == 2

    def test_values(self) -> None:
        assert OrderSide.BUY == "buy"
        assert OrderSide.SELL == "sell"


class TestRunStatus:
    """RunStatus 枚举测试."""

    def test_members(self) -> None:
        """应包含 5 个成员."""
        assert len(RunStatus) == 5

    def test_values(self) -> None:
        assert RunStatus.PENDING == "pending"
        assert RunStatus.RUNNING == "running"
        assert RunStatus.COMPLETED == "completed"
        assert RunStatus.FAILED == "failed"
        assert RunStatus.CANCELLED == "cancelled"


class TestRiskScope:
    """RiskScope 枚举测试."""

    def test_members(self) -> None:
        """应包含 2 个成员."""
        assert len(RiskScope) == 2

    def test_values(self) -> None:
        assert RiskScope.INSTRUMENT == "instrument"
        assert RiskScope.PORTFOLIO == "portfolio"


class TestImpactModel:
    """ImpactModel 枚举测试."""

    def test_members(self) -> None:
        """应包含 2 个成员."""
        assert len(ImpactModel) == 2

    def test_values(self) -> None:
        assert ImpactModel.NONE == "none"
        assert ImpactModel.VOLUME_SHARE == "volume_share"

    def test_is_strenum(self) -> None:
        """应为 StrEnum，支持直接字符串比较."""
        assert ImpactModel.NONE == "none"
