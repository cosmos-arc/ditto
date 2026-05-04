def test_risk_imports_without_execution() -> None:
    import ditto_risk

    assert ditto_risk.__name__ == "ditto_risk"
