"""
RunManifest / RuleRef / RuleRefCollector / serialize_manifest — 回测运行清单.

Task 1B — RuleRefs + RunManifest (Phase 4 Part 03).

- RunMode(StrEnum): 4 种运行模式
- RuleRef(frozen): 单条规则引用（instrument + 版本 + 时间锚点）
- RunManifest(frozen): 一次引擎运行的完整清单
- RuleRefCollector: 运行期间收集规则引用（first_observed 策略）
- serialize_manifest: canonical JSON 序列化（字节级稳定）
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from enum import StrEnum

import orjson
from ditto_kernel.identity import InstrumentId

from ditto_engine.execution.rules import (
    InstrumentDefinition,
    InstrumentRules,
)

__all__ = [
    "InputRef",
    "RuleRef",
    "RuleRefCollector",
    "RunManifest",
    "RunMode",
    "hash_config",
    "hash_spec",
    "serialize_manifest",
]


# ---------------------------------------------------------------------------
# RunMode
# ---------------------------------------------------------------------------


class RunMode(StrEnum):
    """引擎运行模式 — 4 种（R7）。"""

    RESEARCH = "research"
    RECOMMENDATION = "recommendation"
    BACKTEST = "backtest"
    LIVE = "live"


# ---------------------------------------------------------------------------
# InputRef
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputRef:
    """
    输入数据引用 — 含数据指纹，用于可复现性审计.

    Attributes:
        instrument_id: 标的 ID
        data_hash: 数据内容哈希（格式: "sha256:<hex>"）
        date_range: 数据覆盖日期范围 (start, end)
        source: 数据来源描述（如文件路径或数据源标识）

    """

    instrument_id: InstrumentId
    data_hash: str
    date_range: tuple[str, str]
    source: str


# ---------------------------------------------------------------------------
# RuleRef
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# RunManifest
# ---------------------------------------------------------------------------


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
        created_at: 创建时间 (RFC3339 UTC)

    """

    run_id: str
    strategy_id: str
    strategy_version: str
    mode: RunMode
    created_at: str
    input_refs: tuple[InstrumentId, ...] = ()
    input_ref_details: tuple[InputRef, ...] = ()
    parameter_overrides: tuple[str, ...] = ()
    rule_refs: tuple[RuleRef, ...] = ()
    artifacts: tuple[str, ...] = ()
    config_hash: str = ""
    engine_version: str = ""
    rule_resolution_policy: str = "as_of_date"
    universe_hash: str = ""
    spec_hash: str = ""
    dependency_versions: tuple[str, ...] = ()
    random_seed: int | None = None


# ---------------------------------------------------------------------------
# _hash_definition
# ---------------------------------------------------------------------------


def _hash_definition(defn: InstrumentDefinition) -> str:
    """
    对 InstrumentDefinition 关键字段做 SHA-256, 返回前 8 位 hex.

    包含所有字段以保证定义变更一定产生不同哈希。
    """
    payload = (
        f"{defn.instrument_id}|{defn.asset_class}|{defn.exchange}"
        f"|{defn.currency}|{defn.tick_size}|{defn.lot_size}"
        f"|{defn.multiplier}|{defn.board_segment}|{defn.lifecycle_state}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


def hash_config(
    start_date: str,
    end_date: str,
    initial_cash: float,
    strategy_id: str,
    rebalance_freq: str,
    engine_version: str,
) -> str:
    """对 EngineConfig 关键字段做 SHA-256, 返回前 16 位 hex。"""
    payload = (
        f"{start_date}|{end_date}|{initial_cash}"
        f"|{strategy_id}|{rebalance_freq}|{engine_version}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def hash_spec(
    strategy_id: str,
    strategy_version: str,
    rebalance_freq: str,
) -> str:
    """对策略规格关键字段做 SHA-256, 返回前 16 位 hex。"""
    payload = f"{strategy_id}|{strategy_version}|{rebalance_freq}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def hash_universe(instrument_ids: set[InstrumentId]) -> str:
    """对 universe (sorted instrument IDs) 做 SHA-256, 返回前 16 位 hex。"""
    payload = ",".join(str(i) for i in sorted(instrument_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# RuleRefCollector
# ---------------------------------------------------------------------------


class RuleRefCollector:
    """
    规则引用收集器 — 运行期间收集每个 instrument 的规则版本.

    key = (instrument_id, definition_version, trading_rule_as_of, fee_schedule_as_of)
    策略: first_observed — 保留首次出现, 不去重覆盖 (F3).
    """

    def __init__(self) -> None:
        self._refs: dict[tuple[InstrumentId, str, str, str], RuleRef] = {}

    @property
    def rule_refs(self) -> tuple[RuleRef, ...]:
        """返回排序后的 rule_refs 元组。"""
        sorted_keys = sorted(self._refs.keys())
        return tuple(self._refs[k] for k in sorted_keys)

    def observe(
        self,
        date: str,
        rules: dict[InstrumentId, InstrumentRules] | None,
    ) -> None:
        """
        观察当日规则 — 收集新 key, 忽略已存在的 key (F3).

        Args:
            date: 交易日期（未使用，保留供未来扩展）
            rules: instrument_id → InstrumentRules 映射

        """
        if rules is None:
            return
        for instrument_id, rule_tuple in rules.items():
            try:
                defn, trading_rule, fee_schedule = rule_tuple
                key = (
                    instrument_id,
                    _hash_definition(defn),
                    trading_rule.as_of_date,
                    fee_schedule.as_of_date,
                )
            except (TypeError, ValueError, AttributeError):
                continue

            # F3: first_observed — 仅在 key 不存在时写入
            if key not in self._refs:
                self._refs[key] = RuleRef(
                    instrument_id=instrument_id,
                    definition_version=key[1],
                    trading_rule_as_of=trading_rule.as_of_date,
                    fee_schedule_as_of=fee_schedule.as_of_date,
                    trading_rule_effective_to="",
                    fee_schedule_effective_to="",
                )


# ---------------------------------------------------------------------------
# serialize_manifest
# ---------------------------------------------------------------------------


def serialize_manifest(manifest: RunManifest) -> str:
    """
    将 RunManifest 序列化为 canonical JSON 字符串.

    - key 排序 (OPT_SORT_KEYS)
    - 缩进 2 空格 (OPT_INDENT_2)
    - rule_refs 按 (instrument_id, definition_version, trading_rule_as_of,
      fee_schedule_as_of) 排序
    - input_ref_details 按 instrument_id 排序
    - 时间字段 RFC3339 UTC (P3)
    - 同 manifest 二次生成字节级一致 (P2)

    Args:
        manifest: 运行清单

    Returns:
        canonical JSON 字符串

    """
    # asdict 会将 frozen dataclass 转为 dict, StrEnum 转为 str
    raw = asdict(manifest)

    # rule_refs 排序 — 按 key 自然排序
    rule_refs: list[dict[str, str]] = raw["rule_refs"]
    sorted_refs = sorted(
        rule_refs,
        key=lambda r: (
            r["instrument_id"],
            r["definition_version"],
            r["trading_rule_as_of"],
            r["fee_schedule_as_of"],
        ),
    )
    raw["rule_refs"] = sorted_refs

    # input_ref_details 排序 — 按 instrument_id 排序
    input_ref_details = raw["input_ref_details"]
    raw["input_ref_details"] = sorted(
        input_ref_details,
        key=lambda r: int(r["instrument_id"]),
    )

    return orjson.dumps(
        raw,
        option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
    ).decode("utf-8")
