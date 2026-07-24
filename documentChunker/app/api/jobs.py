from __future__ import annotations

import json
import logging
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from app.api.models import (
    IndexJobRequest,
    JobRecord,
    JobResultSummary,
    JobStage,
    JobStatus,
)
from app.api.paths import public_output_file
from app.api.runtime import IndexerRuntime
from app.api.settings import ApiSettings

logger = logging.getLogger(__name__)


class OutputAlreadyInUseError(RuntimeError):
    pass


class JobNotFoundError(KeyError):
    pass


class JobManager:
    """Thread-backed job queue with lightweight JSON status persistence."""

    def __init__(self, *, settings: ApiSettings, runtime: IndexerRuntime) -> None:
        self.settings = settings
        self.runtime = runtime
        self._executor = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_jobs,
            thread_name_prefix="indexer-job",
        )
        self._lock = threading.RLock()
        self._jobs: dict[str, JobRecord] = {}
        self._active_outputs: set[str] = set()
        self.settings.job_state_root.mkdir(parents=True, exist_ok=True)
        self._load_existing_jobs()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def create(
        self,
        *,
        request: IndexJobRequest,
        input_directory: Path,
        output_directory: Path,
    ) -> JobRecord:
        output_file = output_directory / request.output_filename
        output_key = str(output_file.resolve(strict=False))

        with self._lock:
            if output_key in self._active_outputs:
                raise OutputAlreadyInUseError(
                    f"Another active job is already writing to {output_file}"
                )
            if output_file.exists() and not request.overwrite:
                raise FileExistsError(
                    f"Output file already exists: {output_file}. Set overwrite=true to replace it."
                )

            now = datetime.now(UTC)
            job = JobRecord(
                job_id=str(uuid.uuid4()),
                status=JobStatus.QUEUED,
                stage=JobStage.QUEUED,
                user_id=request.resolved_user_id,
                document_id=request.document_id,
                input_directory=request.input_directory,
                output_directory=request.output_directory,
                output_filename=request.output_filename,
                skip_embedding=request.skip_embedding,
                overwrite=request.overwrite,
                created_at=now,
            )
            self._jobs[job.job_id] = job
            self._active_outputs.add(output_key)
            try:
                self._persist(job)
                self._trim_history()
            except Exception:
                # Do not leave a ghost job or an output lock behind when
                # persistence fails before the background task is submitted.
                self._jobs.pop(job.job_id, None)
                self._active_outputs.discard(output_key)
                raise

        self._executor.submit(
            self._execute,
            job.job_id,
            input_directory,
            output_file,
            output_key,
        )
        return job

    def get(self, job_id: str) -> JobRecord:
        with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError as exc:
                raise JobNotFoundError(job_id) from exc

    def list(self, *, limit: int = 100) -> list[JobRecord]:
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )
            return jobs[:limit]

    def _execute(
        self,
        job_id: str,
        input_directory: Path,
        output_file: Path,
        output_key: str,
    ) -> None:
        self._update(
            job_id,
            status=JobStatus.RUNNING,
            stage=JobStage.VALIDATING_INPUT,
            started_at=datetime.now(UTC),
        )
        try:
            job = self.get(job_id)

            def stage_callback(stage: str) -> None:
                self._update(job_id, stage=JobStage(stage))

            output = self.runtime.process(
                user_id=job.user_id,
                document_id=job.document_id,
                input_directory=input_directory,
                output_file=output_file,
                skip_embedding=job.skip_embedding,
                stage_callback=stage_callback,
            )
            summary = JobResultSummary(
                output_file=public_output_file(
                    requested_output_directory=job.output_directory,
                    output_filename=job.output_filename,
                ),
                source_document_id=output.source_document_id,
                total_chunks=output.counts.total,
                parent_chunks=output.counts.parent,
                child_chunks=output.counts.child,
                standalone_chunks=output.counts.standalone,
                table_chunks=output.counts.table,
                figure_chunks=output.counts.figure,
                formula_chunks=output.counts.formula,
                references=output.counts.references,
                embedding_enabled=output.embedding.enabled,
                embedded_chunks=output.embedding.embedded_chunk_count,
                skipped_chunks=output.embedding.skipped_chunk_count,
                embedding_model=output.embedding.model,
                embedding_dimensions=output.embedding.dimensions,
            )
            self._update(
                job_id,
                status=JobStatus.SUCCEEDED,
                stage=JobStage.COMPLETED,
                finished_at=datetime.now(UTC),
                result=summary,
            )
        except Exception as exc:  # noqa: BLE001 - job boundary must capture failures
            logger.error("Indexer job %s failed: %s", job_id, exc)
            logger.debug("Indexer job traceback:\n%s", traceback.format_exc())
            self._update(
                job_id,
                status=JobStatus.FAILED,
                stage=JobStage.FAILED,
                finished_at=datetime.now(UTC),
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        finally:
            with self._lock:
                self._active_outputs.discard(output_key)

    def _update(self, job_id: str, **changes: object) -> JobRecord:
        with self._lock:
            current = self._jobs[job_id]
            updated = current.model_copy(update=changes)
            self._jobs[job_id] = updated
            self._persist(updated)
            return updated

    def _state_file(self, job_id: str) -> Path:
        return self.settings.job_state_root / f"{job_id}.json"

    def _persist(self, job: JobRecord) -> None:
        path = self._state_file(job.job_id)

        # The output directory is a bind mount in Docker. The host may remove
        # or recreate the hidden job-state directory while the API is running,
        # so ensure it exists on every write rather than only at startup.
        path.parent.mkdir(parents=True, exist_ok=True)

        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(job.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _load_existing_jobs(self) -> None:
        for path in sorted(self.settings.job_state_root.glob("*.json")):
            try:
                job = JobRecord.model_validate_json(path.read_bytes())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Ignoring invalid job state file %s: %s", path, exc)
                continue
            if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                job = job.model_copy(
                    update={
                        "status": JobStatus.FAILED,
                        "stage": JobStage.FAILED,
                        "finished_at": datetime.now(UTC),
                        "error_type": "InterruptedJob",
                        "error_message": "The API process restarted before this job completed.",
                    }
                )
                self._persist(job)
            self._jobs[job.job_id] = job
        self._trim_history()

    def _trim_history(self) -> None:
        if len(self._jobs) <= self.settings.job_history_limit:
            return
        completed = sorted(
            (
                job
                for job in self._jobs.values()
                if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED}
            ),
            key=lambda item: item.created_at,
        )
        remove_count = len(self._jobs) - self.settings.job_history_limit
        for job in completed[:remove_count]:
            self._jobs.pop(job.job_id, None)
            self._state_file(job.job_id).unlink(missing_ok=True)
