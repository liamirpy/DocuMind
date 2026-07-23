import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.parsers.tei import parse_tei

logger = logging.getLogger(__name__)


class GrobidServiceError(RuntimeError):
    """Raised when GROBID processing fails."""


class GrobidService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.grobid_base_url,
            timeout=httpx.Timeout(settings.grobid_timeout_seconds),
            # Internal Compose traffic must not be redirected through host proxy
            # variables. Content negotiation is set per endpoint below.
            trust_env=False,
        )
        self._version: str | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def is_alive(self) -> bool:
        """Return True only when GROBID's dedicated liveness endpoint says true."""

        try:
            response = await self._client.get(
                "/api/isalive",
                timeout=10.0,
                headers={"Accept": "text/plain"},
            )
            response.raise_for_status()
            alive = response.text.strip().lower() == "true"
            if not alive:
                logger.warning(
                    "Unexpected GROBID /api/isalive response: %r",
                    response.text,
                )
            return alive
        except httpx.HTTPError as exc:
            logger.warning(
                "GROBID health check failed. base_url=%s error=%r",
                self.settings.grobid_base_url,
                exc,
            )
            return False

    async def version(self) -> str | None:
        """Return version metadata without using it as a liveness decision."""

        if self._version is not None:
            return self._version
        try:
            response = await self._client.get(
                "/api/version",
                timeout=10.0,
                headers={"Accept": "*/*"},
            )
            response.raise_for_status()
            value = response.text.strip()
            self._version = value or None
        except httpx.HTTPError as exc:
            logger.warning(
                "Could not retrieve GROBID version. base_url=%s error=%r",
                self.settings.grobid_base_url,
                exc,
            )
            self._version = None
        return self._version

    async def extract(
        self,
        pdf_path: Path,
        *,
        filename: str,
        consolidate_header: str,
        consolidate_citations: str,
        include_raw_citations: bool,
        include_raw_affiliations: bool,
        segment_sentences: bool,
        include_tei_xml: bool,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        tei_xml = await self._process_fulltext(
            pdf_path,
            filename=filename,
            consolidate_header=consolidate_header,
            consolidate_citations=consolidate_citations,
            include_raw_citations=include_raw_citations,
            include_raw_affiliations=include_raw_affiliations,
            segment_sentences=segment_sentences,
        )
        parsed = parse_tei(tei_xml)

        return {
            "version": await self.version(),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "stats": parsed.get("counts", {}),
            "raw": {"tei_xml": tei_xml} if include_tei_xml else None,
            "parsed": parsed,
        }

    async def _process_fulltext(
        self,
        pdf_path: Path,
        *,
        filename: str,
        consolidate_header: str,
        consolidate_citations: str,
        include_raw_citations: bool,
        include_raw_affiliations: bool,
        segment_sentences: bool,
    ) -> str:
        text_fields: list[tuple[str, str]] = [
            ("consolidateHeader", consolidate_header),
            ("consolidateCitations", consolidate_citations),
            ("includeRawCitations", "1" if include_raw_citations else "0"),
            ("includeRawAffiliations", "1" if include_raw_affiliations else "0"),
            ("segmentSentences", "1" if segment_sentences else "0"),
            ("generateIDs", "1"),
        ]
        text_fields.extend(
            ("teiCoordinates", coordinate) for coordinate in self.settings.grobid_tei_coordinates
        )

        last_error: Exception | None = None
        for attempt in range(1, self.settings.grobid_max_retries + 1):
            try:
                with pdf_path.open("rb") as pdf_file:
                    # Put both the file and normal fields in one multipart list so
                    # repeated `teiCoordinates` values are preserved reliably.
                    multipart: list[tuple[str, tuple[str | None, Any, str | None]]] = [
                        ("input", (filename, pdf_file, "application/pdf")),
                    ]
                    multipart.extend((name, (None, value, None)) for name, value in text_fields)
                    response = await self._client.post(
                        "/api/processFulltextDocument",
                        files=multipart,
                        headers={"Accept": "application/xml"},
                    )

                if response.status_code in {429, 502, 503, 504}:
                    raise GrobidServiceError(
                        f"GROBID returned retryable HTTP {response.status_code}."
                    )
                if response.status_code == 204:
                    raise GrobidServiceError("GROBID completed but extracted no content.")

                response.raise_for_status()
                if not response.text.strip():
                    raise GrobidServiceError("GROBID returned an empty response.")
                return response.text
            except (httpx.HTTPError, GrobidServiceError) as exc:
                last_error = exc
                logger.warning(
                    "GROBID extraction attempt %s/%s failed: %r",
                    attempt,
                    self.settings.grobid_max_retries,
                    exc,
                )
                if attempt < self.settings.grobid_max_retries:
                    await asyncio.sleep(min(2**attempt, 10))

        raise GrobidServiceError(f"GROBID request failed: {last_error}")
