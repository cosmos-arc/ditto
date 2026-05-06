def test_import_ditto_backtest() -> None:
    import ditto_backtest

    assert ditto_backtest.__name__ == "ditto_backtest"
    assert not hasattr(ditto_backtest, "__version__")
