from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.chunking.models import ID_PATTERN


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobStage(StrEnum):
    QUEUED = "queued"
    VALIDATING_INPUT = "validating_input"
    LOADING_MODEL = "loading_model"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    WRITING_OUTPUT = "writing_output"
    COMPLETED = "completed"
    FAILED = "failed"


class IndexJobRequest(BaseModel):
    """Request to process one already-extracted PDF output directory.

    `user_name` is accepted as a convenience alias. In production, prefer the
    PostgreSQL user UUID in `user_id`.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=ID_PATTERN,
    )
    user_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=ID_PATTERN,
    )
    document_id: str = Field(min_length=1, max_length=256, pattern=ID_PATTERN)
    input_directory: str = Field(min_length=1, max_length=4096)
    output_directory: str = Field(min_length=1, max_length=4096)
    output_filename: str = Field(
        default="chunks.json",
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    skip_embedding: bool = False
    overwrite: bool = False

    @model_validator(mode="after")
    def validate_owner(self) -> IndexJobRequest:
        if self.user_id is None and self.user_name is None:
            raise ValueError("Provide user_id or user_name")
        if self.user_id and self.user_name and self.user_id != self.user_name:
            raise ValueError("When both are provided, user_id and user_name must match")
        return self

    @property
    def resolved_user_id(self) -> str:
        return self.user_id or self.user_name or ""


class JobResultSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_file: str
    source_document_id: str
    total_chunks: int = Field(ge=0)
    parent_chunks: int = Field(ge=0)
    child_chunks: int = Field(ge=0)
    standalone_chunks: int = Field(ge=0)
    table_chunks: int = Field(ge=0)
    figure_chunks: int = Field(ge=0)
    formula_chunks: int = Field(ge=0)
    references: int = Field(ge=0)
    embedding_enabled: bool
    embedded_chunks: int = Field(ge=0)
    skipped_chunks: int = Field(ge=0)
    embedding_model: str | None = None
    embedding_dimensions: int | None = Field(default=None, ge=1)


class JobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatus
    stage: JobStage
    user_id: str
    document_id: str
    input_directory: str
    output_directory: str
    output_filename: str
    skip_embedding: bool
    overwrite: bool
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: JobResultSummary | None = None
    error_type: str | None = None
    error_message: str | None = None


class JobListResponse(BaseModel):
    jobs: list[JobRecord]


class QueryEmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_text: str = Field(min_length=1, max_length=100_000)


class QueryEmbeddingResponse(BaseModel):
    provider: str
    model: str
    dimensions: int = Field(ge=1)
    normalized: bool
    device: str | None = None
    tokenizer_name: str
    token_count: int = Field(ge=0)
    query_text: str
    embedding: list[float]


class HealthResponse(BaseModel):
    status: str
    version: str
    details: dict[str, Any] = Field(default_factory=dict)
