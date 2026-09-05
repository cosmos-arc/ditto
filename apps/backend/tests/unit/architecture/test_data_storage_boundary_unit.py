"""Data storage must not import data model barrels."""

from pathlib import Path


def test_data_storage_does_not_import_data_model_barrel() -> None:
    offenders: list[str] = []
    for path in Path("packages/data/src/ditto_data/storage").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        imports_model_barrel = any(
            pattern in text
            for pattern in (
                "from ditto_data.models import",
                "import ditto_data.models",
            )
        )
        if imports_model_barrel:
            offenders.append(path.as_posix())
    assert offenders == [], "\n".join(offenders)
