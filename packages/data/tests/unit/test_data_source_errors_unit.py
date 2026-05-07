"""Tests for DataSource error hierarchy in ditto_data.errors."""

from __future__ import annotations

import pytest
from ditto_data.errors import (
    AuthError,
    DataSourceError,
    DataValidationError,
    NetworkError,
    PersistenceError,
    SourceFetchError,
    WriteError,
    convert_httpx_to_network_error,
)
from ditto_kernel.exceptions import DataError

# ---------------------------------------------------------------------------
# DataSourceError
# ---------------------------------------------------------------------------


class TestDataSourceError:
    def test_inherits_data_hub_error(self) -> None:
        err = DataSourceError(message="test", source="tushare")
        assert isinstance(err, DataError)

    def test_stores_source(self) -> None:
        err = DataSourceError(message="test", source="tushare")
        assert err.source == "tushare"

    def test_source_in_details(self) -> None:
        err = DataSourceError(message="test", source="tushare")
        assert err.details["source"] == "tushare"

    def test_extra_details_merged(self) -> None:
        err = DataSourceError(
            message="test",
            source="tushare",
            details={"key": "value"},
        )
        assert err.details["source"] == "tushare"
        assert err.details["key"] == "value"


# ---------------------------------------------------------------------------
# NetworkError
# ---------------------------------------------------------------------------


class TestNetworkError:
    def test_inherits_data_source_error(self) -> None:
        err = NetworkError(message="timeout", source="tushare")
        assert isinstance(err, DataSourceError)

    def test_timeout_flag_default(self) -> None:
        err = NetworkError(message="test", source="tushare")
        assert err.timeout is False

    def test_timeout_flag_true(self) -> None:
        err = NetworkError(message="test", source="tushare", timeout=True)
        assert err.timeout is True

    def test_cause_stored(self) -> None:
        original = ConnectionError("refused")
        err = NetworkError(message="test", source="tushare", cause=original)
        assert err.__cause__ is original

    def test_timeout_in_details(self) -> None:
        err = NetworkError(message="test", source="tushare", timeout=True)
        assert err.details["timeout"] is True

    def test_from_httpx_timeout(self) -> None:
        import httpx

        original = httpx.TimeoutException("timed out")
        err = NetworkError.from_httpx(original, source="tushare")
        assert isinstance(err, NetworkError)
        assert err.timeout is True
        assert err.source == "tushare"
        assert err.__cause__ is original

    def test_from_httpx_network(self) -> None:
        import httpx

        original = httpx.ConnectError("connection refused")
        err = NetworkError.from_httpx(original, source="tushare")
        assert isinstance(err, NetworkError)
        assert err.timeout is False

    def test_from_httpx_with_context(self) -> None:
        import httpx

        original = httpx.TimeoutException("timed out")
        err = NetworkError.from_httpx(
            original,
            source="tushare",
            context="fetch ETF_DAILY",
        )
        assert "fetch ETF_DAILY" in str(err)


# ---------------------------------------------------------------------------
# AuthError
# ---------------------------------------------------------------------------


class TestAuthError:
    def test_inherits_data_source_error(self) -> None:
        err = AuthError(message="bad key", source="tushare")
        assert isinstance(err, DataSourceError)

    def test_auth_type_default(self) -> None:
        err = AuthError(message="bad key", source="tushare")
        assert err.auth_type == "api_key"

    def test_auth_type_custom(self) -> None:
        err = AuthError(message="bad token", source="fred", auth_type="oauth")
        assert err.auth_type == "oauth"

    def test_auth_type_in_details(self) -> None:
        err = AuthError(message="bad key", source="tushare")
        assert err.details["auth_type"] == "api_key"


# ---------------------------------------------------------------------------
# DataValidationError
# ---------------------------------------------------------------------------


class TestDataValidationError:
    def test_inherits_data_source_error(self) -> None:
        err = DataValidationError(message="bad data", source="tushare")
        assert isinstance(err, DataSourceError)

    def test_dataset_stored(self) -> None:
        err = DataValidationError(
            message="bad data",
            source="tushare",
            dataset="ETF_DAILY",
        )
        assert err.dataset == "ETF_DAILY"

    def test_field_stored(self) -> None:
        err = DataValidationError(
            message="bad data",
            source="tushare",
            field="trade_date",
        )
        assert err.field == "trade_date"

    def test_dataset_and_field_in_details(self) -> None:
        err = DataValidationError(
            message="bad data",
            source="tushare",
            dataset="ETF_DAILY",
            field="trade_date",
        )
        assert err.details["dataset"] == "ETF_DAILY"
        assert err.details["field"] == "trade_date"


# ---------------------------------------------------------------------------
# SourceFetchError
# ---------------------------------------------------------------------------


class TestSourceFetchError:
    def test_inherits_data_source_error(self) -> None:
        err = SourceFetchError(message="fetch failed", source="tushare")
        assert isinstance(err, DataSourceError)

    def test_cause_stored(self) -> None:
        original = ValueError("bad response")
        err = SourceFetchError(
            message="fetch failed",
            source="tushare",
            cause=original,
        )
        assert err.__cause__ is original


# ---------------------------------------------------------------------------
# PersistenceError
# ---------------------------------------------------------------------------


class TestPersistenceError:
    def test_inherits_data_hub_error(self) -> None:
        err = PersistenceError(message="write failed")
        assert isinstance(err, DataError)

    def test_dataset_stored(self) -> None:
        err = PersistenceError(message="write failed", dataset="ETF_DAILY")
        assert err.dataset == "ETF_DAILY"

    def test_dataset_in_details(self) -> None:
        err = PersistenceError(message="write failed", dataset="ETF_DAILY")
        assert err.details["dataset"] == "ETF_DAILY"


# ---------------------------------------------------------------------------
# WriteError
# ---------------------------------------------------------------------------


class TestWriteError:
    def test_inherits_persistence_error(self) -> None:
        err = WriteError(message="disk full")
        assert isinstance(err, PersistenceError)

    def test_cause_stored(self) -> None:
        original = OSError("No space left")
        err = WriteError(message="disk full", cause=original)
        assert err.__cause__ is original

    def test_from_exception(self) -> None:
        original = OSError("No space left")
        err = WriteError.from_exception(
            original,
            dataset="ETF_DAILY",
            context="writing parquet",
        )
        assert isinstance(err, WriteError)
        assert err.dataset == "ETF_DAILY"
        assert err.__cause__ is original
        assert "writing parquet" in str(err)


# ---------------------------------------------------------------------------
# convert_httpx_to_network_error
# ---------------------------------------------------------------------------


class TestConvertHttpxToNetworkError:
    def test_converts_timeout(self) -> None:
        import httpx

        original = httpx.TimeoutException("timed out")
        err = convert_httpx_to_network_error(original, source="tushare")
        assert isinstance(err, NetworkError)
        assert err.timeout is True

    def test_converts_network_error(self) -> None:
        import httpx

        original = httpx.ConnectError("refused")
        err = convert_httpx_to_network_error(original, source="tushare")
        assert isinstance(err, NetworkError)
        assert err.timeout is False

    def test_rejects_non_httpx(self) -> None:
        with pytest.raises(ValueError, match="Expected httpx"):
            convert_httpx_to_network_error(
                RuntimeError("not httpx"),
                source="tushare",
            )

    def test_passes_context(self) -> None:
        import httpx

        original = httpx.TimeoutException("timed out")
        err = convert_httpx_to_network_error(
            original,
            source="tushare",
            context="fetch ETF_DAILY",
        )
        assert "fetch ETF_DAILY" in str(err)
