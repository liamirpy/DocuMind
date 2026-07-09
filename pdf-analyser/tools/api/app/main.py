import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models import ExtractionResponse, ParserResult
from app.services.docling_service import DoclingService
from app.services.grobid_service import GrobidService
from app.services.merge_service import build_merged_preview
from app.utils import safe_filename, save_upload_to_temp

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.docling = DoclingService(settings)
    app.state.grobid = GrobidService(settings)

    if settings.docling_preload_on_startup:
        try:
            await app.state.docling.initialize()
        except Exception:
            logger.exception("Docling initialization failed during startup.")

    yield
    await app.state.grobid.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Upload a scientific PDF and receive Docling JSON/Markdown, persisted figure/table "
        "assets, GROBID TEI, parsed views, and a conservative merged preview."
    ),
    lifespan=lifespan,
)

if settings.serve_assets:
    settings.assets_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.assets_url_prefix,
        StaticFiles(directory=str(settings.assets_dir)),
        name="assets",
    )


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready(request: Request) -> dict[str, Any]:
    grobid_alive = await request.app.state.grobid.is_alive()
    docling_ready = request.app.state.docling.is_initialized

    if not grobid_alive or not docling_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "grobid": grobid_alive,
                "docling": docling_ready,
                "docling_error": request.app.state.docling.initialization_error,
            },
        )

    return {"status": "ready", "grobid": True, "docling": True}


@app.get("/v1/runtime")
async def runtime(request: Request) -> dict[str, Any]:
    return {
        "app": {"name": settings.app_name, "version": settings.app_version},
        "docling": await request.app.state.docling.runtime_info(),
        "grobid": {
            "alive": await request.app.state.grobid.is_alive(),
            "version": await request.app.state.grobid.version(),
        },
    }


@app.post("/v1/extract", response_model=ExtractionResponse)
async def extract_pdf(
    request: Request,
    file: Annotated[UploadFile, File(description="Scientific article PDF")],
    include_docling_markdown: Annotated[bool, Form()] = True,
    include_docling_json: Annotated[bool, Form()] = True,
    include_grobid_tei: Annotated[bool, Form()] = True,
    export_picture_images: Annotated[bool, Form()] = settings.docling_export_pictures,
    export_table_images: Annotated[bool, Form()] = settings.docling_export_tables,
    grobid_consolidate_header: Annotated[str, Form(pattern="^[0-3]$")] = "0",
    grobid_consolidate_citations: Annotated[str, Form(pattern="^[0-2]$")] = "0",
    grobid_include_raw_citations: Annotated[bool, Form()] = True,
    grobid_include_raw_affiliations: Annotated[bool, Form()] = True,
    grobid_segment_sentences: Annotated[bool, Form()] = True,
) -> ExtractionResponse:
    request_id = str(uuid.uuid4())
    filename = safe_filename(file.filename)
    started = time.perf_counter()
    temp_path: Path | None = None

    try:
        temp_path, sha256, size_bytes = await save_upload_to_temp(
            file,
            max_bytes=settings.max_upload_size_bytes,
        )

        docling_started = time.perf_counter()
        grobid_started = time.perf_counter()
        docling_task = asyncio.create_task(
            request.app.state.docling.extract(
                temp_path,
                document_id=sha256,
                include_markdown=include_docling_markdown,
                export_pictures=export_picture_images,
                export_tables=export_table_images,
            )
        )
        grobid_task = asyncio.create_task(
            request.app.state.grobid.extract(
                temp_path,
                filename=filename,
                consolidate_header=grobid_consolidate_header,
                consolidate_citations=grobid_consolidate_citations,
                include_raw_citations=grobid_include_raw_citations,
                include_raw_affiliations=grobid_include_raw_affiliations,
                segment_sentences=grobid_segment_sentences,
                include_tei_xml=include_grobid_tei,
            )
        )

        docling_outcome, grobid_outcome = await asyncio.gather(
            docling_task,
            grobid_task,
            return_exceptions=True,
        )

        warnings: list[str] = []
        docling_data: dict[str, Any] | None = None
        grobid_data: dict[str, Any] | None = None

        if isinstance(docling_outcome, Exception):
            logger.error(
                "Docling failed for request %s: %s",
                request_id,
                docling_outcome,
                exc_info=(
                    type(docling_outcome),
                    docling_outcome,
                    docling_outcome.__traceback__,
                ),
            )
            docling = ParserResult(
                status="failed",
                duration_seconds=round(time.perf_counter() - docling_started, 3),
                error=str(docling_outcome),
            )
            warnings.append("Docling extraction failed; GROBID output may still be available.")
        else:
            docling_data = docling_outcome
            raw = docling_data.get("raw")
            if raw is not None and not include_docling_json:
                raw.pop("document_json", None)
            docling = ParserResult(
                status="completed",
                version=docling_data.get("version"),
                duration_seconds=docling_data["duration_seconds"],
                stats=docling_data.get("stats", {}),
                raw=raw,
                parsed=docling_data.get("parsed"),
            )
            if docling_data.get("parsed", {}).get("quality_flags"):
                warnings.append(
                    "Docling detected one or more tables with an empty row/column/cell structure."
                )

        if isinstance(grobid_outcome, Exception):
            logger.error(
                "GROBID failed for request %s: %s",
                request_id,
                grobid_outcome,
                exc_info=(
                    type(grobid_outcome),
                    grobid_outcome,
                    grobid_outcome.__traceback__,
                ),
            )
            grobid = ParserResult(
                status="failed",
                duration_seconds=round(time.perf_counter() - grobid_started, 3),
                error=str(grobid_outcome),
            )
            warnings.append("GROBID extraction failed; Docling output may still be available.")
        else:
            grobid_data = grobid_outcome
            grobid = ParserResult(
                status="completed",
                version=grobid_data.get("version"),
                duration_seconds=grobid_data["duration_seconds"],
                stats=grobid_data.get("stats", {}),
                raw=grobid_data.get("raw"),
                parsed=grobid_data.get("parsed"),
            )

        completed_count = int(docling.status == "completed") + int(grobid.status == "completed")
        overall_status = (
            "completed" if completed_count == 2 else "partial" if completed_count == 1 else "failed"
        )

        if overall_status == "failed":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "request_id": request_id,
                    "message": "Both extractors failed.",
                    "docling_error": docling.error,
                    "grobid_error": grobid.error,
                },
            )

        return ExtractionResponse(
            request_id=request_id,
            status=overall_status,
            document={
                "filename": filename,
                "content_type": file.content_type or "application/pdf",
                "size_bytes": size_bytes,
                "sha256": sha256,
                "asset_namespace": sha256,
            },
            options={
                "include_docling_markdown": include_docling_markdown,
                "include_docling_json": include_docling_json,
                "include_grobid_tei": include_grobid_tei,
                "export_picture_images": export_picture_images,
                "export_table_images": export_table_images,
                "grobid_consolidate_header": grobid_consolidate_header,
                "grobid_consolidate_citations": grobid_consolidate_citations,
                "grobid_include_raw_citations": grobid_include_raw_citations,
                "grobid_include_raw_affiliations": grobid_include_raw_affiliations,
                "grobid_segment_sentences": grobid_segment_sentences,
            },
            processing={
                "total_duration_seconds": round(time.perf_counter() - started, 3),
                "parallel_extractors": True,
            },
            docling=docling,
            grobid=grobid,
            merged=build_merged_preview(
                docling_result=docling_data,
                grobid_result=grobid_data,
            ),
            warnings=warnings,
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
