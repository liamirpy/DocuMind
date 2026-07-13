from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.utils import join_url


class ExtractorClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.tools_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.tools_timeout_seconds),
            verify=settings.tools_verify_tls,
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def is_ready(self) -> bool:
        try:
            response = await self._client.get(self.settings.tools_ready_path)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def extract(
        self,
        pdf_path: Path,
        *,
        filename: str,
    ) -> dict[str, Any]:
        data = {
            "include_docling_markdown": "true",
            "include_docling_json": "true",
            "include_grobid_tei": "true",
            "export_picture_images": "true",
            "export_table_images": "true",
            "grobid_consolidate_header": "0",
            "grobid_consolidate_citations": "0",
            "grobid_include_raw_citations": "true",
            "grobid_include_raw_affiliations": "true",
            "grobid_segment_sentences": "true",
        }
        with pdf_path.open("rb") as file_handle:
            files = {"file": (filename, file_handle, "application/pdf")}
            response = await self._client.post(
                self.settings.tools_extract_path,
                data=data,
                files=files,
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Extractor response is not a JSON object.")
        return payload

    async def download_asset(self, asset_url: str, destination: Path) -> None:
        url = asset_url
        if asset_url.startswith("/"):
            url = join_url(self.settings.tools_base_url, asset_url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        async with self._client.stream("GET", url) as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                async for chunk in response.aiter_bytes():
                    output.write(chunk)
