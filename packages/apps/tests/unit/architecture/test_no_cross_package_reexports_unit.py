"""Enforce canonical import paths for cross-package types.

Types owned by ditto_kernel or ditto_platform must be imported from their
canonical location, not via ditto_data re-export shims.
"""

from pathlib import Path


def _forbidden(prefix: str, suffix: str = "") -> str:
    return f"{prefix}{suffix}"


FORBIDDEN_IMPORTS = (
    _forbidden("from ditto_data.models.publication_safety", " import"),
    _forbidden("from ditto_data.models.storage", " import WriteResult"),
    _forbidden("from ditto_data.models.storage", " import WriteStoreResult"),
    _forbidden("from ditto_data.models", " import OnDuplicate"),
    _forbidden("from ditto_data.models.common", " import OnDuplicate"),
    _forbidden("from ditto_data.errors", " import Derived"),
    _forbidden("from ditto_data.storage.base", " import ParquetStore"),
    _forbidden("from ditto_data.storage.base", " import MergeResult"),
    _forbidden("from ditto_data.storage.base", " import PartitionStrategy"),
    _forbidden("from ditto_data.storage.base", " import YearlyPartition"),
    _forbidden("from ditto_data.storage.base", " import DatasetReader"),
    _forbidden("from ditto_data.storage.base", " import DatasetWriter"),
    _forbidden("from ditto_data.storage.base.parquet_store", " import"),
    _forbidden("from ditto_data.storage.base.protocols", " import"),
    _forbidden("from ditto_data.storage.base.partition_strategy", " import"),
)


_THIS_FILE = Path(__file__).resolve()


def test_source_uses_canonical_cross_package_types() -> None:
    offenders: list[str] = []
    for path in Path("packages").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.resolve() == _THIS_FILE:
            continue
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in FORBIDDEN_IMPORTS):
            offenders.append(path.as_posix())
    assert offenders == [], "\n".join(offenders)
