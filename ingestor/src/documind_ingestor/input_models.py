from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ForwardCompatibleModel(BaseModel):
    """Accept future indexer fields while validating the fields used by this adapter."""

    model_config = ConfigDict(extra="allow")


class ChunkRecord(ForwardCompatibleModel):
    user_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)

    chunk_id: str = Field(min_length=1)
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

    caption: str | None = None
    text: str | None = None
    summary: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    table_text: str | None = None
    formula_text: str | None = None
    formula_latex: str | None = None

    content: str = Field(min_length=1)
    retrieval_text: str = Field(min_length=1)
    token_count: int = Field(ge=1)
    oversized: bool = False
    warnings: list[str] = Field(default_factory=list)

    content_hash: str = Field(min_length=1)
    chunker_version: str = Field(min_length=1)
    tokenizer_name: str = Field(min_length=1)

    embedding_status: Literal["pending", "embedded", "skipped", "disabled"] = "pending"
    embedding_model: str | None = None
    embedding_dimensions: int | None = Field(default=None, ge=1)
    embedding: list[float] | None = None

    @field_validator("source_ids", "child_chunk_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item for item in value if item))

    @field_validator("embedding")
    @classmethod
    def float_embedding(cls, value: list[float] | None) -> list[float] | None:
        return None if value is None else [float(item) for item in value]


class ChunkCounts(ForwardCompatibleModel):
    total: int = Field(default=0, ge=0)


class EmbeddingRunInfo(ForwardCompatibleModel):
    enabled: bool = False
    model: str | None = None
    dimensions: int | None = Field(default=None, ge=1)


class ChunkingOutput(ForwardCompatibleModel):
    output_schema_version: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    canonical_schema_version: str = Field(min_length=1)
    input_directory: str = ""
    chunker_version: str = Field(min_length=1)
    tokenizer_name: str = Field(min_length=1)
    counts: ChunkCounts
    embedding: EmbeddingRunInfo = Field(default_factory=EmbeddingRunInfo)
    chunks: list[ChunkRecord]
    references: list[dict[str, Any]] = Field(default_factory=list)


class CanonicalDocumentInfo(ForwardCompatibleModel):
    filename: str | None = None
    source_pdf: str | None = None


class CanonicalMetadata(ForwardCompatibleModel):
    title: str | None = None
    authors: list[Any] = Field(default_factory=list)
    language: str | None = None
    source_filename: str | None = None


class CanonicalDocument(ForwardCompatibleModel):
    schema_version: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    document: CanonicalDocumentInfo = Field(default_factory=CanonicalDocumentInfo)
    metadata: CanonicalMetadata = Field(default_factory=CanonicalMetadata)
