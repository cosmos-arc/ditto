"""Enforce canonical import paths for cross-package types.

Types owned by ditto_kernel or ditto_platform must be imported from their
canonical location, not via ditto_data re-export shims.
"""

from pathlib import Path

FORBIDDEN_IMPORTS = (
    "from ditto_data.models.publication_safety import",
    "from ditto_data.models.storage import WriteResult",
    "from ditto_data.models.storage import WriteStoreResult",
    "from ditto_data.models import OnDuplicate",
    "from ditto_data.models.common import OnDuplicate",
    "from ditto_data.errors import Derived",
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
