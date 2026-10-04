"""#444 删除守卫：shadow/certification 发布安全机器不得回流."""

from pathlib import Path

FEATURES_ROOT = Path("packages/features/src/ditto_features")


def test_features_has_no_publication_safety_modules():
    assert not (FEATURES_ROOT / "publication_safety.py").exists()
    assert not (FEATURES_ROOT / "publication_safety_records.py").exists()
    assert not (
        FEATURES_ROOT / "services" / "publication_safety_record_service.py"
    ).exists()
    assert not (FEATURES_ROOT / "services" / "derived_shadow_slot_service.py").exists()


def test_features_has_no_publication_safety_stores():
    runtime_root = FEATURES_ROOT / "storage" / "runtime"
    assert not (runtime_root / "publication_safety").exists()
    assert not (runtime_root / "publication_shadow_sqlite").exists()
