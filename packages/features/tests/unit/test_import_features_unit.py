def test_import_ditto_features() -> None:
    import ditto_features

    assert ditto_features.__name__ == "ditto_features"
    assert not hasattr(ditto_features, "__version__")
