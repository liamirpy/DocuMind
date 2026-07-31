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


class BackendManagedPathProcessRequest(PathProcessRequest):
    """Path request whose lifecycle is tracked by the DocuMind backend."""

    backend_job_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="Backend-generated correlation ID used for callbacks.",
    )


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


class JobAcceptedResponse(BaseModel):
    job_id: str
    document_id: str
    filename: str
    status: Literal["queued"] = "queued"
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    document_id: str
    filename: str
    status: Literal["queued", "running", "completed", "failed"]
    status_url: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result: ProcessResponse | None = None
    error: str | None = None
