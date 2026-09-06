"""Comments and source length cannot substitute for executable boundaries."""

from pathlib import Path

import pytest
from scripts.architecture import check_architecture_smells as checker


def test_comments_and_size_do_not_invent_dependency_violations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "packages/platform/src/ditto_platform/helpers/explanation.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# infra/ is a historical term\n"
        "# from ditto_analysis import old_api\n"
        '# logger.info(f"example")\n' + "# explanation\n" * 1000
    )
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "iter_source_files", lambda: [source])
    assert checker._check_per_file() == []
    assert checker.check_production_no_analysis(
        "from ditto_analysis import actual_api",
        "packages/execution/src/ditto_execution/example.py",
    )
