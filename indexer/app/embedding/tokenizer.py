from __future__ import annotations

from typing import Any


class HuggingFaceTokenCounter:
    """Token counter backed by the exact tokenizer used by the embedding model.

    Counts are computed without special tokens so that token budgets remain
    approximately additive when the chunker subtracts metadata overhead from a
    maximum. The embedding service separately validates the final model input.
    """

    def __init__(self, *, tokenizer: Any, model_name: str) -> None:
        self._tokenizer = tokenizer
        self._model_name = model_name

    @property
    def name(self) -> str:
        return f"huggingface:{self._model_name}"

    def count(self, text: str) -> int:
        if not text:
            return 0
        token_ids = self._tokenizer.encode(
            text,
            add_special_tokens=False,
            truncation=False,
        )
        return len(token_ids)

    def split(self, text: str, max_tokens: int) -> list[str]:
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if not text.strip():
            return []

        token_ids = self._tokenizer.encode(
            text,
            add_special_tokens=False,
            truncation=False,
        )
        if len(token_ids) <= max_tokens:
            return [text.strip()]

        pieces: list[str] = []
        for start in range(0, len(token_ids), max_tokens):
            piece_ids = token_ids[start : start + max_tokens]
            piece = self._tokenizer.decode(
                piece_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            ).strip()
            if piece:
                pieces.append(piece)
        return pieces

    def truncate(self, text: str, max_tokens: int) -> str:
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if not text.strip():
            return ""

        token_ids = self._tokenizer.encode(
            text,
            add_special_tokens=False,
            truncation=False,
        )
        if len(token_ids) <= max_tokens:
            return text.strip()

        return self._tokenizer.decode(
            token_ids[:max_tokens],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        ).strip()
