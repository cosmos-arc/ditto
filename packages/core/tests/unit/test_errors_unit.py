"""Tests for the unified derived exception hierarchy."""

from __future__ import annotations

from ditto_core.engine.errors import (
    DerivedDependencyError,
    DerivedError,
    DerivedMaterializationError,
    DerivedNotFoundError,
    DerivedNotImplementedError,
    DerivedValidationError,
    DerivedVersionError,
)

# ---------------------------------------------------------------------------
# DerivedError (base)
# ---------------------------------------------------------------------------


class TestDerivedError:
    """Tests for DerivedError base exception."""

    def test_inherits_from_exception(self) -> None:
        """DerivedError should be a subclass of Exception."""
        assert issubclass(DerivedError, Exception)

    def test_construction_with_derived_id(self) -> None:
        """DerivedError should store derived_id when provided."""
        exc = DerivedError("test message", derived_id="factor.alpha")
        assert exc.derived_id == "factor.alpha"
        assert str(exc) == "test message"

    def test_construction_without_derived_id(self) -> None:
        """DerivedError should default derived_id to None."""
        exc = DerivedError("test message")
        assert exc.derived_id is None
        assert str(exc) == "test message"

    def test_message_format(self) -> None:
        """DerivedError message should be passed through to Exception."""
        exc = DerivedError("something went wrong", derived_id="factor.beta")
        assert str(exc) == "something went wrong"


# ---------------------------------------------------------------------------
# DerivedNotFoundError
# ---------------------------------------------------------------------------


class TestDerivedNotFoundError:
    """Tests for DerivedNotFoundError."""

    def test_inherits_from_derived_error(self) -> None:
        """DerivedNotFoundError should be a subclass of DerivedError."""
        assert issubclass(DerivedNotFoundError, DerivedError)

    def test_construction_with_derived_id_only(self) -> None:
        """Should store derived_id with version=None."""
        exc = DerivedNotFoundError(derived_id="factor.alpha")
        assert exc.derived_id == "factor.alpha"
        assert exc.version is None
        assert "derived_id=factor.alpha" in str(exc)
        assert "version=" not in str(exc)

    def test_construction_with_version(self) -> None:
        """Should include version in the message."""
        exc = DerivedNotFoundError(derived_id="factor.alpha", version=3)
        assert exc.derived_id == "factor.alpha"
        assert exc.version == 3
        assert "derived_id=factor.alpha" in str(exc)
        assert "version=3" in str(exc)


# ---------------------------------------------------------------------------
# DerivedVersionError
# ---------------------------------------------------------------------------


class TestDerivedVersionError:
    """Tests for DerivedVersionError."""

    def test_inherits_from_derived_error(self) -> None:
        """DerivedVersionError should be a subclass of DerivedError."""
        assert issubclass(DerivedVersionError, DerivedError)

    def test_construction(self) -> None:
        """Should store derived_id and reason."""
        exc = DerivedVersionError(derived_id="factor.alpha", reason="no active version")
        assert exc.derived_id == "factor.alpha"
        assert exc.reason == "no active version"
        assert "factor.alpha" in str(exc)
        assert "no active version" in str(exc)


# ---------------------------------------------------------------------------
# DerivedMaterializationError
# ---------------------------------------------------------------------------


class TestDerivedMaterializationError:
    """Tests for DerivedMaterializationError."""

    def test_inherits_from_derived_error(self) -> None:
        """DerivedMaterializationError should be a subclass of DerivedError."""
        assert issubclass(DerivedMaterializationError, DerivedError)

    def test_construction(self) -> None:
        """Should store derived_id, version, and reason."""
        exc = DerivedMaterializationError(
            derived_id="factor.alpha", version=2, reason="compile failed"
        )
        assert exc.derived_id == "factor.alpha"
        assert exc.version == 2
        assert exc.reason == "compile failed"
        assert "factor.alpha" in str(exc)
        assert "version=2" in str(exc)
        assert "compile failed" in str(exc)


# ---------------------------------------------------------------------------
# DerivedDependencyError
# ---------------------------------------------------------------------------


class TestDerivedDependencyError:
    """Tests for DerivedDependencyError."""

    def test_inherits_from_derived_error(self) -> None:
        """DerivedDependencyError should be a subclass of DerivedError."""
        assert issubclass(DerivedDependencyError, DerivedError)

    def test_construction(self) -> None:
        """Should store derived_id, missing, and available."""
        exc = DerivedDependencyError(
            derived_id="factor.alpha",
            missing=["market.close"],
            available=["market.open", "market.high"],
        )
        assert exc.derived_id == "factor.alpha"
        assert exc.missing == ["market.close"]
        assert exc.available == ["market.open", "market.high"]
        assert "factor.alpha" in str(exc)
        assert "market.close" in str(exc)


# ---------------------------------------------------------------------------
# DerivedNotImplementedError
# ---------------------------------------------------------------------------


class TestDerivedNotImplementedError:
    """Tests for DerivedNotImplementedError."""

    def test_inherits_from_derived_error(self) -> None:
        """DerivedNotImplementedError should be a subclass of DerivedError."""
        assert issubclass(DerivedNotImplementedError, DerivedError)

    def test_construction_with_derived_id(self) -> None:
        """Should store feature and derived_id."""
        exc = DerivedNotImplementedError(
            feature="minute grain", derived_id="factor.alpha"
        )
        assert exc.feature == "minute grain"
        assert exc.derived_id == "factor.alpha"
        assert "minute grain" in str(exc)

    def test_construction_without_derived_id(self) -> None:
        """Should default derived_id to None."""
        exc = DerivedNotImplementedError(feature="composite keys")
        assert exc.feature == "composite keys"
        assert exc.derived_id is None
        assert "composite keys" in str(exc)


# ---------------------------------------------------------------------------
# DerivedValidationError
# ---------------------------------------------------------------------------


class TestDerivedValidationError:
    """Tests for DerivedValidationError."""

    def test_inherits_from_derived_error(self) -> None:
        """DerivedValidationError should be a subclass of DerivedError."""
        assert issubclass(DerivedValidationError, DerivedError)

    def test_construction_with_derived_id(self) -> None:
        """Should store field, value, reason, and derived_id."""
        exc = DerivedValidationError(
            field="grain", value="1m", reason="not supported", derived_id="factor.alpha"
        )
        assert exc.derived_id == "factor.alpha"
        assert exc.field == "grain"
        assert exc.value == "1m"
        assert exc.reason == "not supported"
        assert "grain" in str(exc)
        assert "1m" in str(exc)
        assert "not supported" in str(exc)

    def test_construction_without_derived_id(self) -> None:
        """Should default derived_id to None."""
        exc = DerivedValidationError(
            field="source_scope", value="archive", reason="unsupported"
        )
        assert exc.derived_id is None
        assert exc.field == "source_scope"
        assert exc.value == "archive"
        assert exc.reason == "unsupported"


# ---------------------------------------------------------------------------
# Catchability
# ---------------------------------------------------------------------------


class TestExceptionCatchability:
    """All subtypes should be catchable via DerivedError."""

    def test_catch_all_via_derived_error(self) -> None:
        """All subtypes should be catchable via DerivedError."""
        exceptions = [
            DerivedNotFoundError(derived_id="x"),
            DerivedVersionError(derived_id="x", reason="r"),
            DerivedMaterializationError(derived_id="x", version=1, reason="r"),
            DerivedDependencyError(derived_id="x", missing=[], available=[]),
            DerivedNotImplementedError(feature="f"),
            DerivedValidationError(field="f", value="v", reason="r"),
        ]
        for exc_class, exc_instance in zip(
            [
                DerivedNotFoundError,
                DerivedVersionError,
                DerivedMaterializationError,
                DerivedDependencyError,
                DerivedNotImplementedError,
                DerivedValidationError,
            ],
            exceptions,
            strict=True,
        ):
            caught = False
            try:
                raise exc_instance
            except DerivedError:
                caught = True
            assert caught, f"{exc_class.__name__} should be catchable via DerivedError"
