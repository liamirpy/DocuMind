from typing import Any, Literal

from pydantic import BaseModel, Field


class PathProcessRequest(BaseModel):
    """Process a PDF that is already available inside a mounted directory."""

    input_directory: str = Field(
        min_length=1,
        description="Absolute container directory containing the input PDF.",
        examples=["/host/home/user/papers"],
    )
    input_filename: str = Field(
        min_length=1,
        description="PDF filename inside input_directory; path separators are not allowed.",
        examples=["article.pdf"],
    )
    output_directory: str = Field(
        min_length=1,
        description="Absolute container directory where the package will be written.",
        examples=["/host/home/user/results"],
    )
    output_folder: str | None = Field(
        default=None,
        description="Optional package folder name below output_directory.",
        examples=["article_run_001"],
    )
    use_llm: bool = False
    overwrite: bool | None = None


class ProcessResponse(BaseModel):
    schema_version: str = "0.3.0"
    status: Literal["completed", "completed_with_warnings", "failed"]
    document_id: str
    package_name: str
    output_directory: str
    output_folder: str
    package_directory: str
    canonical_json: str
    zip_file: str | None = None
    urls: dict[str, str | None] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    processing: dict[str, Any] = Field(default_factory=dict)
