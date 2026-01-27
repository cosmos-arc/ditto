"""Unit tests for BaseStore abstract base class."""

from __future__ import annotations

import pytest
from ditto_datahub.stores.base import BaseStore


def test_base_store_cannot_be_instantiated() -> None:
    """BaseStore 是抽象类，不能直接实例化."""
    with pytest.raises(TypeError):
        BaseStore()  # type: ignore[arg-type]


def test_base_store_requires_abstract_methods() -> None:
    """子类必须实现抽象方法."""

    class IncompleteStore(BaseStore):  # type: ignore[misc]
        pass

    with pytest.raises(TypeError):
        IncompleteStore()  # type: ignore[misc]
