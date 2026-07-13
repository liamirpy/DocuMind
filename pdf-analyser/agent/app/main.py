import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models import ProcessResponse
from app.pipeline import AgentPipeline
from app.utils import (
    join_url,
    safe_filename,
    safe_output_folder,
    save_upload_to_temp,
    validate_output_folder,
)

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
_DOCUMENT_ID_RE = re.compile(r"^[a-f0-9]{64}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    app.state.pipeline = AgentPipeline(settings)
    yield
    await app.state.pipeline.close()


settings.output_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Calls the PDF extraction tools service, aligns Docling and GROBID, performs "
        "deterministic quality checks, optionally invokes a bounded Llama vision fallback, "
        "and writes a canonical document package."
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
        "output_dir": str(settings.output_dir),
    }


@app.post("/v1/process", response_model=ProcessResponse)
async def process_pdf(
    request: Request,
    file: Annotated[UploadFile, File(description="Scientific article PDF")],
    use_llm: Annotated[bool, Form()] = False,
    output_folder: Annotated[str | None, Form()] = None,
    overwrite: Annotated[bool | None, Form()] = None,
) -> ProcessResponse:
    filename = safe_filename(file.filename)
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF uploads are supported.",
        )

    normalized_output_folder: str | None = None
    if output_folder is not None:
        try:
            normalized_output_folder = safe_output_folder(output_folder)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    temp_path: Path | None = None
    try:
        temp_path, _sha256, _size = await save_upload_to_temp(
            file,
            max_bytes=settings.max_upload_size_bytes,
        )
        result = await request.app.state.pipeline.process(
            pdf_path=temp_path,
            filename=filename,
            use_llm=use_llm,
            output_folder=normalized_output_folder,
            overwrite=overwrite,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Canonical PDF processing failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    canonical = result["canonical"]
    document_id = result["document_id"]
    package_name = result["package_name"]
    package_dir = result["package_dir"]
    canonical_path = result["canonical_path"]
    zip_path = result["zip_path"]
    quality = canonical.get("quality") or {}
    warnings = canonical.get("warnings") or []
    response_status = "completed" if quality.get("status") == "green" else "completed_with_warnings"

    package_url = join_url(settings.packages_url_prefix, f"{package_name}/")
    canonical_url = join_url(
        settings.packages_url_prefix,
        f"{package_name}/canonical_document.json",
    )
    zip_url = join_url(settings.packages_url_prefix, f"{package_name}.zip") if zip_path else None

    return ProcessResponse(
        status=response_status,
        document_id=document_id,
        package_name=package_name,
        output_folder=package_name,
        package_directory=str(package_dir),
        canonical_json=str(canonical_path),
        zip_file=str(zip_path) if zip_path else None,
        urls={
            "assets_base": package_url,
            "canonical_json": canonical_url,
            "zip": zip_url,
            "download": f"/v1/packages/{package_name}/download" if zip_path else None,
        },
        quality=quality,
        counts=canonical.get("counts") or {},
        warnings=warnings,
        processing=result.get("processing") or {},
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
