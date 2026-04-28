"""Tests for TushareExchangeTransformer."""

from ditto_data.sources.tushare.transformer import TushareExchangeTransformer


class TestTushareExchangeTransformer:
    """Tests for TushareExchangeTransformer."""

    def test_to_standard_sz_exchange(self) -> None:
        """Test SZ exchange converts to XSHE."""
        transformer = TushareExchangeTransformer()
        result = transformer.to_standard("000001.SZ")
        assert result == "000001.XSHE"

    def test_to_standard_sh_exchange(self) -> None:
        """Test SH exchange converts to XSHG."""
        transformer = TushareExchangeTransformer()
        result = transformer.to_standard("600000.SH")
        assert result == "600000.XSHG"

    def test_to_standard_bj_exchange(self) -> None:
        """Test BJ exchange converts to XBSE."""
        transformer = TushareExchangeTransformer()
        result = transformer.to_standard("430047.BJ")
        assert result == "430047.XBSE"

    def test_from_standard_xshe_exchange(self) -> None:
        """Test XSHE exchange converts to SZ."""
        transformer = TushareExchangeTransformer()
        result = transformer.from_standard("000001.XSHE")
        assert result == "000001.SZ"

    def test_from_standard_xshg_exchange(self) -> None:
        """Test XSHG exchange converts to SH."""
        transformer = TushareExchangeTransformer()
        result = transformer.from_standard("600000.XSHG")
        assert result == "600000.SH"

    def test_from_standard_xbse_exchange(self) -> None:
        """Test XBSE exchange converts to BJ."""
        transformer = TushareExchangeTransformer()
        result = transformer.from_standard("430047.XBSE")
        assert result == "430047.BJ"

    def test_to_standard_no_suffix(self) -> None:
        """Test ticker without suffix returns original value."""
        transformer = TushareExchangeTransformer()
        result = transformer.to_standard("000001")
        assert result == "000001"

    def test_from_standard_no_suffix(self) -> None:
        """Test standard ticker without suffix returns original value."""
        transformer = TushareExchangeTransformer()
        result = transformer.from_standard("000001")
        assert result == "000001"

    def test_to_standard_unknown_exchange(self) -> None:
        """Test unknown exchange returns original value."""
        transformer = TushareExchangeTransformer()
        result = transformer.to_standard("000001.UNKNOWN")
        assert result == "000001.UNKNOWN"

    def test_from_standard_unknown_exchange(self) -> None:
        """Test unknown standard exchange returns original value."""
        transformer = TushareExchangeTransformer()
        result = transformer.from_standard("000001.UNKNOWN")
        assert result == "000001.UNKNOWN"

    def test_bidirectional_consistency_sz(self) -> None:
        """Test bidirectional conversion consistency for SZ."""
        transformer = TushareExchangeTransformer()
        original = "000001.SZ"
        standard = transformer.to_standard(original)
        back = transformer.from_standard(standard)
        assert back == original

    def test_bidirectional_consistency_sh(self) -> None:
        """Test bidirectional conversion consistency for SH."""
        transformer = TushareExchangeTransformer()
        original = "600000.SH"
        standard = transformer.to_standard(original)
        back = transformer.from_standard(standard)
        assert back == original

    def test_bidirectional_consistency_bj(self) -> None:
        """Test bidirectional conversion consistency for BJ."""
        transformer = TushareExchangeTransformer()
        original = "430047.BJ"
        standard = transformer.to_standard(original)
        back = transformer.from_standard(standard)
        assert back == original

    def test_bidirectional_consistency_no_suffix(self) -> None:
        """Test bidirectional conversion consistency for no suffix."""
        transformer = TushareExchangeTransformer()
        original = "000001"
        standard = transformer.to_standard(original)
        back = transformer.from_standard(standard)
        assert back == original

    def test_multiple_conversions(self) -> None:
        """Test multiple conversions in sequence."""
        transformer = TushareExchangeTransformer()

        tickers = [
            ("000001.SZ", "000001.XSHE"),
            ("600000.SH", "600000.XSHG"),
            ("430047.BJ", "430047.XBSE"),
            ("399001.SZ", "399001.XSHE"),
            ("000016.SH", "000016.XSHG"),
        ]

        for source, expected_standard in tickers:
            assert transformer.to_standard(source) == expected_standard
            assert transformer.from_standard(expected_standard) == source

    def test_implements_exchange_transformer_protocol(self) -> None:
        """验证 TushareExchangeTransformer 实现 ExchangeTransformer 协议."""
        from ditto_data.sources.exchange_transformers import ExchangeTransformer

        transformer = TushareExchangeTransformer()
        # 验证实例满足协议（structural typing）
        assert isinstance(transformer, ExchangeTransformer)
