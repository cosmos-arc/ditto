"""Apps 层禁止直接导入 data barrels（非 registry 代码）."""

from pathlib import Path

FORBIDDEN_NON_REGISTRY_IMPORTS = (
    "from ditto_data.models",
    "import ditto_data.models",
    "from ditto_data.services",
    "import ditto_data.services",
    "from ditto_data.errors",
    "import ditto_data.errors",
    "from ditto_data.quality",
    "import ditto_data.quality",
    "from ditto_data.config",
    "import ditto_data.config",
)


def test_apps_non_registry_code_does_not_import_forbidden_data_barrels() -> None:
    """非 registry 代码不得直接导入 forbidden data barrels."""
    offenders: list[str] = []
    for path in Path("apps/backend/src/ditto_apps").rglob("*.py"):
        rel = path.as_posix()
        if "/registry/" in rel or rel.endswith(
            ("/jobs/context.py", "/jobs/tasks/monitoring.py")
        ):
            continue
        source = path.read_text(encoding="utf-8")
        if any(pattern in source for pattern in FORBIDDEN_NON_REGISTRY_IMPORTS):
            offenders.append(rel)
    assert offenders == [], "\n".join(offenders)
