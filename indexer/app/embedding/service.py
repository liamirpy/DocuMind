from __future__ import annotations

from dataclasses import dataclass

from app.chunking.config import EmbeddingConfig
from app.chunking.models import ChunkingOutput, EmbeddingRunInfo
from app.embedding.base import EmbeddingProvider


@dataclass(frozen=True)
class _PreparedEmbedding:
    chunk_index: int
    text: str
    token_count: int
    truncated: bool


class ChunkEmbeddingService:
    """Add dense vectors and embedding provenance to chunk records."""

    def __init__(
        self,
        *,
        config: EmbeddingConfig,
        provider: EmbeddingProvider | None,
    ) -> None:
        self.config = config
        self.provider = provider

    def run(self, output: ChunkingOutput) -> ChunkingOutput:
        if not self.config.enabled:
            chunks = [
                chunk.model_copy(
                    update={
                        "embedding_status": "disabled",
                    }
                )
                for chunk in output.chunks
            ]
            return output.model_copy(
                update={
                    "chunks": chunks,
                    "embedding": EmbeddingRunInfo(
                        enabled=False,
                        selection=self.config.selection,
                        embedded_chunk_count=0,
                        skipped_chunk_count=len(chunks),
                        truncated_chunk_count=0,
                    ),
                }
            )

        if self.provider is None:
            raise RuntimeError("Embedding is enabled but no embedding provider was supplied")

        prepared: list[_PreparedEmbedding] = []
        chunks = list(output.chunks)
        skipped_count = 0

        for index, chunk in enumerate(chunks):
            should_embed = self.config.selection == "all" or chunk.retrieval_enabled
            if not should_embed:
                chunks[index] = chunk.model_copy(update={"embedding_status": "skipped"})
                skipped_count += 1
                continue

            text, token_count, truncated = self._prepare_text(chunk.retrieval_text)
            prepared.append(
                _PreparedEmbedding(
                    chunk_index=index,
                    text=text,
                    token_count=token_count,
                    truncated=truncated,
                )
            )

        vectors = self.provider.embed_documents([item.text for item in prepared])
        if len(vectors) != len(prepared):
            raise RuntimeError(
                f"Embedding provider returned {len(vectors)} vectors for {len(prepared)} texts"
            )

        for item, vector in zip(prepared, vectors, strict=True):
            if len(vector) != self.provider.dimensions:
                raise RuntimeError(
                    f"Embedding provider returned a {len(vector)}-dimension vector; "
                    f"expected {self.provider.dimensions}"
                )
            chunk = chunks[item.chunk_index]
            chunks[item.chunk_index] = chunk.model_copy(
                update={
                    "embedding_status": "embedded",
                    "embedding_provider": self.provider.provider_name,
                    "embedding_model": self.provider.model_name,
                    "embedding_dimensions": self.provider.dimensions,
                    "embedding_normalized": self.provider.normalized,
                    "embedding_text": item.text,
                    "embedding_token_count": item.token_count,
                    "embedding_truncated": item.truncated,
                    "embedding": vector,
                }
            )

        summary = EmbeddingRunInfo(
            enabled=True,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            dimensions=self.provider.dimensions,
            normalized=self.provider.normalized,
            device=self.provider.device,
            tokenizer_name=self.provider.token_counter.name,
            model_max_sequence_length=self.provider.max_sequence_length,
            configured_max_input_tokens=self.config.max_input_tokens,
            selection=self.config.selection,
            batch_size=self.config.batch_size,
            embedded_chunk_count=len(prepared),
            skipped_chunk_count=skipped_count,
            truncated_chunk_count=sum(1 for item in prepared if item.truncated),
        )
        return output.model_copy(update={"chunks": chunks, "embedding": summary})

    def _prepare_text(self, text: str) -> tuple[str, int, bool]:
        if self.provider is None:  # pragma: no cover - guarded in run()
            raise RuntimeError("No embedding provider")

        token_counter = self.provider.token_counter
        model_max = self.provider.max_sequence_length
        configured_max = self.config.max_input_tokens
        limits = [value for value in (model_max, configured_max) if value is not None]
        effective_max = min(limits) if limits else None
        token_count = token_counter.count(text)

        if effective_max is None or token_count <= effective_max:
            return text, token_count, False

        if self.config.overlong_policy == "error":
            raise ValueError(
                f"Embedding input has {token_count} tokens, above the effective maximum "
                f"of {effective_max}. Reduce chunk sizes or set "
                'embedding.overlong_policy to "truncate".'
            )

        truncated_text = token_counter.truncate(text, effective_max)
        return truncated_text, token_counter.count(truncated_text), True
