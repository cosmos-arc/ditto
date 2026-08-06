"""Shared canonical JSON value boundary tests."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from ditto_strategy.errors import StrategySpecError


class TestFreezeJsonMappingCycles:
    def test_rejects_self_referential_mapping_with_typed_field_path(self) -> None:
        from ditto_strategy.alpha._canonical_values import freeze_json_mapping

        source: dict[str, object] = {}
        source["self"] = source

        with pytest.raises(StrategySpecError) as exc_info:
            freeze_json_mapping(source, field_name="payload")

        assert exc_info.value.details["reason"] == "cyclic_canonical_json_value"
        assert exc_info.value.details["field_name"] == "payload.self"

    def test_rejects_mapping_list_cycle_with_typed_field_path(self) -> None:
        from ditto_strategy.alpha._canonical_values import freeze_json_mapping

        source: dict[str, object] = {}
        items: list[object] = [source]
        source["items"] = items

        with pytest.raises(StrategySpecError) as exc_info:
            freeze_json_mapping(source, field_name="payload")

        assert exc_info.value.details["reason"] == "cyclic_canonical_json_value"
        assert exc_info.value.details["field_name"] == "payload.items[0]"

    def test_allows_non_cyclic_shared_aliases(self) -> None:
        from ditto_strategy.alpha._canonical_values import freeze_json_mapping

        shared: dict[str, object] = {"weights": [0.4, 0.6]}

        frozen = freeze_json_mapping(
            {"left": shared, "right": shared},
            field_name="payload",
        )

        left = frozen["left"]
        right = frozen["right"]
        assert isinstance(left, Mapping)
        assert isinstance(right, Mapping)
        assert left == right
        assert left is not right
