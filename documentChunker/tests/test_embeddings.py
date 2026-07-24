from __future__ import annotations

import math

import pytest

from app.chunking.config import ChunkingConfig
from app.chunking.models import IngestionContext
from app.chunking.pipeline import DirectoryChunkingPipeline
from app.embedding.development_hash import DevelopmentHashEmbeddingProvider
from app.embedding.service import ChunkEmbeddingService
from app.input_package.reader import load_input_package


def development_config(*, dimensions: int = 12) -> ChunkingConfig:
    config = ChunkingConfig()
    return config.model_copy(
        update={
            "embedding": config.embedding.model_copy(
                update={
                    "provider": "development_hash",
                    "model_name": "development-hash-v1",
                    "expected_dimensions": dimensions,
                    "development_hash_dimensions": dimensions,
                    "show_progress_bar": False,
                }
            )
        }
    )


def test_embedding_service_embeds_only_retrieval_enabled_chunks(sample_directory) -> None:
    config = development_config(dimensions=12)
    provider = DevelopmentHashEmbeddingProvider(config=config.embedding)
    package = load_input_package(sample_directory)
    context = IngestionContext(user_id="user_123", document_id="doc_456")
    chunk_output = DirectoryChunkingPipeline(
        config=config,
        token_counter=provider.token_counter,
    ).run(package=package, context=context)

    output = ChunkEmbeddingService(config=config.embedding, provider=provider).run(chunk_output)

    assert output.embedding.enabled is True
    assert output.embedding.dimensions == 12
    assert output.embedding.embedded_chunk_count > 0
    assert output.embedding.skipped_chunk_count > 0

    for chunk in output.chunks:
        if chunk.retrieval_enabled:
            assert chunk.embedding_status == "embedded"
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 12
            assert chunk.embedding_model == "development-hash-v1"
            assert chunk.embedding_dimensions == 12
            assert chunk.embedding_text == chunk.retrieval_text
            assert math.isclose(
                math.sqrt(sum(value * value for value in chunk.embedding)),
                1.0,
                rel_tol=1e-6,
            )
        else:
            assert chunk.embedding_status == "skipped"
            assert chunk.embedding is None


def test_development_hash_provider_is_deterministic() -> None:
    config = development_config(dimensions=8)
    provider = DevelopmentHashEmbeddingProvider(config=config.embedding)
    first = provider.embed_documents(["same text"])[0]
    second = provider.embed_documents(["same text"])[0]
    different = provider.embed_documents(["different text"])[0]

    assert first == second
    assert first != different
    assert len(first) == 8


def test_embedding_service_can_truncate_overlong_input(sample_directory) -> None:
    config = development_config(dimensions=8)
    config = config.model_copy(
        update={
            "embedding": config.embedding.model_copy(
                update={
                    "max_input_tokens": 20,
                    "overlong_policy": "truncate",
                }
            )
        }
    )
    provider = DevelopmentHashEmbeddingProvider(config=config.embedding)
    package = load_input_package(sample_directory)
    context = IngestionContext(user_id="user_123", document_id="doc_456")
    chunk_output = DirectoryChunkingPipeline(config=config).run(
        package=package,
        context=context,
    )

    output = ChunkEmbeddingService(config=config.embedding, provider=provider).run(chunk_output)

    assert output.embedding.truncated_chunk_count > 0
    assert any(chunk.embedding_truncated for chunk in output.chunks if chunk.retrieval_enabled)


def test_embedding_service_errors_on_overlong_input(sample_directory) -> None:
    config = development_config(dimensions=8)
    config = config.model_copy(
        update={
            "embedding": config.embedding.model_copy(
                update={
                    "max_input_tokens": 5,
                    "overlong_policy": "error",
                }
            )
        }
    )
    provider = DevelopmentHashEmbeddingProvider(config=config.embedding)
    package = load_input_package(sample_directory)
    context = IngestionContext(user_id="user_123", document_id="doc_456")
    chunk_output = DirectoryChunkingPipeline(config=config).run(
        package=package,
        context=context,
    )

    with pytest.raises(ValueError, match="Embedding input has"):
        ChunkEmbeddingService(config=config.embedding, provider=provider).run(chunk_output)
