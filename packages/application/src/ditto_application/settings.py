"""交易策略配置模型."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TradingSettings(BaseModel):
    """交易策略配置。"""

    model_config = ConfigDict(extra="ignore")

    default_universe: str = Field(default="csi300", description="默认标的池")
    max_position_pct: float = Field(default=0.1, description="单只标的最大仓位百分比")
    risk_free_rate: float = Field(default=0.025, description="无风险利率")
    benchmark: str = Field(default="000300.SH", description="基准指数代码")
    cost_bps: float = Field(default=3.0, description="交易成本 (基点)")
    slippage_bps: float = Field(default=1.0, description="滑点成本 (基点)")
    trading_calendar_start: str = Field(
        default="2020-01-01",
        description="交易日历起始日期 (YYYY-MM-DD)",
    )
    trading_calendar_end: str = Field(
        default="2030-12-31",
        description="交易日历结束日期 (YYYY-MM-DD)",
    )

    @field_validator("max_position_pct")
    @classmethod
    def validate_max_position_pct(cls, v: float) -> float:
        """max_position_pct 必须在 (0, 1] 范围内。"""
        if v <= 0 or v > 1:
            raise ValueError("max_position_pct 必须在 (0, 1] 范围内")
        return v


# 默认值仅用于 testing/staging：``code_version`` 必须是非空 canonical 字符串，
# ``environment_lock_hash`` 必须是 64 位小写 hex SHA-256 摘要（由
# ``CodeEnvironmentLock.__post_init__`` 强制）。apps composition root 在 C3 会用
# ``git rev-parse HEAD`` 与 Python 环境身份摘要 覆盖这两个字段；application 层
# 自身不做 git/lockfile I/O。
_DEFAULT_CODE_VERSION = "unversioned"
_DEFAULT_ENVIRONMENT_LOCK_HASH = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)


class ResearchExecutionSettings(BaseModel):
    """
    R3 研究执行 bundle 的 composition-root 配置。

    这两个字段描述当前运行环境的代码版本与依赖锁：``code_version`` 是 git HEAD
    sha，``environment_lock_hash`` 绑定依赖锁、解释器来源和平台。
    构建系统注入这两个身份字段，apps composition root（C3）读取；
    application 层只读取它们以构建 :class:`CodeEnvironmentLock`。
    """

    model_config = ConfigDict(extra="ignore")

    code_version: str = Field(
        default=_DEFAULT_CODE_VERSION,
        description="git HEAD sha, C3 由 apps composition root 写入",
    )
    environment_lock_hash: str = Field(
        default=_DEFAULT_ENVIRONMENT_LOCK_HASH,
        description="Python 环境身份摘要, C3 由 apps 计算",
    )


__all__ = ["ResearchExecutionSettings", "TradingSettings"]
