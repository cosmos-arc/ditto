def test_import_ditto_strategy() -> None:
    import ditto_strategy

    assert ditto_strategy.__name__ == "ditto_strategy"
    assert not hasattr(ditto_strategy, "__version__")
