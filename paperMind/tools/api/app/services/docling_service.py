import asyncio
import importlib.metadata
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.parsers.docling import parse_docling_document
from app.utils import asset_url

logger = logging.getLogger(__name__)


class DoclingService:
    """Long-lived Docling converter guarded by a concurrency limit."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._converter: Any | None = None
        self._init_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.docling_max_concurrency)
        self._initialization_error: str | None = None
        try:
            self.version = importlib.metadata.version("docling")
        except importlib.metadata.PackageNotFoundError:
            self.version = None

    @property
    def is_initialized(self) -> bool:
        return self._converter is not None

    @property
    def initialization_error(self) -> str | None:
        return self._initialization_error

    async def initialize(self) -> None:
        if self._converter is not None:
            return
        async with self._init_lock:
            if self._converter is not None:
                return
            try:
                self._converter = await run_in_threadpool(self._build_converter)
                self._initialization_error = None
            except Exception as exc:
                self._initialization_error = str(exc)
                raise

    def _build_converter(self) -> Any:
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            RapidOcrOptions,
            TableFormerMode,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption

        options = PdfPipelineOptions()
        options.accelerator_options = AcceleratorOptions(
            device=self.settings.docling_accelerator_device,
            num_threads=self.settings.docling_accelerator_num_threads,
        )
        options.document_timeout = self.settings.docling_document_timeout_seconds

        options.do_ocr = self.settings.docling_do_ocr
        if options.do_ocr:
            options.ocr_options = RapidOcrOptions(
                backend=self.settings.docling_ocr_backend,
                force_full_page_ocr=self.settings.docling_ocr_force_full_page,
                bitmap_area_threshold=self.settings.docling_ocr_bitmap_area_threshold,
            )

        options.do_table_structure = self.settings.docling_do_table_structure
        options.table_structure_options.mode = (
            TableFormerMode.ACCURATE
            if self.settings.docling_table_mode == "accurate"
            else TableFormerMode.FAST
        )
        options.table_structure_options.do_cell_matching = (
            self.settings.docling_table_do_cell_matching
        )

        options.do_formula_enrichment = self.settings.docling_do_formula_enrichment
        options.images_scale = self.settings.docling_images_scale
        options.generate_page_images = self.settings.docling_generate_page_images
        options.generate_picture_images = self.settings.docling_generate_picture_images

        return DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options),
            },
        )

    async def runtime_info(self) -> dict[str, Any]:
        return await run_in_threadpool(self._runtime_info_sync)

    def _runtime_info_sync(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "configured_device": self.settings.docling_accelerator_device,
            "ocr_backend": self.settings.docling_ocr_backend,
            "initialized": self.is_initialized,
            "initialization_error": self.initialization_error,
            "docling_version": self.version,
        }
        try:
            import torch

            cuda_available = torch.cuda.is_available()
            info.update(
                {
                    "torch_version": torch.__version__,
                    "torch_cuda_version": torch.version.cuda,
                    "cuda_available": cuda_available,
                    "cuda_device_count": torch.cuda.device_count() if cuda_available else 0,
                    "gpu_name": torch.cuda.get_device_name(0) if cuda_available else None,
                    "gpu_capability": (
                        torch.cuda.get_device_capability(0) if cuda_available else None
                    ),
                    "compiled_architectures": torch.cuda.get_arch_list() if cuda_available else [],
                }
            )
        except Exception as exc:  # pragma: no cover - diagnostics must not break health endpoints
            info["torch_error"] = str(exc)
        return info

    async def extract(
        self,
        pdf_path: Path,
        *,
        document_id: str,
        include_markdown: bool,
        export_pictures: bool,
        export_tables: bool,
    ) -> dict[str, Any]:
        await self.initialize()
        assert self._converter is not None

        async with self._semaphore:
            started = time.perf_counter()
            result = await run_in_threadpool(
                self._convert_sync,
                pdf_path,
                document_id,
                include_markdown,
                export_pictures,
                export_tables,
            )
            result["duration_seconds"] = round(time.perf_counter() - started, 3)
            return result

    def _convert_sync(
        self,
        pdf_path: Path,
        document_id: str,
        include_markdown: bool,
        export_pictures: bool,
        export_tables: bool,
    ) -> dict[str, Any]:
        assert self._converter is not None

        conversion = self._converter.convert(
            pdf_path,
            max_num_pages=self.settings.docling_max_num_pages,
            max_file_size=self.settings.max_upload_size_bytes,
        )
        document = conversion.document
        document_json = document.export_to_dict()

        picture_assets, table_assets = self._export_assets(
            document,
            document_id=document_id,
            export_pictures=export_pictures,
            export_tables=export_tables,
        )
        parsed = parse_docling_document(
            document_json,
            picture_assets=picture_assets,
            table_assets=table_assets,
        )

        counts = parsed["counts"]
        stats = {
            "pages": len(document.pages),
            "text_items": len(document.texts),
            "tables": len(document.tables),
            "pictures": len(document.pictures),
            "groups": len(document.groups),
            "formulas": counts["formulas"],
            "tables_structured": counts["tables_structured"],
            "tables_empty_structure": counts["tables_empty_structure"],
            "exported_pictures": sum(
                1 for asset in picture_assets if asset.get("status") == "saved"
            ),
            "exported_tables": sum(1 for asset in table_assets if asset.get("status") == "saved"),
        }

        raw: dict[str, Any] = {
            "document_json": document_json,
            "assets": {
                "pictures": picture_assets,
                "tables": table_assets,
            },
        }
        if include_markdown:
            raw["markdown"] = document.export_to_markdown()

        return {
            "version": self.version,
            "stats": stats,
            "raw": raw,
            "parsed": parsed,
        }

    def _export_assets(
        self,
        document: Any,
        *,
        document_id: str,
        export_pictures: bool,
        export_tables: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        from docling_core.types.doc import PictureItem, TableItem

        document_dir = self.settings.assets_dir / document_id
        pictures_dir = document_dir / "figures"
        tables_dir = document_dir / "tables"

        # Reprocessing the same content hash should not leave stale files from an
        # earlier run with a different number of elements.
        if export_pictures and pictures_dir.exists():
            shutil.rmtree(pictures_dir)
        if export_tables and tables_dir.exists():
            shutil.rmtree(tables_dir)

        if export_pictures:
            pictures_dir.mkdir(parents=True, exist_ok=True)
        if export_tables:
            tables_dir.mkdir(parents=True, exist_ok=True)

        picture_assets: list[dict[str, Any]] = []
        table_assets: list[dict[str, Any]] = []
        picture_index = 0
        table_index = 0

        for element, _level in document.iterate_items():
            if export_tables and isinstance(element, TableItem):
                table_index += 1
                asset = self._save_element_image(
                    element,
                    document,
                    output_dir=tables_dir,
                    relative_dir=Path(document_id) / "tables",
                    prefix="table",
                    index=table_index,
                )
                table_assets.append(asset)

            if export_pictures and isinstance(element, PictureItem):
                picture_index += 1
                asset = self._save_element_image(
                    element,
                    document,
                    output_dir=pictures_dir,
                    relative_dir=Path(document_id) / "figures",
                    prefix="figure",
                    index=picture_index,
                )
                picture_assets.append(asset)

        return picture_assets, table_assets

    def _save_element_image(
        self,
        element: Any,
        document: Any,
        *,
        output_dir: Path,
        relative_dir: Path,
        prefix: str,
        index: int,
    ) -> dict[str, Any]:
        image = element.get_image(document)
        element_id = str(getattr(element, "self_ref", "")) or None
        if image is None:
            logger.warning("Docling returned no image for %s %s", prefix, index)
            return {
                "index": index,
                "element_id": element_id,
                "status": "not_available",
                "error": "Docling returned no image for this element.",
            }

        filename = f"{prefix}_{index:03d}.png"
        path = output_dir / filename
        with path.open("wb") as file_handle:
            image.save(file_handle, format="PNG", compress_level=6)

        relative_path = (relative_dir / filename).as_posix()
        return {
            "index": index,
            "element_id": element_id,
            "status": "saved",
            "filename": filename,
            "relative_path": relative_path,
            "url": asset_url(self.settings.assets_url_prefix, relative_path),
            "width": image.width,
            "height": image.height,
            "size_bytes": path.stat().st_size,
        }
