"""
回测清单构建函数 — hash 计算、manifest 构建/序列化、规则收集.

从 manifest.py 提取的函数逻辑，供 manifest.py re-export。
类型定义在 manifest_types.py 中。
"""

from __future__ import annotations

import hashlib
import importlib.metadata
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import orjson
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import (
    InstrumentDefinition,
    InstrumentRules,
)
from loguru import logger

from ditto_backtest.config import EngineConfig, validate_spec_hash
from ditto_backtest.manifest_types import (
    InputRef,
    RuleRef,
    RunManifest,
    RunMode,
)
from ditto_backtest.provenance import aggregate_source_snapshot_id

__all__ = [
    "RuleRefCollector",
    "RunManifestInputEvidence",
    "build_run_manifest",
    "hash_config",
    "hash_universe",
    "serialize_manifest",
]

_HASH_TRUNCATE_LEN = 16


@dataclass(frozen=True)
class RunManifestInputEvidence:
    """Manifest 构建所需的输入集合、指纹与上游快照证据。"""

    input_instruments: set[InstrumentId]
    bar_fingerprints: dict[InstrumentId, list[tuple[str, float]]]
    source_snapshot_ids: Mapping[InstrumentId, str | Iterable[str]] | None = None


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
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_HASH_TRUNCATE_LEN]


def hash_universe(instrument_ids: set[InstrumentId]) -> str:
    """对 universe (sorted instrument IDs) 做 SHA-256, 返回前 16 位 hex。"""
    payload = ",".join(str(i) for i in sorted(instrument_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_HASH_TRUNCATE_LEN]


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
                logger.debug(
                    "RuleRefCollector.observe: 跳过格式不匹配的规则元组: {t}",
                    t=rule_tuple,
                )
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


def build_run_manifest(
    *,
    run_id: str,
    config: EngineConfig,
    spec_hash: str,
    input_evidence: RunManifestInputEvidence,
    rule_refs: tuple[RuleRef, ...],
    random_seed: int,
) -> RunManifest:
    """构建 RunManifest — 记录运行配置、规则引用、输入依赖等治理字段."""
    validated_spec_hash = validate_spec_hash(spec_hash)
    if validated_spec_hash != config.spec_hash:
        msg = "spec_hash does not match EngineConfig.spec_hash"
        raise ValueError(msg)
    input_instruments = input_evidence.input_instruments
    input_refs = tuple(sorted(input_instruments))
    config_hash = hash_config(
        start_date=config.start_date,
        end_date=config.end_date,
        initial_cash=config.initial_cash,
        strategy_id=config.strategy_id,
        rebalance_freq=config.rebalance_freq,
        engine_version=config.engine_version,
    )
    return RunManifest(
        run_id=run_id,
        strategy_id=config.strategy_id,
        strategy_version=config.strategy_version,
        mode=RunMode.BACKTEST,
        input_refs=input_refs,
        input_ref_details=_build_input_ref_details(
            input_evidence.bar_fingerprints,
            source_snapshot_ids=input_evidence.source_snapshot_ids,
        ),
        parameter_overrides=config.parameter_overrides,
        rule_refs=rule_refs,
        config_hash=config_hash,
        engine_version=config.engine_version,
        spec_hash=validated_spec_hash,
        base_spec_hash=config.base_spec_hash,
        parameter_hash=config.parameter_hash,
        effective_parameters=config.effective_parameters,
        research_snapshot_id=config.research_snapshot_id,
        research_snapshot_manifest_hash=config.research_snapshot_manifest_hash,
        universe_hash=hash_universe(input_instruments),
        dependency_versions=_collect_dependency_versions(),
        random_seed=random_seed,
        knowledge_lag_days=config.knowledge_lag_days,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _build_input_ref_details(
    bar_fingerprints: dict[InstrumentId, list[tuple[str, float]]],
    *,
    source_snapshot_ids: Mapping[InstrumentId, str | Iterable[str]] | None = None,
) -> tuple[InputRef, ...]:
    """
    从 bar_fingerprints 构建 InputRef 列表.

    对每个 instrument 的 sorted (date, close) 元组列表计算 SHA-256 哈希,
    生成 InputRef(instrument_id, data_hash, date_range, source, source_snapshot_id).
    """
    refs: list[InputRef] = []
    source_snapshot_ids = source_snapshot_ids or {}
    for iid in sorted(bar_fingerprints.keys()):
        entries = bar_fingerprints[iid]
        sorted_entries = sorted(entries, key=lambda t: t[0])
        payload = ",".join(f"{d}:{c}" for d, c in sorted_entries)
        data_hash = (
            "sha256:"
            + hashlib.sha256(
                payload.encode("utf-8"),
            ).hexdigest()[:_HASH_TRUNCATE_LEN]
        )
        dates = [d for d, _ in sorted_entries]
        date_range = (dates[0], dates[-1]) if dates else ("", "")
        refs.append(
            InputRef(
                instrument_id=iid,
                data_hash=data_hash,
                date_range=date_range,
                source="backtest:data_feed",
                source_snapshot_id=_source_snapshot_id_for_instrument(
                    source_snapshot_ids,
                    iid,
                ),
            ),
        )
    return tuple(refs)


def _source_snapshot_id_for_instrument(
    source_snapshot_ids: Mapping[InstrumentId, str | Iterable[str]],
    iid: InstrumentId,
) -> str:
    """Return a manifest-safe single source snapshot ID for one instrument."""
    values = source_snapshot_ids.get(iid)
    if values is None:
        return ""
    if isinstance(values, str):
        aggregate = aggregate_source_snapshot_id((values,))
    else:
        aggregate = aggregate_source_snapshot_id(values)
    return aggregate or ""


def _collect_dependency_versions() -> tuple[str, ...]:
    """收集当前运行环境的依赖版本（用于可复现性审计）."""
    packages = ("polars",)
    versions: list[str] = []
    for pkg in sorted(packages):
        try:
            ver = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            ver = "unknown"
        versions.append(f"{pkg}=={ver}")
    return tuple(versions)
