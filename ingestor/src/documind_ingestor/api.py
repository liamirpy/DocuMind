from __future__ import annotations

import hmac
import logging
import os
import stat
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any, BinaryIO

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from documind_ingestor.opensearch_client import OpenSearchIngestionError
from documind_ingestor.service import IngestionConfig, ingest_chunks
from documind_ingestor.transform import DocumentMetadata

logger = logging.getLogger(__name__)

app = FastAPI(
    title="DocuMind Chunk Ingestor Upload API",
    version="2.0.0",
    description=(
        "Upload a chunks.json file or a ZIP containing a chunk directory, validate it, "
        "and ingest it into OpenSearch. No host input-directory mount is required."
    ),
)


class IngestParameters(BaseModel):
    """JSON parameters sent in the multipart form field named ``parameters``."""

    model_config = ConfigDict(extra="forbid")

    chunks_path: str = Field(
        default="chunks.json",
        min_length=1,
        description=(
            "Path to chunks.json inside an uploaded ZIP. A directory path is also accepted "
            "and resolves to <directory>/chunks.json. When omitted, the API auto-discovers "
            "a single chunks.json file in the archive."
        ),
        examples=["doc_457/chunks.json"],
    )
    canonical_path: str | None = Field(
        default=None,
        description="Optional canonical JSON path inside the uploaded ZIP.",
    )
    index: str | None = Field(
        default=None,
        description="Optional target index override; defaults to OPENSEARCH_INDEX.",
    )
    expected_embedding_dimensions: int | None = Field(default=None, ge=1)
    allow_missing_embeddings: bool | None = None
    replace_document: bool | None = None
    refresh: bool | None = None
    install_template: bool | None = None
    dry_run: bool = False

    document_public_id: str | None = None
    document_title: str | None = None
    document_authors: list[str] = Field(default_factory=list)
    original_filename: str | None = None
    file_type: str | None = None
    language: str | None = None


class HealthResponse(BaseModel):
    status: str


def _environment_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Environment variable {name} must be true or false")


def _environment_int(name: str, *, default: int, minimum: int = 1) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"Environment variable {name} must be at least {minimum}")
    return value


def _environment_path(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    return Path(value) if value else None


def _authorise(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    expected = os.getenv("INGESTOR_API_KEY", "")
    if expected and not hmac.compare_digest(expected, x_api_key or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def _safe_relative_path(raw_path: str, *, field_name: str) -> Path:
    candidate = Path(raw_path.replace("\\", "/"))
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise ValueError(f"{field_name} must be a relative path without '..'")
    if not candidate.parts or candidate == Path("."):
        raise ValueError(f"{field_name} must not be empty")
    return candidate


async def _save_upload(upload: UploadFile, destination: Path, *, max_bytes: int) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with destination.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(
                    f"Uploaded file exceeds INGESTOR_MAX_UPLOAD_BYTES ({max_bytes} bytes)"
                )
            output.write(chunk)
    await upload.close()
    return total


def _copy_limited(source: BinaryIO, destination: BinaryIO, *, remaining: int) -> int:
    copied = 0
    while chunk := source.read(1024 * 1024):
        copied += len(chunk)
        if copied > remaining:
            raise ValueError("Extracted ZIP content exceeds INGESTOR_MAX_EXTRACTED_BYTES")
        destination.write(chunk)
    return copied


def _extract_zip_securely(
    archive_path: Path,
    destination: Path,
    *,
    max_files: int,
    max_extracted_bytes: int,
) -> None:
    extracted_bytes = 0
    extracted_files = 0

    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            relative = _safe_relative_path(info.filename, field_name="ZIP member path")
            target = destination / relative

            unix_type = (info.external_attr >> 16) & 0o170000
            if unix_type == stat.S_IFLNK:
                raise ValueError(f"ZIP symbolic links are not allowed: {info.filename}")
            if info.flag_bits & 0x1:
                raise ValueError(f"Encrypted ZIP members are not supported: {info.filename}")

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            extracted_files += 1
            if extracted_files > max_files:
                raise ValueError(
                    f"ZIP contains more than INGESTOR_MAX_ARCHIVE_FILES ({max_files}) files"
                )
            if info.file_size < 0 or extracted_bytes + info.file_size > max_extracted_bytes:
                raise ValueError(
                    "Extracted ZIP content exceeds INGESTOR_MAX_EXTRACTED_BYTES "
                    f"({max_extracted_bytes} bytes)"
                )

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                extracted_bytes += _copy_limited(
                    source,
                    output,
                    remaining=max_extracted_bytes - extracted_bytes,
                )


def _resolve_archive_file(
    root: Path,
    raw_path: str,
    *,
    field_name: str,
    default_filename: str | None = None,
) -> Path:
    relative = _safe_relative_path(raw_path, field_name=field_name)
    candidate = root / relative
    if default_filename and candidate.is_dir():
        candidate = candidate / default_filename
    if not candidate.is_file():
        raise ValueError(f"{field_name} does not identify a file in the uploaded ZIP: {raw_path}")
    return candidate


def _find_chunks_file(root: Path, requested_path: str) -> Path:
    relative = _safe_relative_path(requested_path, field_name="chunks_path")
    candidate = root / relative
    if candidate.is_dir():
        candidate = candidate / "chunks.json"
    if candidate.is_file():
        return candidate

    if requested_path == "chunks.json":
        matches = sorted(path for path in root.rglob("chunks.json") if path.is_file())
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ValueError("No chunks.json file was found in the uploaded ZIP")
        relative_matches = ", ".join(str(path.relative_to(root)) for path in matches[:10])
        raise ValueError(
            "Multiple chunks.json files were found. Set parameters.chunks_path to one of: "
            f"{relative_matches}"
        )

    raise ValueError(
        f"chunks_path does not identify a file in the uploaded ZIP: {requested_path}"
    )



def _build_config(
    *,
    params: IngestParameters,
    input_path: Path,
    allowed_root: Path,
    canonical_json: Path | None,
) -> IngestionConfig:
    return IngestionConfig(
        input_path=input_path,
        input_filename="chunks.json",
        allowed_input_root=allowed_root,
        url=os.getenv("OPENSEARCH_URL", "http://localhost:9200"),
        index=params.index or os.getenv("OPENSEARCH_INDEX", "documind-chunks-v1"),
        username=os.getenv("OPENSEARCH_USERNAME") or None,
        password=os.getenv("OPENSEARCH_PASSWORD") or None,
        verify_certs=_environment_bool("OPENSEARCH_VERIFY_CERTS", default=False),
        ca_certs=_environment_path("OPENSEARCH_CA_CERTS"),
        expected_embedding_dimensions=(
            params.expected_embedding_dimensions
            or int(os.getenv("OPENSEARCH_EMBEDDING_DIMENSIONS", "1024"))
        ),
        batch_size=int(os.getenv("OPENSEARCH_BULK_BATCH_SIZE", "250")),
        request_timeout_seconds=float(
            os.getenv("OPENSEARCH_REQUEST_TIMEOUT_SECONDS", "120")
        ),
        wait_timeout_seconds=float(os.getenv("OPENSEARCH_WAIT_TIMEOUT_SECONDS", "120")),
        wait_interval_seconds=float(os.getenv("OPENSEARCH_WAIT_INTERVAL_SECONDS", "2")),
        install_template=(
            params.install_template
            if params.install_template is not None
            else _environment_bool("OPENSEARCH_INSTALL_TEMPLATE", default=False)
        ),
        template_name=os.getenv("OPENSEARCH_TEMPLATE_NAME", "documind-chunks-template"),
        template_file=_environment_path("OPENSEARCH_TEMPLATE_FILE"),
        allow_missing_embeddings=(
            params.allow_missing_embeddings
            if params.allow_missing_embeddings is not None
            else _environment_bool("INGESTOR_ALLOW_MISSING_EMBEDDINGS", default=False)
        ),
        replace_document=(
            params.replace_document
            if params.replace_document is not None
            else _environment_bool("INGESTOR_REPLACE_DOCUMENT", default=True)
        ),
        refresh=(
            params.refresh
            if params.refresh is not None
            else _environment_bool("INGESTOR_REFRESH", default=True)
        ),
        canonical_json=canonical_json,
        metadata=DocumentMetadata(
            document_public_id=params.document_public_id,
            document_title=params.document_title,
            document_authors=params.document_authors,
            original_filename=params.original_filename,
            file_type=params.file_type,
            language=params.language,
        ),
        dry_run=params.dry_run,
    )


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/ingest", dependencies=[Depends(_authorise)], tags=["ingestion"])
async def ingest(
    payload: Annotated[
        UploadFile,
        File(
            description=(
                "A chunks.json file or a ZIP containing the document's chunk directory."
            )
        ),
    ],
    parameters: Annotated[
        str,
        Form(
            description=(
                "JSON object containing optional ingestion parameters. For ZIP uploads, "
                "set chunks_path when the archive contains multiple chunks.json files."
            )
        ),
    ] = "{}",
    canonical_file: Annotated[
        UploadFile | None,
        File(description="Optional canonical_document.json upload for a direct JSON payload."),
    ] = None,
) -> dict[str, Any]:
    """Ingest an uploaded chunks JSON file or ZIP archive without an input mount."""

    try:
        params = IngestParameters.model_validate_json(parameters or "{}")
        max_upload_bytes = _environment_int(
            "INGESTOR_MAX_UPLOAD_BYTES",
            default=512 * 1024 * 1024,
        )
        max_archive_files = _environment_int("INGESTOR_MAX_ARCHIVE_FILES", default=10_000)
        max_extracted_bytes = _environment_int(
            "INGESTOR_MAX_EXTRACTED_BYTES",
            default=2 * 1024 * 1024 * 1024,
        )

        uploaded_name = Path(payload.filename or "upload").name
        with TemporaryDirectory(prefix="documind-upload-") as temporary_directory:
            workspace = Path(temporary_directory)
            stored_payload = workspace / "payload.bin"
            await _save_upload(payload, stored_payload, max_bytes=max_upload_bytes)

            is_zip = zipfile.is_zipfile(stored_payload)
            canonical_json: Path | None = None

            if is_zip:
                extracted_root = workspace / "archive"
                extracted_root.mkdir()
                _extract_zip_securely(
                    stored_payload,
                    extracted_root,
                    max_files=max_archive_files,
                    max_extracted_bytes=max_extracted_bytes,
                )
                chunks_json = _find_chunks_file(extracted_root, params.chunks_path)
                allowed_root = extracted_root
                if params.canonical_path:
                    canonical_json = _resolve_archive_file(
                        extracted_root,
                        params.canonical_path,
                        field_name="canonical_path",
                    )
                if canonical_file is not None:
                    raise ValueError(
                        "canonical_file cannot be combined with a ZIP payload; put the canonical "
                        "file in the ZIP and use parameters.canonical_path when necessary"
                    )
            else:
                if params.chunks_path != "chunks.json":
                    raise ValueError("chunks_path is only used when payload is a ZIP archive")
                if params.canonical_path is not None:
                    raise ValueError("canonical_path is only used when payload is a ZIP archive")
                allowed_root = workspace / "direct"
                allowed_root.mkdir()
                chunks_json = allowed_root / "chunks.json"
                stored_payload.replace(chunks_json)
                if canonical_file is not None:
                    canonical_json = allowed_root / "canonical_document.json"
                    await _save_upload(
                        canonical_file,
                        canonical_json,
                        max_bytes=max_upload_bytes,
                    )

            config = _build_config(
                params=params,
                input_path=chunks_json,
                allowed_root=allowed_root,
                canonical_json=canonical_json,
            )
            result = await run_in_threadpool(ingest_chunks, config)

            result["uploaded_file"] = uploaded_name
            if is_zip:
                result["input_file"] = (
                    f"{uploaded_name}!/{chunks_json.relative_to(extracted_root).as_posix()}"
                )
                returned_canonical = result.get("canonical_file")
                if returned_canonical is not None:
                    returned_path = Path(returned_canonical)
                    try:
                        returned_relative = returned_path.relative_to(extracted_root)
                    except ValueError:
                        result["canonical_file"] = returned_canonical
                    else:
                        result["canonical_file"] = (
                            f"{uploaded_name}!/{returned_relative.as_posix()}"
                        )
            else:
                result["input_file"] = uploaded_name
                if result.get("canonical_file") is not None:
                    result["canonical_file"] = (
                        Path(canonical_file.filename).name
                        if canonical_file is not None and canonical_file.filename
                        else "canonical_document.json"
                    )
            return result
    except (ValueError, ValidationError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OpenSearchIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected ingestion failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected ingestion failure",
        ) from exc
