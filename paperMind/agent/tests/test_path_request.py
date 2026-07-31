import pytest
from pydantic import ValidationError

from app.models import PathProcessRequest


def test_path_process_request_accepts_directories_and_filename() -> None:
    request = PathProcessRequest(
        input_directory="/host/papers",
        input_filename="article.pdf",
        output_directory="/host/results",
        output_folder="run-001",
    )
    assert request.input_filename == "article.pdf"
    assert request.use_llm is False


def test_path_process_request_requires_non_empty_paths() -> None:
    with pytest.raises(ValidationError):
        PathProcessRequest(
            input_directory="",
            input_filename="article.pdf",
            output_directory="/host/results",
        )


def test_backend_managed_path_request_requires_backend_job_id() -> None:
    from app.models import BackendManagedPathProcessRequest

    request = BackendManagedPathProcessRequest(
        backend_job_id="document-job-123",
        input_directory="/host/papers",
        input_filename="article.pdf",
        output_directory="/host/results",
    )
    assert request.backend_job_id == "document-job-123"

    with pytest.raises(ValidationError):
        BackendManagedPathProcessRequest(
            backend_job_id="contains spaces",
            input_directory="/host/papers",
            input_filename="article.pdf",
            output_directory="/host/results",
        )
