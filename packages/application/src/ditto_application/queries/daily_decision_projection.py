"""Daily Decision V2 只读模型的纯投影函数。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Literal, cast

import orjson
from ditto_strategy.models import StrategyArtifactRecord
from ditto_strategy.runs.models import StrategyRunRecord

from ditto_application.execution_dto import (
    ActualPositionSnapshot,
    ManualExecutionFill,
    TradeIntent,
    record_to_snapshot,
)
from ditto_application.queries.account import AccountBaselineReadModel

_BLOCKED_DATA_ERROR = "blocked:REQUIRED_DATA_NOT_READY"
_DATASET_STATUSES = frozenset({"ready", "missing", "stale", "dq_failed", "unknown"})


@dataclass(frozen=True)
class MissingPackageRunProjection:
    """Signal Package 缺失时，从确定性 run 恢复的受控证据。"""

    outcome: Literal["blocked", "failed"]
    required_datasets: tuple[str, ...]
    dataset_snapshots: dict[str, str]
    dataset_states: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class DailyDecisionDatasetProjection:
    """V2 data 分区及其 readiness 事实。"""

    required_datasets: tuple[str, ...]
    dataset_snapshots: dict[str, str]
    dataset_states: tuple[dict[str, object], ...]
    data_ready: bool


def matching_deterministic_run(
    run: StrategyRunRecord | None,
    *,
    expected_batch_key: str | None,
    expected_strategy_id: str,
    expected_strategy_version: str | None,
    expected_mode: str,
) -> StrategyRunRecord | None:
    """仅接受与查询身份完全一致的确定性运行记录。"""
    if (
        run is None
        or expected_batch_key is None
        or expected_strategy_version is None
        or run.run_id != expected_batch_key
        or run.strategy_id != expected_strategy_id
        or run.strategy_version != expected_strategy_version
        or run.mode != expected_mode
    ):
        return None
    return run


def project_missing_package_run(
    run: StrategyRunRecord | None,
    *,
    expected_batch_key: str | None,
    expected_signal_date: str | None,
    expected_strategy_id: str,
    expected_strategy_version: str | None,
    expected_mode: str,
) -> MissingPackageRunProjection | None:
    """按受控错误前缀恢复缺包 run，不采信身份不匹配的配置证据。"""
    run = matching_deterministic_run(
        run,
        expected_batch_key=expected_batch_key,
        expected_strategy_id=expected_strategy_id,
        expected_strategy_version=expected_strategy_version,
        expected_mode=expected_mode,
    )
    if run is None:
        return None
    if run.error_message == _BLOCKED_DATA_ERROR:
        required, snapshots, states = _blocked_dataset_evidence(
            run.config_json,
            expected_batch_key=run.run_id,
            expected_signal_date=expected_signal_date,
        )
        return MissingPackageRunProjection(
            outcome="blocked",
            required_datasets=required,
            dataset_snapshots=snapshots,
            dataset_states=states,
        )
    if run.error_message.startswith("failed:"):
        return MissingPackageRunProjection(
            outcome="failed",
            required_datasets=(),
            dataset_snapshots={},
            dataset_states=(),
        )
    return None


def _blocked_dataset_evidence(
    config_json: str,
    *,
    expected_batch_key: str,
    expected_signal_date: str | None,
) -> tuple[
    tuple[str, ...],
    dict[str, str],
    tuple[dict[str, object], ...],
]:
    config = _matching_blocked_config(
        config_json,
        expected_batch_key=expected_batch_key,
        expected_signal_date=expected_signal_date,
    )
    if config is None:
        return _empty_dataset_evidence()
    return _dataset_evidence(config.get("required_dataset_states"))


def _matching_blocked_config(
    config_json: str,
    *,
    expected_batch_key: str,
    expected_signal_date: str | None,
) -> dict[object, object] | None:
    if expected_signal_date is None:
        return None
    try:
        raw_config = orjson.loads(config_json)
    except orjson.JSONDecodeError:
        return None
    if not isinstance(raw_config, dict):
        return None
    config = cast(dict[object, object], raw_config)
    if (
        config.get("batch_key") != expected_batch_key
        or config.get("signal_date") != expected_signal_date
        or config.get("outcome") != "blocked"
    ):
        return None
    return config


def _dataset_evidence(
    raw_states: object,
) -> tuple[
    tuple[str, ...],
    dict[str, str],
    tuple[dict[str, object], ...],
]:
    if not isinstance(raw_states, list):
        return _empty_dataset_evidence()

    datasets: list[str] = []
    snapshots: dict[str, str] = {}
    states: list[dict[str, object]] = []
    for raw_state in cast(list[object], raw_states):
        if not isinstance(raw_state, dict):
            return (), {}, ()
        state = cast(dict[object, object], raw_state)
        dataset = optional_string(state.get("dataset"))
        status = optional_string(state.get("status"))
        snapshot_value = state.get("snapshot_id")
        snapshot_id = optional_string(snapshot_value)
        reason = state.get("reason", "")
        if (
            dataset is None
            or dataset in datasets
            or status not in _DATASET_STATUSES
            or (snapshot_value is not None and snapshot_id is None)
            or not isinstance(reason, str)
        ):
            return _empty_dataset_evidence()
        datasets.append(dataset)
        if snapshot_id is not None:
            snapshots[dataset] = snapshot_id
        states.append(
            {
                "dataset": dataset,
                "status": status,
                "snapshot_id": snapshot_id,
                "reason": reason,
            }
        )
    return tuple(datasets), snapshots, tuple(states)


def _empty_dataset_evidence() -> tuple[
    tuple[str, ...],
    dict[str, str],
    tuple[dict[str, object], ...],
]:
    return (), {}, ()


def optional_string(value: object) -> str | None:
    """仅返回非空字符串，其他值返回 ``None``。"""
    return value if isinstance(value, str) and value else None


def string_tuple(value: object) -> tuple[str, ...]:
    """从列表或元组中提取非空字符串。"""
    items: list[object] | tuple[object, ...]
    if isinstance(value, list):
        items = cast(list[object], value)
    elif isinstance(value, tuple):
        items = cast(tuple[object, ...], value)
    else:
        return ()
    return tuple(item for item in items if isinstance(item, str) and item)


def is_string_sequence(value: object) -> bool:
    """判断值是否为只包含非空字符串的列表或元组。"""
    if not isinstance(value, (list, tuple)):
        return False
    items = cast(list[object] | tuple[object, ...], value)
    return all(isinstance(item, str) and bool(item) for item in items)


def string_mapping(value: object) -> dict[str, str]:
    """从映射中提取非空字符串键值对。"""
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in cast(dict[object, object], value).items()
        if isinstance(key, str) and isinstance(item, str) and item
    }


def project_dataset_states(
    raw_states: object,
    *,
    required_datasets: tuple[str, ...],
    dataset_snapshots: Mapping[str, str],
) -> tuple[dict[str, object], ...]:
    """将持久化数据集状态元数据投影为 V2 只读模型。"""
    by_dataset: dict[str, dict[str, object]] = {}
    if isinstance(raw_states, (list, tuple)):
        for raw_state in cast(list[object] | tuple[object, ...], raw_states):
            if not isinstance(raw_state, dict):
                continue
            state = cast(dict[str, object], raw_state)
            dataset = optional_string(state.get("dataset"))
            if dataset is None:
                continue
            status = optional_string(state.get("status")) or "unknown"
            snapshot_id = optional_string(state.get("snapshot_id"))
            by_dataset[dataset] = {
                "dataset": dataset,
                "status": status,
                "snapshot_id": snapshot_id,
                "reason": optional_string(state.get("reason")) or "",
            }
    return tuple(
        by_dataset.get(
            dataset,
            {
                "dataset": dataset,
                "status": "unknown",
                "snapshot_id": dataset_snapshots.get(dataset),
                "reason": "DATASET_STATE_MISSING",
            },
        )
        for dataset in required_datasets
    )


def project_datasets(
    metadata: Mapping[str, object],
    *,
    package_exists: bool,
    missing_package_run: MissingPackageRunProjection | None,
) -> DailyDecisionDatasetProjection:
    """从 package 或确定性缺包 run 投影 V2 data 分区。"""
    if missing_package_run is not None:
        return DailyDecisionDatasetProjection(
            required_datasets=missing_package_run.required_datasets,
            dataset_snapshots=missing_package_run.dataset_snapshots,
            dataset_states=missing_package_run.dataset_states,
            data_ready=missing_package_run.outcome != "blocked",
        )

    raw_required_datasets = metadata.get("required_datasets")
    required_dataset_contract_valid = not package_exists or is_string_sequence(
        raw_required_datasets
    )
    required_datasets = string_tuple(raw_required_datasets)
    dataset_snapshots = string_mapping(metadata.get("dataset_snapshot_ids"))
    dataset_states = project_dataset_states(
        metadata.get("required_dataset_states"),
        required_datasets=required_datasets,
        dataset_snapshots=dataset_snapshots,
    )
    data_ready = not package_exists or (
        required_dataset_contract_valid
        and all(
            state["status"] == "ready" and state["snapshot_id"] is not None
            for state in dataset_states
        )
    )
    return DailyDecisionDatasetProjection(
        required_datasets=required_datasets,
        dataset_snapshots=dataset_snapshots,
        dataset_states=dataset_states,
        data_ready=data_ready,
    )


def intent_payloads(value: object) -> tuple[dict[str, object], ...]:
    """将持久化意图元数据解析为字典载荷。"""
    if not isinstance(value, list):
        return ()
    return tuple(
        cast(dict[str, object], item)
        for item in cast(list[object], value)
        if isinstance(item, dict)
    )


def _float_or_default(value: object, *, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) else default


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _finite_float(value: object, *, positive: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    if not isfinite(parsed) or (positive and parsed <= 0.0):
        return None
    return parsed


def _sizing_readiness(value: object) -> str | None:
    return (
        value
        if isinstance(value, str) and value in {"ready", "review", "blocked"}
        else None
    )


def project_actions(
    *,
    raw_intents: tuple[dict[str, object], ...],
    persisted_intents: Mapping[str, TradeIntent],
    risk_flags: tuple[str, ...],
    effective_fills: tuple[ManualExecutionFill, ...],
) -> tuple[dict[str, object], ...]:
    """将 package 意图和有效成交投影为可执行动作。"""
    fills_by_intent: dict[str, int] = {}
    for fill in effective_fills:
        fills_by_intent[fill.intent_id] = (
            fills_by_intent.get(fill.intent_id, 0) + fill.quantity
        )
    actions: list[dict[str, object]] = []
    for raw in raw_intents:
        intent_id = optional_string(raw.get("intent_id"))
        instrument_id = raw.get("instrument_id")
        if intent_id is None or not isinstance(instrument_id, int):
            continue
        persisted = persisted_intents.get(intent_id)
        raw_quantity = _nonnegative_int(raw.get("raw_quantity"))
        rounded_quantity = _nonnegative_int(raw.get("rounded_quantity"))
        suggested_quantity = rounded_quantity
        reference_price = _finite_float(raw.get("reference_price"), positive=True)
        lot_size = _positive_int(raw.get("lot_size"))
        cash_impact = _finite_float(raw.get("cash_impact"))
        sizing_reason = optional_string(raw.get("sizing_reason"))
        sizing_readiness = _sizing_readiness(raw.get("sizing_readiness"))
        filled_quantity = fills_by_intent.get(intent_id, 0)
        remaining_quantity = (
            max(0, suggested_quantity - filled_quantity)
            if suggested_quantity is not None
            else None
        )
        actions.append(
            {
                "intent_id": intent_id,
                "instrument_id": instrument_id,
                "direction": str(raw.get("direction", "")),
                "target_weight": _float_or_default(raw.get("target_weight")),
                "current_weight": _float_or_default(raw.get("current_weight")),
                "delta_weight": _float_or_default(raw.get("delta_weight")),
                "raw_quantity": raw_quantity,
                "rounded_quantity": rounded_quantity,
                "suggested_quantity": suggested_quantity,
                "reference_price": reference_price,
                "lot_size": lot_size,
                "cash_impact": cash_impact,
                "reason": sizing_reason,
                "sizing_readiness": sizing_readiness,
                "risk_flags": risk_flags,
                "intent_status": (persisted.status if persisted is not None else None),
                "filled_quantity": filled_quantity,
                "remaining_quantity": remaining_quantity,
            }
        )
    return tuple(
        sorted(
            actions,
            key=lambda action: cast(int, action["instrument_id"]),
        )
    )


def persisted_intents_match_package(
    *,
    raw_intents: tuple[dict[str, object], ...],
    persisted_intents: Mapping[str, TradeIntent],
) -> bool:
    """每条 package intent 必须唯一且与当前持久化业务事实一致。"""
    seen: set[str] = set()
    for raw in raw_intents:
        intent_id = optional_string(raw.get("intent_id"))
        if intent_id is None or intent_id in seen:
            return False
        seen.add(intent_id)
        persisted = persisted_intents.get(intent_id)
        if persisted is None or persisted.status == "superseded":
            return False
        if not _persisted_intent_matches(raw, persisted):
            return False
    non_superseded_ids = {
        intent_id
        for intent_id, intent in persisted_intents.items()
        if intent.status != "superseded"
    }
    return seen == non_superseded_ids


def _persisted_intent_matches(
    raw: Mapping[str, object],
    persisted: TradeIntent,
) -> bool:
    """比较不可变业务字段；允许持久化 status 随成交生命周期变化。"""
    expected = {
        "strategy_id": persisted.strategy_id,
        "signal_date": persisted.signal_date,
        "instrument_id": persisted.instrument_id,
        "direction": persisted.direction,
        "target_weight": persisted.target_weight,
        "current_weight": persisted.current_weight,
        "delta_weight": persisted.delta_weight,
        "quantity": persisted.quantity,
    }
    return all(raw.get(field) == value for field, value in expected.items())


def has_ready_sizing_evidence(action: Mapping[str, object]) -> bool:
    """判断动作是否包含全部必需的仓位计算证据。"""
    raw_quantity = action.get("raw_quantity")
    rounded_quantity = action.get("rounded_quantity")
    return (
        isinstance(raw_quantity, int)
        and isinstance(rounded_quantity, int)
        and action.get("suggested_quantity") == rounded_quantity
        and isinstance(action.get("reference_price"), float)
        and isinstance(action.get("lot_size"), int)
        and isinstance(action.get("cash_impact"), float)
        and isinstance(action.get("reason"), str)
        and bool(action["reason"])
        and action.get("sizing_readiness") == "ready"
    )


def unresolved_conflicts(
    *,
    actions: tuple[dict[str, object], ...],
    run_outcome: str,
) -> tuple[str, ...]:
    """将持久化重跑冲突和超额成交投影为稳定证据。"""
    conflicts: list[str] = []
    if run_outcome == "rerun_conflict":
        conflicts.append("RERUN_CONFLICT")
    for action in actions:
        suggested = action["suggested_quantity"]
        filled = action["filled_quantity"]
        if (
            isinstance(suggested, int)
            and isinstance(filled, int)
            and filled > suggested
        ):
            conflicts.append(f"OVERFILLED:{action['intent_id']}")
    return tuple(conflicts)


def resolve_run_outcome(
    *,
    package: StrategyArtifactRecord | None,
    run: StrategyRunRecord | None,
    metadata: Mapping[str, object],
) -> str:
    """将持久化 package 与运行生命周期记录解析为统一结果。"""
    if run is not None:
        run_status = str(run.status)
        if run_status != "completed":
            return run_status
    persisted = optional_string(metadata.get("outcome"))
    if persisted is not None:
        return persisted
    if run is not None:
        return str(run.status)
    return "missing" if package is None else "completed"


def project_baseline_positions(
    baseline: AccountBaselineReadModel | None,
) -> tuple[ActualPositionSnapshot, ...]:
    """将持久化账户基线持仓投影为执行快照。"""
    if baseline is None:
        return ()
    return tuple(record_to_snapshot(position) for position in baseline.positions)


def baseline_matches_identity(
    baseline: AccountBaselineReadModel | None,
    *,
    account_id: str | None,
    sleeve_id: str | None,
    strategy_id: str,
) -> bool:
    """判断账户基线是否属于 package 执行身份。"""
    if baseline is None or account_id is None or sleeve_id is None:
        return False
    account = baseline.account
    return (
        account.account_id == account_id
        and account.run_id == sleeve_id
        and account.strategy_id == strategy_id
    )


def project_account_positions(
    baseline: AccountBaselineReadModel | None,
    positions: tuple[ActualPositionSnapshot, ...],
) -> dict[str, object]:
    """将账户基线证据投影为 V2 只读模型。"""
    if baseline is None:
        return {
            "baseline_id": None,
            "account_id": None,
            "sleeve_id": None,
            "cash_available": None,
            "cash_settled": None,
            "cash_frozen": None,
            "total_value": None,
            "nav": None,
            "exposure": None,
            "as_of": None,
            "positions": (),
        }
    account = baseline.account
    return {
        "baseline_id": account.snapshot_id,
        "account_id": account.account_id,
        "sleeve_id": account.run_id,
        "cash_available": account.cash_available,
        "cash_settled": account.cash_settled,
        "cash_frozen": account.cash_frozen,
        "total_value": account.total_value,
        "nav": account.nav,
        "exposure": account.exposure,
        "as_of": account.snapshot_date,
        "positions": positions,
    }
