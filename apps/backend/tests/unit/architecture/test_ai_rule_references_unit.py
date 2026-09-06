from pathlib import Path


def test_importlinter_has_no_unmatched_bare_barrel_ignore() -> None:
    text = Path(".importlinter").read_text(encoding="utf-8")
    # The bare barrel ignore (no trailing .**) is stale —
    # no code imports ditto_data.models directly.
    assert "ditto_data.storage.** -> ditto_data.models\n" not in text


def test_importlinter_apps_service_isolation_fails_on_stale_ignores() -> None:
    text = Path(".importlinter").read_text(encoding="utf-8")

    assert "ditto_apps.jobs.context -> ditto_data.quality\n" not in text
    assert "ditto_apps.jobs.context -> ditto_data.quality.protocols\n" not in text
    assert "unmatched_ignore_imports_alerting = error" in text
