from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.jobs import JobManager, JobNotFoundError, OutputAlreadyInUseError
from app.api.models import (
    HealthResponse,
    IndexJobRequest,
    JobListResponse,
    JobRecord,
    QueryEmbeddingRequest,
    QueryEmbeddingResponse,
)
from app.api.paths import PathResolutionError, resolve_mounted_directory
from app.api.runtime import IndexerRuntime
from app.api.security import require_api_key
from app.api.settings import ApiSettings, get_settings
from app.api.storage import verify_readable_directory, verify_writable_directory

logger = logging.getLogger(__name__)


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.api_log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Fail fast during container startup instead of accepting a job and
        # discovering a volume-permission problem several seconds later.
        verify_readable_directory(
            settings.indexer_input_root,
            label="Indexer input root",
        )
        verify_writable_directory(
            settings.indexer_output_root,
            label="Indexer output root",
        )
        verify_writable_directory(
            settings.job_state_root,
            label="Job-state directory",
        )
        if (
            settings.embedding_enabled
            and settings.embedding_provider == "sentence_transformers"
            and settings.embedding_cache_root is not None
        ):
            verify_writable_directory(
                settings.embedding_cache_root,
                label="Embedding model cache",
            )

        runtime = IndexerRuntime(settings)
        jobs = JobManager(settings=settings, runtime=runtime)
        app.state.settings = settings
        app.state.runtime = runtime
        app.state.jobs = jobs
        if settings.model_preload:
            logger.info("Preloading configured embedding model")
            runtime.preload()
        yield
        jobs.shutdown()

    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=(
            "Chunk and embed an existing DocuMind PDF output directory. "
            "Input and output paths are restricted to the roots mounted by Docker Compose."
        ),
        lifespan=lifespan,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-API-Key"],
        )

    protected = [Depends(require_api_key(settings))]

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def health_live() -> HealthResponse:
        return HealthResponse(status="ok", version=settings.api_version)

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def health_ready(request: Request) -> HealthResponse:
        input_ok = settings.indexer_input_root.is_dir()
        output_ok = settings.indexer_output_root.is_dir()
        jobs_ok = settings.job_state_root.is_dir()
        cache_root = settings.embedding_cache_root
        cache_required = (
            settings.embedding_enabled
            and settings.embedding_provider == "sentence_transformers"
            and cache_root is not None
        )
        cache_ok = not cache_required or cache_root.is_dir()
        status_value = "ready" if input_ok and output_ok and jobs_ok and cache_ok else "not_ready"
        if status_value != "ready":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Configured input, output, job-state, or model-cache storage is unavailable",
            )
        runtime: IndexerRuntime = request.app.state.runtime
        return HealthResponse(
            status=status_value,
            version=settings.api_version,
            details={
                "input_root": str(settings.indexer_input_root),
                "output_root": str(settings.indexer_output_root),
                "job_state_root": str(settings.job_state_root),
                "embedding_cache_root": (
                    str(settings.embedding_cache_root)
                    if settings.embedding_cache_root is not None
                    else None
                ),
                "storage_ready": True,
                "embedding_enabled": runtime.config.embedding.enabled,
                "embedding_provider": runtime.config.embedding.provider,
                "embedding_model": runtime.config.embedding.model_name,
                "model_loaded": runtime._provider is not None,  # noqa: SLF001
                "max_concurrent_jobs": settings.max_concurrent_jobs,
            },
        )

    @app.post(
        "/v1/indexing/jobs",
        response_model=JobRecord,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["indexing"],
        dependencies=protected,
    )
    async def create_indexing_job(request_body: IndexJobRequest, request: Request) -> JobRecord:
        try:
            input_directory = resolve_mounted_directory(
                request_body.input_directory,
                container_root=settings.indexer_input_root,
                host_root=settings.documind_input_root_host,
                must_exist=True,
                label="input_directory",
            )
            output_directory = resolve_mounted_directory(
                request_body.output_directory,
                container_root=settings.indexer_output_root,
                host_root=settings.documind_output_root_host,
                must_exist=False,
                label="output_directory",
            )
            jobs: JobManager = request.app.state.jobs
            return jobs.create(
                request=request_body,
                input_directory=input_directory,
                output_directory=output_directory,
            )
        except (PathResolutionError, FileNotFoundError, NotADirectoryError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        except (FileExistsError, OutputAlreadyInUseError) as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.get(
        "/v1/indexing/jobs/{job_id}",
        response_model=JobRecord,
        tags=["indexing"],
        dependencies=protected,
    )
    async def get_indexing_job(job_id: str, request: Request) -> JobRecord:
        jobs: JobManager = request.app.state.jobs
        try:
            return jobs.get(job_id)
        except JobNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            ) from exc

    @app.get(
        "/v1/indexing/jobs",
        response_model=JobListResponse,
        tags=["indexing"],
        dependencies=protected,
    )
    async def list_indexing_jobs(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> JobListResponse:
        jobs: JobManager = request.app.state.jobs
        return JobListResponse(jobs=jobs.list(limit=limit))

    @app.post(
        "/v1/embeddings/query",
        response_model=QueryEmbeddingResponse,
        tags=["embeddings"],
        dependencies=protected,
    )
    async def create_query_embedding(
        request_body: QueryEmbeddingRequest,
        request: Request,
    ) -> QueryEmbeddingResponse:
        runtime: IndexerRuntime = request.app.state.runtime
        try:
            output = await run_in_threadpool(runtime.embed_query, request_body.query_text)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        return QueryEmbeddingResponse.model_validate(output.model_dump(mode="json"))

    return app


app = create_app()
