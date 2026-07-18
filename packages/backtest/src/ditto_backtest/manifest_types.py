"""
回测清单数据类型 — RunMode / InputRef / RuleRef / RunManifest.

从 manifest.py 提取的 frozen dataclass 类型定义，
供 manifest.py 和其他模块导入使用。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ditto_kernel.identity import InstrumentId
from ditto_kernel.time_semantics import DEFAULT_PIT_TIME_COLUMN, PIT_POLICY_FAIL_CLOSED

from ditto_backtest.config import validate_spec_hash

__all__ = [
    "InputRef",
    "RuleRef",
    "RunManifest",
    "RunMode",
]


class RunMode(StrEnum):
    """引擎运行模式 — 4 种（R7）。"""

    RESEARCH = "research"
    RECOMMENDATION = "recommendation"
    BACKTEST = "backtest"
    LIVE = "live"


@dataclass(frozen=True)
class InputRef:
    """
    输入数据引用 — 含数据指纹，用于可复现性审计.

    Attributes:
        instrument_id: 标的 ID
        data_hash: 数据内容哈希（格式: "sha256:<hex>"）
        date_range: 数据覆盖日期范围 (start, end)
        source: 数据来源描述（如文件路径或数据源标识）
        source_snapshot_id: 数据源快照/版本 ID（空字符串表示当前来源未提供）

    """

    instrument_id: InstrumentId
    data_hash: str
    date_range: tuple[str, str]
    source: str
    source_snapshot_id: str = ""


@dataclass(frozen=True)
class RuleRef:
    """
    单条规则引用 — 捕获某次运行中实际使用的规则版本。

    Attributes:
        instrument_id: 标的 ID
        definition_version: InstrumentDefinition 哈希（前 8 位 hex）
        trading_rule_as_of: 交易规则生效日期
        fee_schedule_as_of: 费率生效日期
        trading_rule_effective_to: 交易规则失效日期（V1 留空）
        fee_schedule_effective_to: 费率失效日期（V1 留空）

    """

    instrument_id: InstrumentId
    definition_version: str
    trading_rule_as_of: str
    fee_schedule_as_of: str
    trading_rule_effective_to: str = ""
    fee_schedule_effective_to: str = ""


@dataclass(frozen=True)
class RunManifest:
    """
    一次引擎运行的完整清单 — frozen, 运行结束时构建.

    Attributes:
        run_id: 运行唯一 ID
        strategy_id: 策略 ID
        strategy_version: 策略版本
        mode: 运行模式
        input_refs: 输入标的 ID 列表（向后兼容）
        input_ref_details: 输入数据引用详情（含数据指纹）
        parameter_overrides: 参数覆盖列表
        rule_refs: 规则引用列表
        artifacts: 产出物列表
        config_hash: 配置哈希
        engine_version: 引擎版本
        rule_resolution_policy: 规则解析策略（S2）
        universe_hash: 标的池哈希
        spec_hash: 策略规格哈希
        dependency_versions: 依赖版本列表
        random_seed: 随机种子（None 表示未指定）
        pit_time_column: PIT 安全时间列
        pit_policy: PIT 时间策略
        unsafe_time_policy: 显式 unsafe 研究时间策略（空字符串表示未启用）
        knowledge_lag_days: 决策知识延迟天数
        created_at: 创建时间 (RFC3339 UTC)

    """

    run_id: str
    strategy_id: str
    strategy_version: str
    mode: RunMode
    created_at: str
    spec_hash: str
    input_refs: tuple[InstrumentId, ...] = ()
    input_ref_details: tuple[InputRef, ...] = ()
    parameter_overrides: tuple[str, ...] = ()
    rule_refs: tuple[RuleRef, ...] = ()
    artifacts: tuple[str, ...] = ()
    config_hash: str = ""
    engine_version: str = ""
    rule_resolution_policy: str = "as_of_date"
    universe_hash: str = ""
    dependency_versions: tuple[str, ...] = ()
    random_seed: int | None = None
    pit_time_column: str = DEFAULT_PIT_TIME_COLUMN
    pit_policy: str = PIT_POLICY_FAIL_CLOSED
    unsafe_time_policy: str = ""
    knowledge_lag_days: int = 1

    def __post_init__(self) -> None:
        """A persisted run manifest always has resolved canonical strategy identity."""
        validate_spec_hash(self.spec_hash)
