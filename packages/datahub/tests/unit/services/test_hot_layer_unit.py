"""Unit tests for hot layer protocols and placeholder implementations."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_datahub.services.hot_layer import (
    HotLayerReader,
    HotLayerWriter,
    StateStore,
    UnavailableHotLayerReader,
    UnavailableHotLayerWriter,
    UnavailableStateStore,
)


class TestUnavailableHotLayerReader:
    """Tests for UnavailableHotLayerReader placeholder."""

    def test_is_available_returns_false(self) -> None:
        """UnavailableHotLayerReader.is_available() should return False."""
        reader = UnavailableHotLayerReader()
        assert reader.is_available() is False

    def test_read_latest_raises_not_implemented(self) -> None:
        """read_latest() should raise NotImplementedError."""
        reader = UnavailableHotLayerReader()
        with pytest.raises(
            NotImplementedError,
            match=r"Hot layer .*QuestDB.* not implemented",
        ):
            reader.read_latest(
                derived_id="factor.test",
                instrument_ids=None,
                as_of=None,
            )

    def test_satisfies_hot_layer_reader_protocol(self) -> None:
        """UnavailableHotLayerReader should satisfy the HotLayerReader protocol."""
        reader: HotLayerReader = UnavailableHotLayerReader()
        assert isinstance(reader, HotLayerReader)


class TestUnavailableHotLayerWriter:
    """Tests for UnavailableHotLayerWriter placeholder."""

    def test_write_frame_raises_not_implemented(self) -> None:
        """write_frame() should raise NotImplementedError."""
        writer = UnavailableHotLayerWriter()
        with pytest.raises(
            NotImplementedError,
            match=r"Hot layer writer .*QuestDB.* not implemented",
        ):
            writer.write_frame(
                derived_id="factor.test",
                version=1,
                frame=pl.DataFrame(),
            )

    def test_satisfies_hot_layer_writer_protocol(self) -> None:
        """UnavailableHotLayerWriter should satisfy the HotLayerWriter protocol."""
        writer: HotLayerWriter = UnavailableHotLayerWriter()
        assert isinstance(writer, HotLayerWriter)


class TestUnavailableStateStore:
    """Tests for UnavailableStateStore placeholder."""

    def test_get_raises_not_implemented(self) -> None:
        """get() should raise NotImplementedError."""
        store = UnavailableStateStore()
        with pytest.raises(
            NotImplementedError,
            match=r"State store .*Kvrocks.* not implemented",
        ):
            store.get("test-key")

    def test_set_raises_not_implemented(self) -> None:
        """set() should raise NotImplementedError."""
        store = UnavailableStateStore()
        with pytest.raises(
            NotImplementedError,
            match=r"State store .*Kvrocks.* not implemented",
        ):
            store.set("test-key", b"value")

    def test_set_with_ttl_raises_not_implemented(self) -> None:
        """set() with ttl_seconds should raise NotImplementedError."""
        store = UnavailableStateStore()
        with pytest.raises(
            NotImplementedError,
            match=r"State store .*Kvrocks.* not implemented",
        ):
            store.set("test-key", b"value", ttl_seconds=60)

    def test_satisfies_state_store_protocol(self) -> None:
        """UnavailableStateStore should satisfy the StateStore protocol."""
        store: StateStore = UnavailableStateStore()
        assert isinstance(store, StateStore)
