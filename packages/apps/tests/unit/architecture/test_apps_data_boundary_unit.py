"""Apps 层禁止直接导入 ditto_data.models（非 registry 代码）."""

from pathlib import Path


def test_apps_non_registry_code_does_not_import_data_models() -> None:
    """非 registry 代码不得直接导入 ditto_data.models.

    Dataset 等数据模型应通过 ditto_application.config 间接引用，
    避免 apps 层与 data.models 直接耦合。
    """
    offenders: list[str] = []
    for path in Path("packages/apps/src/ditto_apps").rglob("*.py"):
        rel = path.as_posix()
        if "/registry/" in rel:
            continue
        source = path.read_text(encoding="utf-8")
        if "from ditto_data.models" in source or "import ditto_data.models" in source:
            offenders.append(rel)
    assert offenders == [], "\n".join(offenders)
