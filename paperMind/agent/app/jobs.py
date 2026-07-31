import asyncio
import inspect
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from app.models import ProcessResponse

logger = logging.getLogger(__name__)
JobStatus = Literal["queued", "running", "completed", "failed"]
CleanupCallback = Callable[[], Awaitable[None] | None]
JobRunner = Callable[[], Awaitable[ProcessResponse]]
StatusCallback = Callable[["JobRecord"], Awaitable[None] | None]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class JobRecord:
    job_id: str
    filename: str
    document_id: str
    status: JobStatus = "queued"
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    result: ProcessResponse | None = None
    error: str | None = None

    def as_dict(self, *, status_url: str) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "status": self.status,
            "status_url": status_url,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    """Run long PDF jobs outside the HTTP request lifetime.

    Local records remain available for diagnostics. Backend-managed path jobs
    additionally report every lifecycle transition to the backend, whose Redis
    record is the distributed source of truth used by DocuMind workers.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def submit(
        self,
        *,
        filename: str,
        document_id: str,
        runner: JobRunner,
        cleanup: CleanupCallback | None = None,
        job_id: str | None = None,
        on_status: StatusCallback | None = None,
    ) -> JobRecord:
        selected_job_id = job_id or str(uuid.uuid4())
        if selected_job_id in self._jobs:
            raise ValueError(f"Job already exists: {selected_job_id}")

        record = JobRecord(
            job_id=selected_job_id,
            filename=filename,
            document_id=document_id,
        )
        self._jobs[selected_job_id] = record
        task = asyncio.create_task(
            self._run(
                record=record,
                runner=runner,
                cleanup=cleanup,
                on_status=on_status,
            ),
            name=f"pdf-job-{selected_job_id}",
        )
        self._tasks[selected_job_id] = task
        task.add_done_callback(
            lambda _task, key=selected_job_id: self._tasks.pop(key, None)
        )
        return record

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    async def close(self) -> None:
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _notify(
        self,
        record: JobRecord,
        on_status: StatusCallback | None,
    ) -> None:
        if on_status is None:
            return
        try:
            result = on_status(record)
            if inspect.isawaitable(result):
                await result
        except Exception:
            # Processing must not crash solely because a status callback had a
            # transient transport failure. The callback client performs its own
            # retries and logs the final failure.
            logger.exception("Status callback failed for PDF job %s", record.job_id)

    async def _run(
        self,
        *,
        record: JobRecord,
        runner: JobRunner,
        cleanup: CleanupCallback | None,
        on_status: StatusCallback | None,
    ) -> None:
        record.status = "running"
        record.started_at = _utc_now()
        await self._notify(record, on_status)
        try:
            record.result = await runner()
            record.status = "completed"
        except asyncio.CancelledError:
            record.status = "failed"
            record.error = "Processing was interrupted because the service stopped."
            raise
        except Exception as exc:
            logger.exception("Background PDF job %s failed", record.job_id)
            record.status = "failed"
            record.error = str(exc) or exc.__class__.__name__
        finally:
            record.finished_at = _utc_now()
            await self._notify(record, on_status)
            if cleanup is not None:
                try:
                    cleanup_result = cleanup()
                    if inspect.isawaitable(cleanup_result):
                        await cleanup_result
                except Exception:
                    logger.exception("Cleanup failed for PDF job %s", record.job_id)
