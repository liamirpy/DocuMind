from __future__ import annotations

from typing import Any

from app.chunking.config import EmbeddingConfig
from app.embedding.tokenizer import HuggingFaceTokenCounter


class SentenceTransformersEmbeddingProvider:
    """Local dense embeddings using Sentence Transformers and PyTorch."""

    def __init__(self, *, config: EmbeddingConfig) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on optional runtime dependency
            raise RuntimeError(
                "The sentence-transformers provider is enabled, but the package is not installed. "
                "Run `python3 -m pip install -r requirements.txt`."
            ) from exc

        device = None if config.device in (None, "", "auto") else config.device
        kwargs: dict[str, Any] = {
            "device": device,
            "trust_remote_code": config.trust_remote_code,
            "local_files_only": config.local_files_only,
        }
        if config.cache_folder:
            kwargs["cache_folder"] = config.cache_folder
        if config.revision:
            kwargs["revision"] = config.revision

        self._config = config
        self._model = SentenceTransformer(config.model_name, **kwargs)
        native_max = int(self._model.max_seq_length) if self._model.max_seq_length else None
        if config.max_sequence_length is not None:
            if native_max is not None and config.max_sequence_length > native_max:
                raise ValueError(
                    "embedding.max_sequence_length cannot exceed the model's native maximum "
                    f"({native_max}); got {config.max_sequence_length}."
                )
            self._model.max_seq_length = config.max_sequence_length

        dimension = self._model.get_sentence_embedding_dimension()
        if dimension is None:
            raise RuntimeError("The embedding model did not report an output dimension")
        self._dimensions = int(dimension)
        if (
            config.expected_dimensions is not None
            and self._dimensions != config.expected_dimensions
        ):
            raise ValueError(
                f"Embedding model {config.model_name!r} produces {self._dimensions} dimensions, "
                f"but embedding.expected_dimensions={config.expected_dimensions}."
            )

        tokenizer = getattr(self._model, "tokenizer", None)
        if tokenizer is None:
            raise RuntimeError("The SentenceTransformer model does not expose a tokenizer")
        self._token_counter = HuggingFaceTokenCounter(
            tokenizer=tokenizer,
            model_name=config.model_name,
        )

    @property
    def provider_name(self) -> str:
        return "sentence_transformers"

    @property
    def model_name(self) -> str:
        return self._config.model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def max_sequence_length(self) -> int | None:
        value = self._model.max_seq_length
        return int(value) if value else None

    @property
    def device(self) -> str | None:
        target_device = getattr(self._model, "device", None)
        return str(target_device) if target_device is not None else self._config.device

    @property
    def normalized(self) -> bool:
        return self._config.normalize_embeddings

    @property
    def token_counter(self) -> HuggingFaceTokenCounter:
        return self._token_counter

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        encoder = getattr(self._model, "encode_document", None)
        if encoder is None or not self._config.use_document_encoder:
            encoder = self._model.encode
        vectors = encoder(
            texts,
            batch_size=self._config.batch_size,
            show_progress_bar=self._config.show_progress_bar,
            convert_to_numpy=True,
            normalize_embeddings=self._config.normalize_embeddings,
        )
        return [[float(value) for value in vector] for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        encoder = getattr(self._model, "encode_query", None)
        if encoder is None or not self._config.use_query_encoder:
            encoder = self._model.encode
        vector = encoder(
            text,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=self._config.normalize_embeddings,
        )
        return [float(value) for value in vector]
