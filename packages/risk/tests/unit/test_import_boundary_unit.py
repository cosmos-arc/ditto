def test_risk_imports_without_execution() -> None:
    import ditto_risk

    assert ditto_risk.__version__ == "0.1.0"
