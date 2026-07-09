from typing import Any, Literal

from pydantic import BaseModel, Field

ParserStatus = Literal["completed", "failed"]
OverallStatus = Literal["completed", "partial", "failed"]


class ParserResult(BaseModel):
    status: ParserStatus
    version: str | None = None
    duration_seconds: float
    error: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] | None = None
    parsed: dict[str, Any] | None = None


class ExtractionResponse(BaseModel):
    schema_version: str = "0.2.0"
    request_id: str
    status: OverallStatus
    document: dict[str, Any]
    options: dict[str, Any]
    processing: dict[str, Any]
    docling: ParserResult
    grobid: ParserResult
    merged: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
