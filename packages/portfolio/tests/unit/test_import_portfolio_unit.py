def test_import_ditto_portfolio() -> None:
    import ditto_portfolio

    assert ditto_portfolio.__name__ == "ditto_portfolio"
    assert not hasattr(ditto_portfolio, "__version__")
