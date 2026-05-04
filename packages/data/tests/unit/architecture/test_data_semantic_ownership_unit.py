from pathlib import Path


def test_data_runtime_storage_has_no_publication_safety_store():
    runtime_root = Path("packages/data/src/ditto_data/storage/runtime")
    assert not (runtime_root / "publication_safety").exists()
