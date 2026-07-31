import logging
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.backend_callback import BackendCallbackClient
from app.config import get_settings
from app.jobs import JobManager
from app.models import (
    BackendManagedPathProcessRequest,
    JobAcceptedResponse,
    JobStatusResponse,
    PathProcessRequest,
    ProcessResponse,
)
from app.pipeline import AgentPipeline
from app.utils import (
    join_url,
    parse_output_directories,
    resolve_input_pdf,
    resolve_output_directory,
    safe_filename,
    safe_output_folder,
    save_upload_to_temp,
    sha256_file,
    validate_output_folder,
)

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
_DOCUMENT_ID_RE = re.compile(r"^[a-f0-9]{64}$")


def _allowed_input_roots() -> tuple[Path, ...]:
    return parse_output_directories(settings.allowed_input_directories)


def _allowed_output_roots() -> tuple[Path, ...]:
    return (
        settings.output_dir.expanduser().resolve(),
        *parse_output_directories(settings.allowed_output_directories),
    )


def _normalise_output_folder(output_folder: str | None) -> str | None:
    if output_folder is None:
        return None
    try:
        return safe_output_folder(output_folder)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


async def _save_pdf_upload(file: UploadFile) -> tuple[Path, str, int]:
    try:
        return await save_upload_to_temp(
            file,
            max_bytes=settings.max_upload_size_bytes,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if "exceeds" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc


def _resolve_selected_output_directory(output_directory: str | None) -> Path | None:
    if output_directory is None:
        return None
    try:
        return resolve_output_directory(
            output_directory,
            allowed_roots=_allowed_output_roots(),
            require_absolute=True,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


def _build_process_response(result: dict[str, Any]) -> ProcessResponse:
    canonical = result["canonical"]
    document_id = result["document_id"]
    package_name = result["package_name"]
    output_root = result["output_directory"]
    package_dir = result["package_dir"]
    canonical_path = result["canonical_path"]
    zip_path = result["zip_path"]
    quality = canonical.get("quality") or {}
    warnings = canonical.get("warnings") or []
    response_status = "completed" if quality.get("status") == "green" else "completed_with_warnings"

    is_default_output_root = output_root == settings.output_dir.expanduser().resolve()
    package_url = (
        join_url(settings.packages_url_prefix, f"{package_name}/")
        if is_default_output_root
        else None
    )
    canonical_url = (
        join_url(
            settings.packages_url_prefix,
            f"{package_name}/canonical_document.json",
        )
        if is_default_output_root
        else None
    )
    zip_url = (
        join_url(settings.packages_url_prefix, f"{package_name}.zip")
        if is_default_output_root and zip_path
        else None
    )

    return ProcessResponse(
        status=response_status,
        document_id=document_id,
        package_name=package_name,
        output_directory=str(output_root),
        output_folder=package_name,
        package_directory=str(package_dir),
        canonical_json=str(canonical_path),
        zip_file=str(zip_path) if zip_path else None,
        urls={
            "assets_base": package_url,
            "canonical_json": canonical_url,
            "zip": zip_url,
            "download": (
                f"/v1/packages/{package_name}/download"
                if is_default_output_root and zip_path
                else None
            ),
        },
        quality=quality,
        counts=canonical.get("counts") or {},
        warnings=warnings,
        processing=result.get("processing") or {},
    )


async def _run_pipeline(
    request: Request,
    *,
    pdf_path: Path,
    filename: str,
    use_llm: bool,
    output_folder: str | None,
    output_directory: Path | None,
    overwrite: bool | None,
) -> ProcessResponse:
    try:
        result = await request.app.state.pipeline.process(
            pdf_path=pdf_path,
            filename=filename,
            use_llm=use_llm,
            output_folder=output_folder,
            output_directory=output_directory,
            overwrite=overwrite,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Canonical PDF processing failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return _build_process_response(result)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    app.state.pipeline = AgentPipeline(settings)
    app.state.jobs = JobManager()
    app.state.backend_callback = BackendCallbackClient(settings)
    yield
    await app.state.jobs.close()
    await app.state.backend_callback.close()
    await app.state.pipeline.close()


settings.output_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Calls the PDF extraction tools service, aligns Docling and GROBID, performs "
        "deterministic quality checks, optionally invokes a bounded Llama vision fallback, "
        "and writes a canonical document package. PDFs can be uploaded or read from "
        "allow-listed directories mounted into the container."
    ),
    lifespan=lifespan,
)
app.mount(
    settings.packages_url_prefix,
    StaticFiles(directory=str(settings.output_dir)),
    name="packages",
)


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready(request: Request) -> dict[str, Any]:
    result = await request.app.state.pipeline.ready()
    if not result["ready"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", **result},
        )
    return {"status": "ready", **result}


@app.get("/v1/runtime")
async def runtime(request: Request) -> dict[str, Any]:
    readiness = await request.app.state.pipeline.ready()
    return {
        "app": {"name": settings.app_name, "version": settings.app_version},
        "tools": {
            "base_url": settings.tools_base_url,
            "ready": readiness["tools_ready"],
        },
        "llm": {
            "enabled": settings.llm_enabled,
            "provider": settings.llm_provider,
            "base_url": settings.ollama_base_url if settings.llm_enabled else None,
            "model": settings.ollama_model if settings.llm_enabled else None,
            "alive": readiness["llm_alive"],
        },
        "path_api": {
            "enabled": settings.path_api_enabled,
            "allowed_input_directories": [str(path) for path in _allowed_input_roots()],
            "allowed_output_directories": [str(path) for path in _allowed_output_roots()],
        },
        "output_dir": str(settings.output_dir),
    }


@app.post("/v1/process", response_model=ProcessResponse)
async def process_pdf(
    request: Request,
    file: Annotated[UploadFile, File(description="Scientific article PDF")],
    use_llm: Annotated[bool, Form()] = False,
    output_folder: Annotated[str | None, Form()] = None,
    output_directory: Annotated[str | None, Form()] = None,
    overwrite: Annotated[bool | None, Form()] = None,
) -> ProcessResponse:
    """Process an uploaded PDF."""

    filename = safe_filename(file.filename)
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF uploads are supported.",
        )

    normalized_output_folder = _normalise_output_folder(output_folder)
    resolved_output_directory = _resolve_selected_output_directory(output_directory)

    temp_path: Path | None = None
    try:
        temp_path, _sha256, _size = await _save_pdf_upload(file)
        return await _run_pipeline(
            request,
            pdf_path=temp_path,
            filename=filename,
            use_llm=use_llm,
            output_folder=normalized_output_folder,
            output_directory=resolved_output_directory,
            overwrite=overwrite,
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@app.post(
    "/v1/process-async",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_pdf_async(
    request: Request,
    file: Annotated[UploadFile, File(description="Scientific article PDF")],
    use_llm: Annotated[bool, Form()] = False,
    output_folder: Annotated[str | None, Form()] = None,
    output_directory: Annotated[str | None, Form()] = None,
    overwrite: Annotated[bool | None, Form()] = None,
) -> JobAcceptedResponse:
    """Queue a PDF and return immediately instead of holding a long HTTP request open."""

    filename = safe_filename(file.filename)
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF uploads are supported.",
        )

    normalized_output_folder = _normalise_output_folder(output_folder)
    resolved_output_directory = _resolve_selected_output_directory(output_directory)
    temp_path, sha256, _size = await _save_pdf_upload(file)

    async def runner() -> ProcessResponse:
        result = await request.app.state.pipeline.process(
            pdf_path=temp_path,
            filename=filename,
            use_llm=use_llm,
            output_folder=normalized_output_folder,
            output_directory=resolved_output_directory,
            overwrite=overwrite,
        )
        return _build_process_response(result)

    def cleanup() -> None:
        temp_path.unlink(missing_ok=True)

    try:
        job = request.app.state.jobs.submit(
            filename=filename,
            document_id=sha256,
            runner=runner,
            cleanup=cleanup,
        )
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    status_url = str(request.url_for("get_job_status", job_id=job.job_id))
    return JobAcceptedResponse(
        job_id=job.job_id,
        document_id=job.document_id,
        filename=job.filename,
        status_url=status_url,
    )


@app.get("/v1/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(request: Request, job_id: str) -> JobStatusResponse:
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    status_url = str(request.url_for("get_job_status", job_id=job.job_id))
    return JobStatusResponse.model_validate(job.as_dict(status_url=status_url))


@app.post(
    "/v1/process-path-async",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_pdf_from_path_async(
    request: Request,
    payload: BackendManagedPathProcessRequest,
) -> JobAcceptedResponse:
    """Queue a mounted PDF and report status to backend-managed Redis.

    The backend supplies a correlation ID. This agent keeps a local diagnostic
    record, but the DocuMind backend callback record is the shared source of
    truth, allowing this endpoint to be safely load-balanced across replicas.
    """

    if not settings.path_api_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path-based processing is disabled by PATH_API_ENABLED.",
        )

    callback = request.app.state.backend_callback
    if not callback.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Backend callback is not configured. Set "
                "BACKEND_CALLBACK_BASE_URL and BACKEND_CALLBACK_TOKEN."
            ),
        )

    try:
        input_path = resolve_input_pdf(
            payload.input_directory,
            payload.input_filename,
            allowed_roots=_allowed_input_roots(),
            max_bytes=settings.max_upload_size_bytes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    normalized_output_folder = _normalise_output_folder(payload.output_folder)
    resolved_output_directory = _resolve_selected_output_directory(payload.output_directory)
    document_id = sha256_file(input_path)
    agent_job_id = str(uuid.uuid4())

    async def runner() -> ProcessResponse:
        result = await request.app.state.pipeline.process(
            pdf_path=input_path,
            filename=input_path.name,
            use_llm=payload.use_llm,
            output_folder=normalized_output_folder,
            output_directory=resolved_output_directory,
            overwrite=payload.overwrite,
        )
        return _build_process_response(result)

    async def report_status(record) -> None:
        await callback.report_record(
            backend_job_id=payload.backend_job_id,
            record=record,
        )

    job = request.app.state.jobs.submit(
        job_id=agent_job_id,
        filename=input_path.name,
        document_id=document_id,
        runner=runner,
        on_status=report_status,
    )
    status_url = str(request.url_for("get_job_status", job_id=job.job_id))
    return JobAcceptedResponse(
        job_id=job.job_id,
        document_id=job.document_id,
        filename=job.filename,
        status_url=status_url,
    )


@app.post("/v1/process-path", response_model=ProcessResponse)
async def process_pdf_from_path(
    request: Request,
    payload: PathProcessRequest,
) -> ProcessResponse:
    """Process a PDF from mounted storage without uploading it through HTTP."""

    if not settings.path_api_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path-based processing is disabled by PATH_API_ENABLED.",
        )

    try:
        input_path = resolve_input_pdf(
            payload.input_directory,
            payload.input_filename,
            allowed_roots=_allowed_input_roots(),
            max_bytes=settings.max_upload_size_bytes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    normalized_output_folder = _normalise_output_folder(payload.output_folder)
    resolved_output_directory = _resolve_selected_output_directory(payload.output_directory)

    return await _run_pipeline(
        request,
        pdf_path=input_path,
        filename=input_path.name,
        use_llm=payload.use_llm,
        output_folder=normalized_output_folder,
        output_directory=resolved_output_directory,
        overwrite=payload.overwrite,
    )


@app.get("/v1/documents/{document_id}")
async def get_document(document_id: str) -> FileResponse:
    if not _DOCUMENT_ID_RE.fullmatch(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID.")
    path = settings.output_dir / document_id / "canonical_document.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document package not found.")
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.get("/v1/documents/{document_id}/download")
async def download_document(document_id: str) -> FileResponse:
    if not _DOCUMENT_ID_RE.fullmatch(document_id):
        raise HTTPException(status_code=400, detail="Invalid document ID.")
    path = settings.output_dir / f"{document_id}.zip"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document ZIP package not found.")
    return FileResponse(path, media_type="application/zip", filename=path.name)


@app.get("/v1/packages/{package_name}")
async def get_package(package_name: str) -> FileResponse:
    try:
        safe_name = validate_output_folder(package_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    path = settings.output_dir / safe_name / "canonical_document.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document package not found.")
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.get("/v1/packages/{package_name}/download")
async def download_package(package_name: str) -> FileResponse:
    try:
        safe_name = validate_output_folder(package_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    path = settings.output_dir / f"{safe_name}.zip"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document ZIP package not found.")
    return FileResponse(path, media_type="application/zip", filename=path.name)
