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
            timeout=httpx.Timeout(
                connect=30.0,
                read=settings.tools_timeout_seconds,
                write=settings.tools_timeout_seconds,
                pool=60.0,
            ),
            verify=settings.tools_verify_tls,
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def is_ready(self) -> bool:
        try:
            response = await self._client.get(self.settings.tools_ready_path, timeout=20.0)
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
        try:
            with pdf_path.open("rb") as file_handle:
                files = {"file": (filename, file_handle, "application/pdf")}
                response = await self._client.post(
                    self.settings.tools_extract_path,
                    data=data,
                    files=files,
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                "The extractor exceeded TOOLS_TIMEOUT_SECONDS "
                f"({self.settings.tools_timeout_seconds:g}s). Keep this value above the "
                "Docling/GROBID timeout plus export overhead."
            ) from exc
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail", exc.response.text)
            except ValueError:
                detail = exc.response.text
            detail_text = str(detail).strip()[:2000]
            raise RuntimeError(
                f"Extractor returned HTTP {exc.response.status_code}: {detail_text}"
            ) from exc
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
