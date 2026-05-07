"""Lexer for the derived expression language."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_features.expression.diagnostics import (
    SourcePosition,
    Span,
    make_compile_error,
)

__all__ = ["Token", "tokenize"]

_DOUBLE_CHAR_OPERATORS = frozenset({"<=", ">=", "==", "!="})
_SINGLE_CHAR_OPERATORS = frozenset(
    {"(", ")", "+", "-", "*", "/", ",", "<", ">", ".", "@"}
)
_KEYWORDS = frozenset({"and", "or", "not"})
_ESCAPES = {
    '"': '"',
    "'": "'",
    "\\": "\\",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


@dataclass(frozen=True)
class Token:
    """Single lexical token."""

    kind: str
    value: str
    span: Span


def tokenize(source: str) -> tuple[Token, ...]:
    """Convert source text into a token sequence."""
    tokens: list[Token] = []
    scanner = _Scanner(source)
    while not scanner.is_done:
        token = scanner.next_token()
        if token is not None:
            tokens.append(token)
    eof_position = scanner.position
    tokens.append(
        Token(
            kind="EOF",
            value="",
            span=Span(start=eof_position, end=eof_position),
        )
    )
    return tuple(tokens)


class _Scanner:
    def __init__(self, source: str) -> None:
        self._source = source
        self._index = 0
        self._line = 1
        self._column = 1

    @property
    def is_done(self) -> bool:
        return self._index >= len(self._source)

    @property
    def position(self) -> SourcePosition:
        return SourcePosition(
            offset=self._index,
            line=self._line,
            column=self._column,
        )

    def next_token(self) -> Token | None:
        current = self._peek()
        if current is None:
            return None
        if current.isspace():
            self._consume_whitespace()
            return None
        if current in {'"', "'"}:
            return self._scan_string()
        if current.isdigit():
            return self._scan_number()
        if current.isalpha() or current == "_":
            return self._scan_identifier_or_keyword()
        return self._scan_operator()

    def _scan_number(self) -> Token:
        start = self.position
        digits: list[str] = []
        while (current := self._peek()) is not None and current.isdigit():
            digits.append(self._advance())
        next_char = self._peek(1)
        if self._peek() == "." and next_char is not None and next_char.isdigit():
            digits.append(self._advance())
            while (current := self._peek()) is not None and current.isdigit():
                digits.append(self._advance())
        return Token(
            kind="NUMBER",
            value="".join(digits),
            span=Span(start=start, end=self.position),
        )

    def _scan_identifier_or_keyword(self) -> Token:
        start = self.position
        characters: list[str] = []
        while (current := self._peek()) is not None:
            if not (current.isalnum() or current == "_"):
                break
            characters.append(self._advance())
        value = "".join(characters)
        kind = "KEYWORD" if value in _KEYWORDS else "IDENT"
        return Token(
            kind=kind,
            value=value,
            span=Span(start=start, end=self.position),
        )

    def _scan_string(self) -> Token:
        quote = self._advance()
        start = SourcePosition(
            offset=self._index - 1,
            line=self._line,
            column=self._column - 1,
        )
        characters: list[str] = []
        while True:
            current = self._peek()
            if current is None:
                raise make_compile_error(
                    source=self._source,
                    message="unterminated string literal",
                    error_code="E002_UNTERMINATED_STRING",
                    span=Span(start=start, end=self.position),
                )
            if current == quote:
                self._advance()
                return Token(
                    kind="STRING",
                    value="".join(characters),
                    span=Span(start=start, end=self.position),
                )
            if current == "\\":
                self._advance()
                escaped = self._peek()
                if escaped is None:
                    raise make_compile_error(
                        source=self._source,
                        message="unterminated string literal",
                        error_code="E002_UNTERMINATED_STRING",
                        span=Span(start=start, end=self.position),
                    )
                translated = _ESCAPES.get(escaped, escaped)
                characters.append(translated)
                self._advance()
                continue
            characters.append(self._advance())

    def _scan_operator(self) -> Token:
        start = self.position
        current = self._peek()
        if current is None:
            raise make_compile_error(
                source=self._source,
                message="unexpected end of input",
                error_code="E001_UNEXPECTED_TOKEN",
                span=Span(start=start, end=start),
            )
        pair = current + (self._peek(1) or "")
        if pair in _DOUBLE_CHAR_OPERATORS:
            self._advance()
            self._advance()
            return Token(
                kind="OP",
                value=pair,
                span=Span(start=start, end=self.position),
            )
        if current in _SINGLE_CHAR_OPERATORS:
            value = self._advance()
            return Token(
                kind="OP",
                value=value,
                span=Span(start=start, end=self.position),
            )
        raise make_compile_error(
            source=self._source,
            message=f"unexpected token: {current}",
            error_code="E001_UNEXPECTED_TOKEN",
            span=Span(start=start, end=self.position),
        )

    def _consume_whitespace(self) -> None:
        while (current := self._peek()) is not None and current.isspace():
            self._advance()

    def _peek(self, lookahead: int = 0) -> str | None:
        index = self._index + lookahead
        if index >= len(self._source):
            return None
        return self._source[index]

    def _advance(self) -> str:
        current = self._source[self._index]
        self._index += 1
        if current == "\n":
            self._line += 1
            self._column = 1
        else:
            self._column += 1
        return current
