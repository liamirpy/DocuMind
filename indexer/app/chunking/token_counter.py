from __future__ import annotations

import re
from typing import Protocol


class TokenCounter(Protocol):
    """Interface that can later be backed by the embedding model tokenizer."""

    @property
    def name(self) -> str: ...

    def count(self, text: str) -> int: ...

    def split(self, text: str, max_tokens: int) -> list[str]: ...

    def truncate(self, text: str, max_tokens: int) -> str: ...


class RegexTokenCounter:
    """Dependency-free approximate tokenizer for chunker development.

    Replace this adapter with the exact embedding model tokenizer before
    production embedding. The rest of the package only depends on the
    TokenCounter interface.
    """

    _token_pattern = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)

    @property
    def name(self) -> str:
        return "regex-approx-v1"

    def count(self, text: str) -> int:
        return len(self._token_pattern.findall(text))

    def split(self, text: str, max_tokens: int) -> list[str]:
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")

        matches = list(self._token_pattern.finditer(text))
        if not matches:
            return []
        if len(matches) <= max_tokens:
            return [text.strip()]

        pieces: list[str] = []
        for start in range(0, len(matches), max_tokens):
            window = matches[start : start + max_tokens]
            piece = text[window[0].start() : window[-1].end()].strip()
            if piece:
                pieces.append(piece)
        return pieces

    def truncate(self, text: str, max_tokens: int) -> str:
        pieces = self.split(text, max_tokens)
        return pieces[0] if pieces else ""
