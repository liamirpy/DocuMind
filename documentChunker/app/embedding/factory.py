from __future__ import annotations

from app.chunking.config import EmbeddingConfig
from app.embedding.base import EmbeddingProvider
from app.embedding.development_hash import DevelopmentHashEmbeddingProvider
from app.embedding.sentence_transformers import SentenceTransformersEmbeddingProvider


def build_embedding_provider(config: EmbeddingConfig) -> EmbeddingProvider:
    if config.provider == "sentence_transformers":
        return SentenceTransformersEmbeddingProvider(config=config)
    if config.provider == "development_hash":
        return DevelopmentHashEmbeddingProvider(config=config)
    raise ValueError(f"Unsupported embedding provider: {config.provider}")
