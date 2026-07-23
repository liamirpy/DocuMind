from typing import Any, Literal

from pydantic import BaseModel, Field


class ProcessResponse(BaseModel):
    schema_version: str = "0.3.0"
    status: Literal["completed", "completed_with_warnings", "failed"]
    document_id: str
    package_name: str
    output_folder: str
    package_directory: str
    canonical_json: str
    zip_file: str | None = None
    urls: dict[str, str | None] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    processing: dict[str, Any] = Field(default_factory=dict)
