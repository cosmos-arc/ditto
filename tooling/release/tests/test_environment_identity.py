from pathlib import Path

from tooling.release.environment_identity import environment_identity


def test_environment_identity_binds_interpreter_source_version_and_platform(
    tmp_path: Path,
) -> None:
    (tmp_path / "deploy/docker").mkdir(parents=True)
    (tmp_path / "uv.lock").write_text("same dependencies")
    (tmp_path / ".python-version").write_text("cpython-3.13.14")
    dockerfile = tmp_path / "deploy/docker/Dockerfile"
    dockerfile.write_text("FROM python@sha256:first")
    original = environment_identity(tmp_path)
    assert original == environment_identity(tmp_path)
    assert original != environment_identity(tmp_path, platform="linux/arm64")
    dockerfile.write_text("FROM python@sha256:second")
    changed_source = environment_identity(tmp_path)
    assert original != changed_source
    (tmp_path / ".python-version").write_text("cpython-3.13.15")
    assert changed_source != environment_identity(tmp_path)
