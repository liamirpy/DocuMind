import asyncio

from app.jobs import JobManager
from app.models import ProcessResponse


def _result() -> ProcessResponse:
    return ProcessResponse(
        status="completed",
        document_id="a" * 64,
        package_name="package",
        output_directory="/data/outputs",
        output_folder="package",
        package_directory="/data/outputs/package",
        canonical_json="/data/outputs/package/canonical_document.json",
    )


async def test_job_manager_completes_and_cleans_up() -> None:
    manager = JobManager()
    cleaned = False

    async def runner() -> ProcessResponse:
        await asyncio.sleep(0)
        return _result()

    def cleanup() -> None:
        nonlocal cleaned
        cleaned = True

    record = manager.submit(
        filename="article.pdf",
        document_id="a" * 64,
        runner=runner,
        cleanup=cleanup,
    )

    for _ in range(20):
        if record.status == "completed":
            break
        await asyncio.sleep(0)

    assert record.status == "completed"
    assert record.result is not None
    assert cleaned is True
    await manager.close()


async def test_job_manager_records_failure() -> None:
    manager = JobManager()

    async def runner() -> ProcessResponse:
        raise RuntimeError("extractor timed out")

    record = manager.submit(
        filename="article.pdf",
        document_id="b" * 64,
        runner=runner,
    )

    for _ in range(20):
        if record.status == "failed":
            break
        await asyncio.sleep(0)

    assert record.status == "failed"
    assert record.error == "extractor timed out"
    await manager.close()


async def test_job_manager_accepts_predefined_id_and_reports_status() -> None:
    manager = JobManager()
    statuses: list[str] = []

    async def runner() -> ProcessResponse:
        await asyncio.sleep(0)
        return _result()

    async def on_status(record) -> None:
        statuses.append(record.status)

    record = manager.submit(
        job_id="agent-job-123",
        filename="article.pdf",
        document_id="c" * 64,
        runner=runner,
        on_status=on_status,
    )

    for _ in range(20):
        if record.status == "completed":
            break
        await asyncio.sleep(0)

    assert record.job_id == "agent-job-123"
    assert statuses == ["running", "completed"]
    await manager.close()
