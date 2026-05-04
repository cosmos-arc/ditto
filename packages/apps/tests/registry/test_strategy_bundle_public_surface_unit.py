"""Strategy registry bundle public surface tests."""

from __future__ import annotations

from dataclasses import fields
from types import UnionType
from typing import get_args, get_origin, get_type_hints

from ditto_apps.registry.contexts.bundle import StrategyBundle


def _annotation_paths(annotation: object) -> set[str]:
    origin = get_origin(annotation)
    if origin is UnionType:
        return {
            path
            for arg in get_args(annotation)
            if arg is not type(None)
            for path in _annotation_paths(arg)
        }
    module = getattr(annotation, "__module__", "")
    qualname = getattr(annotation, "__qualname__", "")
    if module and qualname:
        return {f"{module}.{qualname}"}
    return {str(annotation)}


def test_strategy_bundle_does_not_expose_storage_implementation_types() -> None:
    type_hints = get_type_hints(StrategyBundle)
    field_types = {
        path
        for field in fields(StrategyBundle)
        for path in _annotation_paths(type_hints[field.name])
    }

    assert not any(".storage.sqlite." in value for value in field_types)
