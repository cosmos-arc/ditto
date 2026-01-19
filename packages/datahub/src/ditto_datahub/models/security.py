"""Security-related data models."""

from pydantic import BaseModel, Field


class SecurityRegistration(BaseModel):
    """
    证券注册信息配置对象。

    封装注册新证券所需的所有参数，提供类型安全和清晰的接口。

    Attributes:
        src_code: 源代码（如 "600000.SH"）
        symbol: 显示符号（如 "600000"）
        name: 证券名称
        exchange: 交易所代码（如 "SSE", "SZSE"）
        asset_class: 资产类别（stock/etf/index）
        list_date: 上市日期（YYYY-MM-DD 格式）
        source: 数据源标识符（默认 "tushare"）
        board: 板块代码（可选）

    Examples:
        >>> registration = SecurityRegistration(
        ...     src_code="600000.SH",
        ...     symbol="600000",
        ...     name="浦发银行",
        ...     exchange="SSE",
        ...     asset_class="stock",
        ...     list_date="1999-11-10",
        ... )
        >>> sid = accessor.register(registration)

    """

    src_code: str = Field(description="源代码 (如 '600000.SH')")
    symbol: str = Field(description="显示符号 (如 '600000')")
    name: str = Field(description="证券名称")
    exchange: str = Field(description="交易所代码 (如 'SSE', 'SZSE')")
    asset_class: str = Field(description="资产类别 (stock/etf/index)")
    list_date: str = Field(description="上市日期 (YYYY-MM-DD 格式)")
    source: str = Field(default="tushare", description="数据源标识符")
    board: str | None = Field(default=None, description="板块代码 (可选)")
