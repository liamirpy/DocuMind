from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path

from app.api.settings import ApiSettings
from app.chunking.models import IngestionContext, QueryEmbeddingOutput
from app.chunking.pipeline import DirectoryChunkingPipeline
from app.chunking.token_counter import RegexTokenCounter
from app.embedding import ChunkEmbeddingService, build_embedding_provider
from app.embedding.base import EmbeddingProvider
from app.input_package.reader import load_input_package

logger = logging.getLogger(__name__)


class IndexerRuntime:
    """Reusable chunking and embedding runtime shared by API jobs."""

    def __init__(self, settings: ApiSettings) -> None:
        self.settings = settings
        self.config = settings.build_chunking_config()
        self._provider: EmbeddingProvider | None = None
        self._provider_lock = threading.Lock()
        self._inference_lock = threading.Lock()

    def preload(self) -> None:
        if self.config.embedding.enabled:
            self.get_provider()

    def get_provider(self) -> EmbeddingProvider:
        if self._provider is not None:
            return self._provider
        with self._provider_lock:
            if self._provider is None:
                logger.info(
                    "Loading embedding provider=%s model=%s",
                    self.config.embedding.provider,
                    self.config.embedding.model_name,
                )
                self._provider = build_embedding_provider(self.config.embedding)
                logger.info(
                    "Embedding model loaded: model=%s dimensions=%s device=%s",
                    self._provider.model_name,
                    self._provider.dimensions,
                    self._provider.device,
                )
        return self._provider

    def process(
        self,
        *,
        user_id: str,
        document_id: str,
        input_directory: Path,
        output_file: Path,
        skip_embedding: bool,
        stage_callback: Callable[[str], None] | None = None,
    ):
        config = self.config
        if skip_embedding:
            config = config.model_copy(
                update={
                    "embedding": config.embedding.model_copy(update={"enabled": False}),
                }
            )
            provider = None
            token_counter = RegexTokenCounter()
        else:
            if stage_callback:
                stage_callback("loading_model")
            provider = self.get_provider() if config.embedding.enabled else None
            token_counter = provider.token_counter if provider is not None else RegexTokenCounter()

        if stage_callback:
            stage_callback("validating_input")
        package = load_input_package(
            input_directory,
            canonical_filename=config.package_assets.canonical_filename,
        )
        context = IngestionContext(user_id=user_id, document_id=document_id)

        if stage_callback:
            stage_callback("chunking")
        chunk_output = DirectoryChunkingPipeline(
            config=config,
            token_counter=token_counter,
        ).run(
            package=package,
            context=context,
        )

        if stage_callback:
            stage_callback("embedding")
        embedding_service = ChunkEmbeddingService(
            config=config.embedding,
            provider=provider,
        )
        if provider is None:
            output = embedding_service.run(chunk_output)
        else:
            # Sentence Transformer model instances are shared across API requests.
            # Serialize inference to avoid concurrent access to one model instance.
            with self._inference_lock:
                output = embedding_service.run(chunk_output)

        if stage_callback:
            stage_callback("writing_output")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_file = output_file.with_name(f".{output_file.name}.tmp-{os.getpid()}")
        temporary_file.write_text(
            json.dumps(output.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_file, output_file)
        return output

    def embed_query(self, query_text: str) -> QueryEmbeddingOutput:
        config = self.config
        if not config.embedding.enabled:
            raise ValueError("Embedding is disabled by environment configuration")

        provider = self.get_provider()
        text = query_text.strip()
        if not text:
            raise ValueError("query_text must not be empty")
        with self._inference_lock:
            vector = provider.embed_query(text)
        if len(vector) != provider.dimensions:
            raise RuntimeError(
                f"Embedding provider returned {len(vector)} values; expected {provider.dimensions}"
            )
        return QueryEmbeddingOutput(
            provider=provider.provider_name,
            model=provider.model_name,
            dimensions=provider.dimensions,
            normalized=provider.normalized,
            device=provider.device,
            tokenizer_name=provider.token_counter.name,
            token_count=provider.token_counter.count(text),
            query_text=text,
            embedding=vector,
        )
