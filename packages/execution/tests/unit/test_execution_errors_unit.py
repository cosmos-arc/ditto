"""Execution error hierarchy unit tests."""

from ditto_execution.errors import (
    AuditError,
    ExecutionError,
    FillProcessingError,
    OrderStateError,
    OrderSubmitError,
    ReconciliationError,
)


def test_execution_error_hierarchy() -> None:
    """All execution domain errors inherit from ExecutionError."""
    assert issubclass(OrderSubmitError, ExecutionError)
    assert issubclass(OrderStateError, ExecutionError)
    assert issubclass(FillProcessingError, ExecutionError)
    assert issubclass(ReconciliationError, ExecutionError)
    assert issubclass(AuditError, ExecutionError)


def test_execution_error_is_ditto_error() -> None:
    """ExecutionError inherits from DittoError (kernel root)."""
    from ditto_kernel.exceptions import DittoError

    assert issubclass(ExecutionError, DittoError)


def test_order_submit_error_carries_details() -> None:
    """OrderSubmitError exposes order_id via details."""
    err = OrderSubmitError("submit failed", order_id="ORD-001")
    assert err.details["order_id"] == "ORD-001"


def test_order_state_error_carries_details() -> None:
    """OrderStateError exposes state info via details."""
    err = OrderStateError("invalid transition", state="FILLED", target="CANCELLED")
    assert err.details["state"] == "FILLED"
    assert err.details["target"] == "CANCELLED"


def test_fill_processing_error_carries_details() -> None:
    """FillProcessingError carries fill context."""
    err = FillProcessingError("fill error", fill_id="FILL-001")
    assert err.details["fill_id"] == "FILL-001"


def test_reconciliation_error_carries_details() -> None:
    """ReconciliationError carries reconciliation context."""
    err = ReconciliationError("mismatch", expected=100, actual=95)
    assert err.details["expected"] == 100
    assert err.details["actual"] == 95


def test_audit_error_carries_details() -> None:
    """AuditError carries audit context."""
    err = AuditError("audit failure", audit_id="AUD-001")
    assert err.details["audit_id"] == "AUD-001"
