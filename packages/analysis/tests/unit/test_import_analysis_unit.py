def test_import_ditto_analysis() -> None:
    import ditto_analysis

    assert ditto_analysis.__name__ == "ditto_analysis"
    assert not hasattr(ditto_analysis, "__version__")
