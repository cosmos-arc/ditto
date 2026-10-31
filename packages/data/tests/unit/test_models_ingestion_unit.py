"""Tests for ingestion models in ditto_data.models.ingestion."""

from __future__ import annotations

import pytest
from ditto_data.models.ingestion import (
    INGESTION_ERROR_CODE_KINDS,
    BackfillResult,
    IngestionFailureKind,
    IngestionResult,
    ResultCounts,
    RetryResult,
    classify_ingestion_failure,
    is_retryable_ingestion_failure,
)
from ditto_kernel.instrument import InstrumentIngestParams

# ---------------------------------------------------------------------------
# InstrumentIngestParams
# ---------------------------------------------------------------------------


class TestInstrumentIngestParams:
    def test_default_values(self) -> None:
        params = InstrumentIngestParams(start_date="2024-01-01", end_date="2024-01-31")
        assert params.instrument_id is None
        assert params.standard_ticker is None
        assert params.ticker is None
        assert params.start_date == "2024-01-01"
        assert params.end_date == "2024-01-31"

    def test_instrument_id_priority(self) -> None:
        params = InstrumentIngestParams(instrument_id=12345)
        assert params.instrument_id == 12345

    def test_frozen(self) -> None:
        params = InstrumentIngestParams(start_date="2024-01-01")
        with pytest.raises(AttributeError):
            params.start_date = "2024-02-01"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IngestionResult
# ---------------------------------------------------------------------------


class TestIngestionResult:
    def test_success(self) -> None:
        result = IngestionResult(
            dataset="ETF_DAILY",
            trade_date="2024-01-15",
            status="success",
            row_count=100,
            checksum="abc123",
        )
        assert result.dataset == "ETF_DAILY"
        assert result.status == "success"
        assert result.row_count == 100

    def test_failed(self) -> None:
        result = IngestionResult(
            dataset="ETF_DAILY",
            trade_date="2024-01-15",
            status="failed",
            message="timeout",
            error="ConnectionError",
        )
        assert result.status == "failed"
        assert result.error == "ConnectionError"

    def test_skipped(self) -> None:
        result = IngestionResult(
            dataset="ETF_DAILY",
            trade_date="2024-01-15",
            status="skipped",
        )
        assert result.status == "skipped"

    def test_frozen(self) -> None:
        result = IngestionResult(
            dataset="ETF_DAILY",
            trade_date="2024-01-15",
            status="success",
        )
        with pytest.raises(AttributeError):
            result.status = "failed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ResultCounts
# ---------------------------------------------------------------------------


class TestResultCounts:
    def test_basic(self) -> None:
        counts = ResultCounts(success=10, failed=2, skipped=1)
        assert counts.success == 10
        assert counts.failed == 2
        assert counts.skipped == 1

    def test_frozen(self) -> None:
        counts = ResultCounts(success=0, failed=0, skipped=0)
        with pytest.raises(AttributeError):
            counts.success = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BackfillResult
# ---------------------------------------------------------------------------


class TestBackfillResult:
    def test_basic(self) -> None:
        r1 = IngestionResult(
            dataset="ETF_DAILY",
            trade_date="2024-01-01",
            status="success",
        )
        r2 = IngestionResult(
            dataset="ETF_DAILY",
            trade_date="2024-01-02",
            status="success",
        )
        result = BackfillResult(
            dataset="ETF_DAILY",
            total_dates=2,
            success_count=2,
            skipped_count=0,
            failed_count=0,
            results=(r1, r2),
        )
        assert result.dataset == "ETF_DAILY"
        assert result.total_dates == 2
        assert len(result.results) == 2

    def test_frozen(self) -> None:
        result = BackfillResult(
            dataset="ETF_DAILY",
            total_dates=0,
            success_count=0,
            skipped_count=0,
            failed_count=0,
            results=(),
        )
        with pytest.raises(AttributeError):
            result.total_dates = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RetryResult
# ---------------------------------------------------------------------------


class TestRetryResult:
    def test_basic(self) -> None:
        r1 = IngestionResult(
            dataset="ETF_DAILY",
            trade_date="2024-01-01",
            status="success",
        )
        result = RetryResult(
            dataset="ETF_DAILY",
            total_failed=3,
            retried_count=3,
            success_count=2,
            still_failed_count=1,
            results=(r1,),
        )
        assert result.total_failed == 3
        assert result.success_count == 2
        assert result.still_failed_count == 1

    def test_frozen(self) -> None:
        result = RetryResult(
            dataset="ETF_DAILY",
            total_failed=0,
            retried_count=0,
            success_count=0,
            still_failed_count=0,
            results=(),
        )
        with pytest.raises(AttributeError):
            result.total_failed = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IngestionFailureKind（#623 失败分类）
# ---------------------------------------------------------------------------


class TestIngestionFailureKind:
    TRANSIENT_CODES = (
        "RATE_LIMIT",
        "NETWORK_ERROR",
        "FETCH_ERROR",
        "EMPTY_DATA_UNEXPECTED",
    )
    PERMANENT_CODES = (
        "UNKNOWN_ERROR",
        "WRITE_ERROR",
        "DQ_BLOCKED",
        "SOURCE_AUTH_ERROR",
        "PARTITION_INTENT_FAILED",
        "PIT_SNAPSHOT_MISSING",
        "SNAPSHOT_CANONICAL_DRIFT",
        "CATALOG_WRITE_FAILED",
        "SUCCESS_LOG_WRITE_FAILED",
        "PIT_KNOWLEDGE_DATE_AFTER_CUTOFF",
        "INGESTION_QUALITY_CHECK_REQUIRED",
        "R2_EVIDENCE_COMMIT_FAILED",
    )

    def test_transient_codes_retryable(self) -> None:
        """瞬态失败（限流/网络/一般取数/供应商晚发）进入自动重试。"""
        for code in self.TRANSIENT_CODES:
            assert classify_ingestion_failure(code) is IngestionFailureKind.TRANSIENT
            assert is_retryable_ingestion_failure(code) is True

    def test_permanent_codes_not_retryable(self) -> None:
        """永久失败重试无意义：排除出自动重试。"""
        for code in self.PERMANENT_CODES:
            assert classify_ingestion_failure(code) is IngestionFailureKind.PERMANENT
            assert is_retryable_ingestion_failure(code) is False

    def test_source_missing_not_retryable(self) -> None:
        """源缺失=覆盖缺口，不按日盲目回补（#623 低频源条款）。"""
        assert (
            classify_ingestion_failure("EMPTY_DATA")
            is IngestionFailureKind.SOURCE_MISSING
        )
        assert is_retryable_ingestion_failure("EMPTY_DATA") is False

    def test_unsupported_is_capability_gap(self) -> None:
        """源不支持是能力声明而非故障。"""
        assert (
            classify_ingestion_failure("SOURCE_UNSUPPORTED")
            is IngestionFailureKind.UNSUPPORTED
        )
        assert is_retryable_ingestion_failure("SOURCE_UNSUPPORTED") is False

    def test_unknown_code_fails_closed_to_permanent(self) -> None:
        """不可分类的失败 fail-closed：不自动重试，由人工裁决（#608）。"""
        assert (
            classify_ingestion_failure("SOME_NEW_CODE")
            is IngestionFailureKind.PERMANENT
        )
        assert classify_ingestion_failure(None) is IngestionFailureKind.PERMANENT

    def test_vocabulary_is_closed(self) -> None:
        """词汇表四类全覆盖：每个码都映射到唯一已知分类。"""
        kinds = set(INGESTION_ERROR_CODE_KINDS.values())
        assert kinds == set(IngestionFailureKind)
