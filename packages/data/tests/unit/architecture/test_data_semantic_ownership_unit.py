from pathlib import Path


def test_data_runtime_storage_has_no_publication_safety_store():
    runtime_root = Path("packages/data/src/ditto_data/storage/runtime")
    assert not (runtime_root / "publication_safety").exists()


def test_data_runtime_storage_has_no_publication_shadow_sqlite():
    runtime_root = Path("packages/data/src/ditto_data/storage/runtime")
    assert not (runtime_root / "publication_shadow_sqlite").exists()


def test_data_ingestion_has_no_derived_publication_service():
    path = Path(
        "packages/data/src/ditto_data/ingestion/publication_safety_record_service.py"
    )
    assert not path.exists()
