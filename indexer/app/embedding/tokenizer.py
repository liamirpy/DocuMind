from __future__ import annotations

from typing import Any, Sequence


class HuggingFaceTokenCounter:
    """Token counter backed by the exact tokenizer used by the embedding model.

    Counts are computed without special tokens so that token budgets remain
    approximately additive when the chunker subtracts metadata overhead from a
    maximum.

    Important tokenizer detail
    --------------------------
    A decoded slice of token IDs is not always round-trip stable. For example,
    decoding 359 IDs and encoding the resulting string again can occasionally
    produce 360 IDs because whitespace/subword boundaries changed. The chunker
    counts the decoded string, so ``split()`` must verify the decoded piece and
    shrink the source ID window when necessary.
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

    def _decode(self, token_ids: Sequence[int]) -> str:
        return self._tokenizer.decode(
            token_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        ).strip()

    def _decode_fitting_window(
        self,
        token_ids: Sequence[int],
        *,
        start: int,
        maximum_end: int,
        max_tokens: int,
    ) -> tuple[int, str]:
        """Return the largest decoded ID window that re-encodes within budget."""

        end = maximum_end

        while end > start:
            piece = self._decode(token_ids[start:end])

            if not piece:
                end -= 1
                continue

            actual_tokens = self.count(piece)

            if actual_tokens <= max_tokens:
                return end, piece

            # Usually the decoded string is only one token over budget. Shrink
            # by the measured overflow, then verify again on the next loop.
            end -= max(1, actual_tokens - max_tokens)

        raise RuntimeError(
            "The tokenizer could not produce a non-empty text piece within "
            f"the {max_tokens}-token limit."
        )

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
            cleaned = text.strip()

            # Even the original string is checked so the method's contract is
            # explicit for custom tokenizers.
            if self.count(cleaned) <= max_tokens:
                return [cleaned]

        pieces: list[str] = []
        start = 0

        while start < len(token_ids):
            maximum_end = min(
                start + max_tokens,
                len(token_ids),
            )

            end, piece = self._decode_fitting_window(
                token_ids,
                start=start,
                maximum_end=maximum_end,
                max_tokens=max_tokens,
            )

            pieces.append(piece)
            start = end

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
            cleaned = text.strip()
            if self.count(cleaned) <= max_tokens:
                return cleaned

        _, piece = self._decode_fitting_window(
            token_ids,
            start=0,
            maximum_end=min(max_tokens, len(token_ids)),
            max_tokens=max_tokens,
        )
        return piece
