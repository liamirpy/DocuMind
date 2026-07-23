import asyncio
import time
from pathlib import Path
from typing import Any

from app.canonical.builder import CanonicalPackageBuilder
from app.clients.extractor import ExtractorClient
from app.clients.ollama import OllamaClient
from app.config import Settings


class AgentPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.extractor = ExtractorClient(settings)
        self.llm = OllamaClient(settings)
        self.builder = CanonicalPackageBuilder(
            settings,
            extractor=self.extractor,
            llm=self.llm,
        )
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def close(self) -> None:
        await self.extractor.close()
        await self.llm.close()

    async def ready(self) -> dict[str, Any]:
        tools_ready = await self.extractor.is_ready()
        llm_alive = await self.llm.is_alive() if self.settings.llm_enabled else None
        return {
            "tools_ready": tools_ready,
            "llm_enabled": self.settings.llm_enabled,
            "llm_alive": llm_alive,
            "ready": tools_ready,
        }

    async def process(
        self,
        *,
        pdf_path: Path,
        filename: str,
        use_llm: bool,
        output_folder: str | None = None,
        overwrite: bool | None = None,
    ) -> dict[str, Any]:
        async with self._semaphore:
            started = time.perf_counter()
            extraction_started = time.perf_counter()
            extraction = await self.extractor.extract(pdf_path, filename=filename)
            extraction_seconds = time.perf_counter() - extraction_started

            packaging_started = time.perf_counter()
            result = await self.builder.build(
                pdf_path=pdf_path,
                filename=filename,
                extraction=extraction,
                use_llm=use_llm,
                output_folder=output_folder,
                overwrite=overwrite,
            )
            packaging_seconds = time.perf_counter() - packaging_started
            result["processing"] = {
                "extraction_seconds": round(extraction_seconds, 3),
                "canonicalization_seconds": round(packaging_seconds, 3),
                "total_seconds": round(time.perf_counter() - started, 3),
            }
            return result
