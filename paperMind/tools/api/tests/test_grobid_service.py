from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.services.grobid_service import GrobidService


@pytest.mark.asyncio
async def test_is_alive_uses_dedicated_plain_text_endpoint() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="true", headers={"content-type": "text/plain"})

    settings = Settings(_env_file=None, grobid_base_url="http://grobid:8070")
    service = GrobidService(settings)
    await service._client.aclose()  # noqa: SLF001
    service._client = httpx.AsyncClient(  # noqa: SLF001
        base_url=settings.grobid_base_url,
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )

    try:
        assert await service.is_alive() is True
    finally:
        await service.close()

    assert seen[0].url.path == "/api/isalive"
    assert seen[0].headers["accept"] == "text/plain"


@pytest.mark.asyncio
async def test_fulltext_requests_xml(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="<TEI xmlns='http://www.tei-c.org/ns/1.0'/>")

    settings = Settings(
        _env_file=None,
        grobid_base_url="http://grobid:8070",
        grobid_max_retries=1,
    )
    service = GrobidService(settings)
    await service._client.aclose()  # noqa: SLF001
    service._client = httpx.AsyncClient(  # noqa: SLF001
        base_url=settings.grobid_base_url,
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )

    try:
        result = await service._process_fulltext(  # noqa: SLF001
            pdf,
            filename="sample.pdf",
            consolidate_header="0",
            consolidate_citations="0",
            include_raw_citations=False,
            include_raw_affiliations=False,
            segment_sentences=False,
        )
    finally:
        await service.close()

    assert result.startswith("<TEI")
    assert seen[0].url.path == "/api/processFulltextDocument"
    assert seen[0].headers["accept"] == "application/xml"
