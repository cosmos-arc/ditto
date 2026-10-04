"""#444 删除守卫：级联失效与发布门面不得回流."""

from pathlib import Path

MATERIALIZATION_ROOT = Path(
    "packages/application/src/ditto_application/processes/materialization"
)


def test_materialization_has_no_cascade_or_publication_facade():
    for name in (
        "cascade_orchestrator.py",
        "publication_facade.py",
        "certification_rules.py",
        "publication_helpers.py",
    ):
        assert not (MATERIALIZATION_ROOT / name).exists(), name
