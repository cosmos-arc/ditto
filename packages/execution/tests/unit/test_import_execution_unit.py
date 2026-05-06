def test_import_ditto_execution() -> None:
    import ditto_execution

    assert ditto_execution.__name__ == "ditto_execution"
    assert not hasattr(ditto_execution, "__version__")
