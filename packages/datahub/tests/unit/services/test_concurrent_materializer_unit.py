"""Tests for ConcurrentMaterializer (MAT-M-7)."""

from __future__ import annotations

import pytest


class TestMaterializationTaskResult:
    """Tests for MaterializationTaskResult dataclass."""

    def test_is_frozen(self) -> None:
        from ditto_datahub.services.derived.concurrent_materializer import (
            MaterializationTaskResult,
        )

        result = MaterializationTaskResult(
            derived_id="factor.test",
            success=True,
            error=None,
        )

        with pytest.raises(AttributeError):
            result.derived_id = "other"  # type: ignore[misc]

    def test_success_result(self) -> None:
        from ditto_datahub.services.derived.concurrent_materializer import (
            MaterializationTaskResult,
        )

        result = MaterializationTaskResult(
            derived_id="factor.test",
            success=True,
            error=None,
        )

        assert result.derived_id == "factor.test"
        assert result.success is True
        assert result.error is None

    def test_failure_result(self) -> None:
        from ditto_datahub.services.derived.concurrent_materializer import (
            MaterializationTaskResult,
        )

        result = MaterializationTaskResult(
            derived_id="factor.test",
            success=False,
            error="disk full",
        )

        assert result.success is False
        assert result.error == "disk full"


class TestConcurrentMaterializer:
    """Tests for ConcurrentMaterializer."""

    def test_batch_materializes_all_specs(self) -> None:
        """ConcurrentMaterializer should process all specs and return success."""
        from ditto_datahub.services.derived.concurrent_materializer import (
            ConcurrentMaterializer,
        )

        call_log: list[str] = []

        def materialize_fn(derived_id: str) -> None:
            call_log.append(derived_id)

        materializer = ConcurrentMaterializer(max_workers=2)
        results = materializer.materialize_batch(
            derived_ids=["factor.a", "factor.b", "factor.c"],
            materialize_fn=materialize_fn,
        )

        assert len(results) == 3
        assert all(r.success for r in results)
        assert all(r.error is None for r in results)

        # All three IDs should have been called
        assert set(call_log) == {"factor.a", "factor.b", "factor.c"}

    def test_batch_collects_exceptions(self) -> None:
        """ConcurrentMaterializer should return error info for failed specs."""
        from ditto_datahub.services.derived.concurrent_materializer import (
            ConcurrentMaterializer,
        )

        def materialize_fn(derived_id: str) -> None:
            if derived_id == "factor.bad":
                raise RuntimeError("compilation failed")

        materializer = ConcurrentMaterializer(max_workers=2)
        results = materializer.materialize_batch(
            derived_ids=["factor.good", "factor.bad", "factor.also_good"],
            materialize_fn=materialize_fn,
        )

        assert len(results) == 3

        # Find individual results by derived_id
        by_id = {r.derived_id: r for r in results}

        assert by_id["factor.good"].success is True
        assert by_id["factor.bad"].success is False
        assert "compilation failed" in by_id["factor.bad"].error
        assert by_id["factor.also_good"].success is True

    def test_batch_runs_concurrently(self) -> None:
        """Multiple specs should run in parallel, not sequentially."""
        # Each call blocks for 0.2s.  If sequential, 3 calls = 0.6s+.
        # With 3 workers in parallel, should finish in ~0.2s.
        import time

        from ditto_datahub.services.derived.concurrent_materializer import (
            ConcurrentMaterializer,
        )

        def slow_fn(derived_id: str) -> None:
            time.sleep(0.2)

        materializer = ConcurrentMaterializer(max_workers=3)
        start = time.monotonic()
        materializer.materialize_batch(
            derived_ids=["a", "b", "c"],
            materialize_fn=slow_fn,
        )
        elapsed = time.monotonic() - start

        # Sequential would take >= 0.6s; parallel should be < 0.5s
        assert elapsed < 0.5, f"Expected concurrent execution, took {elapsed:.2f}s"

    def test_batch_empty_ids(self) -> None:
        """Empty derived_ids should return empty results."""
        from ditto_datahub.services.derived.concurrent_materializer import (
            ConcurrentMaterializer,
        )

        materializer = ConcurrentMaterializer(max_workers=2)
        results = materializer.materialize_batch(
            derived_ids=[],
            materialize_fn=lambda _: None,
        )

        assert results == []

    def test_single_worker(self) -> None:
        """max_workers=1 should still produce correct results."""
        from ditto_datahub.services.derived.concurrent_materializer import (
            ConcurrentMaterializer,
        )

        call_log: list[str] = []

        def materialize_fn(derived_id: str) -> None:
            call_log.append(derived_id)

        materializer = ConcurrentMaterializer(max_workers=1)
        results = materializer.materialize_batch(
            derived_ids=["factor.x", "factor.y"],
            materialize_fn=materialize_fn,
        )

        assert len(results) == 2
        assert all(r.success for r in results)
        assert len(call_log) == 2
