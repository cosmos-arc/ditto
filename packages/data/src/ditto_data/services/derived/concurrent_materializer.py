"""Concurrent materialization orchestrator (MAT-M-7)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

__all__ = ["ConcurrentMaterializer", "MaterializationTaskResult"]


@dataclass(frozen=True)
class MaterializationTaskResult:
    """Result of a single materialization task."""

    derived_id: str
    success: bool
    error: str | None


class ConcurrentMaterializer:
    """
    Thin orchestration layer for concurrent materialization.

    Delegates the actual materialization work to a caller-provided callback,
    executing each derived_id in a thread pool.  This keeps the materializer
    decoupled from any specific materialization logic.

    Args:
        max_workers: Maximum number of concurrent threads. Defaults to 4.

    """

    def __init__(self, *, max_workers: int = 4) -> None:
        self._max_workers = max_workers

    def materialize_batch(
        self,
        derived_ids: Sequence[str],
        materialize_fn: Callable[[str], None],
    ) -> list[MaterializationTaskResult]:
        """
        Execute *materialize_fn* for each *derived_id* concurrently.

        Args:
            derived_ids: Identifiers of derived artifacts to materialize.
            materialize_fn: Callable that materializes a single derived artifact.
                Receives the derived_id as its only argument.

        Returns:
            A result for every derived_id, in the same order as *derived_ids*.

        """
        results: dict[str, MaterializationTaskResult] = {}

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_id = {
                executor.submit(materialize_fn, did): did for did in derived_ids
            }
            for future in as_completed(future_to_id):
                derived_id = future_to_id[future]
                try:
                    future.result()
                    results[derived_id] = MaterializationTaskResult(
                        derived_id=derived_id,
                        success=True,
                        error=None,
                    )
                except Exception as exc:
                    results[derived_id] = MaterializationTaskResult(
                        derived_id=derived_id,
                        success=False,
                        error=str(exc),
                    )

        # Return results in the original order
        return [results[did] for did in derived_ids]
