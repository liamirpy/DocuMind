from __future__ import annotations

import hashlib
import math

from app.chunking.config import EmbeddingConfig
from app.chunking.token_counter import RegexTokenCounter


class DevelopmentHashEmbeddingProvider:
    """Deterministic non-semantic vectors for tests and pipeline smoke checks.

    Never use this provider for production retrieval. It exists so the complete
    package can be tested without downloading a neural model.
    """

    def __init__(self, *, config: EmbeddingConfig) -> None:
        self._config = config
        self._dimensions = config.development_hash_dimensions
        self._token_counter = RegexTokenCounter()

    @property
    def provider_name(self) -> str:
        return "development_hash"

    @property
    def model_name(self) -> str:
        return "development-hash-v1"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def max_sequence_length(self) -> int | None:
        return self._config.max_sequence_length

    @property
    def device(self) -> str | None:
        return "cpu"

    @property
    def normalized(self) -> bool:
        return self._config.normalize_embeddings

    @property
    def token_counter(self) -> RegexTokenCounter:
        return self._token_counter

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text, prefix="document") for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text, prefix="query")

    def _vector(self, text: str, *, prefix: str) -> list[float]:
        seed = f"{prefix}\0{text}".encode()
        values: list[float] = []
        counter = 0
        while len(values) < self._dimensions:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for byte in digest:
                values.append((byte / 127.5) - 1.0)
                if len(values) == self._dimensions:
                    break
            counter += 1

        if self._config.normalize_embeddings:
            norm = math.sqrt(sum(value * value for value in values))
            if norm:
                values = [value / norm for value in values]
        return values
