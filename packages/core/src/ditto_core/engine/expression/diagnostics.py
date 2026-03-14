"""Structured diagnostics for the derived expression engine."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CompileDiagnostic",
    "ExpressionCompileError",
    "SourcePosition",
    "Span",
    "format_compile_error",
    "make_compile_error",
    "merge_spans",
]


@dataclass(frozen=True)
class SourcePosition:
    """One source position in 1-based line/column coordinates."""

    offset: int
    line: int
    column: int


@dataclass(frozen=True)
class Span:
    """Closed-open source span."""

    start: SourcePosition
    end: SourcePosition


def merge_spans(start: Span, end: Span) -> Span:
    """Return a span covering both inputs."""
    return Span(start=start.start, end=end.end)


@dataclass(frozen=True)
class CompileDiagnostic:
    """Stable compile-time diagnostic payload."""

    message: str
    error_code: str
    span: Span
    source_line: str
    suggestions: tuple[str, ...] = ()


class ExpressionCompileError(Exception):
    """Raised when expression compilation fails with a structured diagnostic."""

    def __init__(self, diagnostic: CompileDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(format_compile_error(diagnostic))


def make_compile_error(
    *,
    source: str,
    message: str,
    error_code: str,
    span: Span,
    suggestions: tuple[str, ...] = (),
) -> ExpressionCompileError:
    """Create a formatted compile error from the current source text."""
    diagnostic = CompileDiagnostic(
        message=message,
        error_code=error_code,
        span=span,
        source_line=_line_text(source, span.start.line),
        suggestions=suggestions,
    )
    return ExpressionCompileError(diagnostic)


def format_compile_error(diagnostic: CompileDiagnostic) -> str:
    """Format a compile diagnostic in a compiler-style layout."""
    category = _error_category(diagnostic.error_code)
    highlight_width = max(1, diagnostic.span.end.column - diagnostic.span.start.column)
    help_line = ""
    if diagnostic.suggestions:
        help_line = f"\n   = help: did you mean '{diagnostic.suggestions[0]}'?"
    location = (
        "  --> expression:"
        f"{diagnostic.span.start.line}:{diagnostic.span.start.column}\n"
    )
    return (
        f"{category}: {diagnostic.message} [{diagnostic.error_code}]\n"
        f"{location}"
        "   |\n"
        f"{diagnostic.span.start.line:3} | {diagnostic.source_line}\n"
        f"   | {' ' * (diagnostic.span.start.column - 1)}{'^' * highlight_width}\n"
        f"   | {diagnostic.message}"
        f"{help_line}"
    )


def _line_text(source: str, line_number: int) -> str:
    lines = source.splitlines()
    if not lines:
        return source
    if line_number <= 0 or line_number > len(lines):
        return ""
    return lines[line_number - 1]


def _error_category(error_code: str) -> str:
    if error_code.startswith("E001") or error_code.startswith("E002"):
        return "LexError"
    if error_code.startswith("E01"):
        return "SyntaxError"
    if error_code.startswith("E02"):
        return "SemanticError"
    if error_code.startswith("E03"):
        return "TypeError"
    if error_code.startswith("E04"):
        return "ComplexityError"
    return "CompileError"
