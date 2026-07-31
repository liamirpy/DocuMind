import asyncio
import logging
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.jobs import JobRecord

logger = logging.getLogger(__name__)


class BackendCallbackClient:
    """Report PaperMind job lifecycle events to the DocuMind backend.

    The backend Redis record is the shared source of truth. PaperMind replicas
    may still keep local records for diagnostics, but the backend never polls
    those local records, so requests can be distributed across replicas safely.
    """

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.backend_callback_base_url.rstrip("/")
        self._token = (
            settings.backend_callback_token.get_secret_value()
            if settings.backend_callback_token is not None
            else ""
        )
        self._maximum_retries = settings.backend_callback_max_retries
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.backend_callback_timeout_seconds)
        )

    @property
    def enabled(self) -> bool:
        return bool(self._base_url and self._token)

    async def close(self) -> None:
        await self._client.aclose()

    async def report_record(
        self,
        *,
        backend_job_id: str,
        record: JobRecord,
    ) -> bool:
        result: dict[str, Any] | None = None
        if record.result is not None:
            result = record.result.model_dump(mode="json")

        return await self.report(
            backend_job_id=backend_job_id,
            agent_job_id=record.job_id,
            status=record.status,
            stage=_stage_for_status(record.status),
            progress=_progress_for_status(record.status),
            result=result,
            error=record.error,
        )

    async def report(
        self,
        *,
        backend_job_id: str,
        agent_job_id: str,
        status: str,
        stage: str | None = None,
        progress: int = 0,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        if not self.enabled:
            logger.error(
                "Backend callback is not configured; cannot report job %s",
                backend_job_id,
            )
            return False

        url = (
            f"{self._base_url}/"
            f"{quote(backend_job_id, safe='')}"
            "/status"
        )
        payload = {
            "agent_job_id": agent_job_id,
            "status": status,
            "stage": stage,
            "progress": progress,
            "result": result,
            "error": error,
        }
        headers = {
            "X-PaperMind-Callback-Token": self._token,
        }

        for attempt in range(1, self._maximum_retries + 1):
            try:
                response = await self._client.post(
                    url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                return True
            except httpx.HTTPError:
                logger.exception(
                    "Backend callback failed for %s (attempt %s/%s)",
                    backend_job_id,
                    attempt,
                    self._maximum_retries,
                )
                if attempt < self._maximum_retries:
                    await asyncio.sleep(min(2**attempt, 10))

        return False


def _stage_for_status(status: str) -> str:
    return {
        "queued": "queued",
        "running": "processing",
        "completed": "finished",
        "failed": "failed",
    }.get(status, status)


def _progress_for_status(status: str) -> int:
    return {
        "queued": 0,
        "running": 10,
        "completed": 100,
        "failed": 100,
    }.get(status, 0)
