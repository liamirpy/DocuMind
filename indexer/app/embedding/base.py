from __future__ import annotations

from typing import Protocol

from app.chunking.token_counter import TokenCounter


class EmbeddingProvider(Protocol):
    """Provider interface shared by local and remote embedding backends."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    @property
    def max_sequence_length(self) -> int | None: ...

    @property
    def device(self) -> str | None: ...

    @property
    def normalized(self) -> bool: ...

    @property
    def token_counter(self) -> TokenCounter: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...
