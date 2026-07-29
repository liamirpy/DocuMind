from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OpenSearchChunkDocument(BaseModel):
    """One `_source` document that exactly matches the strict index mapping."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    document_id: str
    document_public_id: str
    source_document_id: str

    chunk_id: str
    chunk_index: int = Field(ge=1)
    source_type: str
    chunk_role: str
    parent_chunk_id: str | None = None
    child_chunk_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    retrieval_enabled: bool
    oversized: bool

    document_title: str | None = None
    document_authors: list[str] = Field(default_factory=list)
    original_filename: str | None = None
    file_type: str | None = None
    language: str | None = None

    section_id: str | None = None
    section_path: list[str] = Field(default_factory=list)
    section_path_text: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)

    content: str
    retrieval_text: str
    caption: str | None = None
    summary: str | None = None
    element_text: str | None = None
    table_text: str | None = None
    formula_text: str | None = None
    formula_latex: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    token_count: int = Field(ge=1)
    content_hash: str
    canonical_schema_version: str
    chunks_schema_version: str
    chunker_version: str
    tokenizer_name: str

    embedding_model: str | None = None
    embedding_dimensions: int | None = Field(default=None, ge=1)
    indexed_at: datetime
    embedding: list[float] | None = None

    @field_validator("child_chunk_ids", "source_ids", "section_path", "document_authors")
    @classmethod
    def unique_strings(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item for item in value if item))

    @field_validator("embedding")
    @classmethod
    def finite_embedding(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        converted = [float(item) for item in value]
        if any(not math.isfinite(item) for item in converted):
            raise ValueError("embedding contains NaN or infinite values")
        return converted

    @model_validator(mode="after")
    def validate_embedding_metadata(self) -> OpenSearchChunkDocument:
        if self.embedding is None:
            if self.embedding_dimensions is not None:
                raise ValueError("embedding_dimensions is set but embedding is absent")
            return self

        if self.embedding_dimensions is None:
            raise ValueError("embedding_dimensions is required when embedding is present")
        if len(self.embedding) != self.embedding_dimensions:
            raise ValueError(
                "embedding length does not match embedding_dimensions: "
                f"{len(self.embedding)} != {self.embedding_dimensions}"
            )
        return self

    def source(self) -> dict[str, Any]:
        """Return a JSON-ready source without null fields."""

        return self.model_dump(mode="json", exclude_none=True)
