def test_import_ditto_risk() -> None:
    import ditto_risk

    assert ditto_risk.__name__ == "ditto_risk"
    assert not hasattr(ditto_risk, "__version__")
