"""Catalog strategy record to EOD request boundary mapping."""

from typing import cast

from ditto_data.models.common import Dataset
from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders.deserialization import (
    default_required_datasets_for_template,
    deserialize_strategy_spec,
)
from ditto_application.exceptions import AppBuilderError
from ditto_application.processes.execution.eod_coordinator import EodStrategyRequest

__all__ = ["eod_request_from_strategy_spec"]


def eod_request_from_strategy_spec(spec: StrategySpecRecord) -> EodStrategyRequest:
    """从 catalog record 提取 EOD 依赖，无效或未知 spec fail closed。"""
    raw_required = spec.spec_json.get("required_datasets")
    required_items: list[object] | tuple[object, ...] | None = None
    if isinstance(raw_required, list):
        required_items = cast(list[object], raw_required)
    elif isinstance(raw_required, tuple):
        required_items = cast(tuple[object, ...], raw_required)

    explicit: tuple[str, ...] | None = None
    if required_items and all(
        isinstance(item, str) and item for item in required_items
    ):
        explicit = tuple(cast(str, item) for item in required_items)

    template = spec.spec_json.get("template")
    template_required = (
        default_required_datasets_for_template(template)
        if isinstance(template, str)
        else ()
    )
    required: tuple[str, ...] | None = None
    if explicit is not None:
        required = tuple(dict.fromkeys((*template_required, *explicit)))
    else:
        try:
            required = deserialize_strategy_spec(spec).required_datasets
        except (AppBuilderError, TypeError, ValueError):
            # 不能把无法解析的策略依赖降级为空集。
            required = None

    if not required or any(not _is_known_dataset(item) for item in required):
        required = ("__invalid_strategy_spec__",)
    return EodStrategyRequest(
        strategy_id=spec.strategy_id,
        strategy_version=str(spec.version),
        required_datasets=required,
    )


def _is_known_dataset(dataset: str) -> bool:
    try:
        Dataset(dataset)
    except ValueError:
        return False
    return True
