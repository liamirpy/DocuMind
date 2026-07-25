from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ID_PATTERN = r"^[A-Za-z0-9_.:-]+$"


class IngestionContext(BaseModel):
    """Identity supplied by the application that owns the uploaded PDF."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(min_length=1, max_length=128, pattern=ID_PATTERN)
    document_id: str = Field(min_length=1, max_length=256, pattern=ID_PATTERN)


class ChunkRecord(BaseModel):
    """One output chunk ready for OpenSearch indexing."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    document_id: str
    source_document_id: str

    chunk_id: str = Field(min_length=64, max_length=64)
    chunk_ordinal: int = Field(ge=1)
    chunk_role: Literal["parent", "child", "standalone"]
    source_type: Literal["paragraph", "table", "figure", "formula"]

    parent_chunk_id: str | None = None
    child_chunk_ids: list[str] = Field(default_factory=list)
    retrieval_enabled: bool = True

    source_ids: list[str] = Field(min_length=1)
    title: str | None = None
    section_id: str | None = None
    section_path: str = ""
    section_path_parts: list[str] = Field(default_factory=list)

    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)

    # Explicit semantic fields for visual/scientific elements.
    caption: str | None = None
    text: str | None = None
    summary: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    table_text: str | None = None
    formula_text: str | None = None
    formula_latex: str | None = None

    # Human-readable source content and retrieval input.
    content: str = Field(min_length=1)
    retrieval_text: str = Field(min_length=1)
    content_token_count: int = Field(ge=1)
    token_count: int = Field(ge=1)
    configured_max_tokens: int = Field(ge=20)
    oversized: bool = False
    warnings: list[str] = Field(default_factory=list)

    content_hash: str = Field(min_length=64, max_length=64)
    chunker_version: str
    tokenizer_name: str

    # Dense embedding output. Parent chunks are skipped by default because
    # retrieval_enabled=False; they are loaded after child retrieval.
    embedding_status: Literal["pending", "embedded", "skipped", "disabled"] = "pending"
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = Field(default=None, ge=1)
    embedding_normalized: bool | None = None
    embedding_text: str | None = None
    embedding_token_count: int | None = Field(default=None, ge=0)
    embedding_truncated: bool = False
    embedding: list[float] | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_ids", "child_chunk_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @field_validator("embedding")
    @classmethod
    def validate_embedding_values(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        return [float(item) for item in value]


class ReferenceRecord(BaseModel):
    """One bibliography entry kept separate from normal RAG chunks."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    document_id: str
    source_document_id: str

    reference_id: str = Field(min_length=64, max_length=64)
    reference_ordinal: int = Field(ge=1)
    source_reference_id: str | None = None

    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: str | None = None
    doi: str | None = None
    raw_text: str | None = None

    retrieval_enabled: bool = False
    retrieval_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkCounts(BaseModel):
    total: int = 0
    parent: int = 0
    child: int = 0
    standalone: int = 0
    paragraph: int = 0
    table: int = 0
    figure: int = 0
    formula: int = 0
    references: int = 0
    oversized: int = 0


class EmbeddingRunInfo(BaseModel):
    """Summary of the embedding stage included in the output JSON."""

    enabled: bool = False
    provider: str | None = None
    model: str | None = None
    dimensions: int | None = Field(default=None, ge=1)
    normalized: bool | None = None
    device: str | None = None
    tokenizer_name: str | None = None
    model_max_sequence_length: int | None = Field(default=None, ge=1)
    configured_max_input_tokens: int | None = Field(default=None, ge=1)
    selection: Literal["retrieval_enabled", "all"] = "retrieval_enabled"
    batch_size: int | None = Field(default=None, ge=1)
    embedded_chunk_count: int = Field(default=0, ge=0)
    skipped_chunk_count: int = Field(default=0, ge=0)
    truncated_chunk_count: int = Field(default=0, ge=0)


class ChunkingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_schema_version: str = "3.0.0"
    user_id: str
    document_id: str
    source_document_id: str
    canonical_schema_version: str
    input_directory: str
    chunker_version: str
    tokenizer_name: str
    config: dict[str, Any]
    counts: ChunkCounts
    embedding: EmbeddingRunInfo = Field(default_factory=EmbeddingRunInfo)
    chunks: list[ChunkRecord]
    references: list[ReferenceRecord] = Field(default_factory=list)


class QueryEmbeddingOutput(BaseModel):
    """Vector payload for querying the future OpenSearch index."""

    provider: str
    model: str
    dimensions: int = Field(ge=1)
    normalized: bool
    device: str | None = None
    tokenizer_name: str
    token_count: int = Field(ge=0)
    query_text: str = Field(min_length=1)
    embedding: list[float]
