import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.canonical.coordinates import region_from_docling, regions_from_grobid
from app.canonical.cropper import crop_grobid_region, crop_region
from app.canonical.exporters import (
    latex_escape,
    normalize_llm_table,
    table_matrix,
    table_to_latex,
    write_table_assets,
)
from app.canonical.matching import best_match
from app.canonical.quality import build_quality_report
from app.canonical.refs import referenced_texts
from app.canonical.sections import (
    assign_text_blocks_to_sections,
    attach_elements_to_sections,
    build_section_structure,
    build_section_tree,
)
from app.clients.extractor import ExtractorClient
from app.clients.ollama import OllamaClient
from app.config import Settings
from app.utils import (
    atomic_write_json,
    atomic_write_text,
    recreate_directory,
    relative_posix,
    safe_output_folder,
)


class CanonicalPackageBuilder:
    def __init__(
        self,
        settings: Settings,
        *,
        extractor: ExtractorClient,
        llm: OllamaClient,
    ) -> None:
        self.settings = settings
        self.extractor = extractor
        self.llm = llm

    async def build(
        self,
        *,
        pdf_path: Path,
        filename: str,
        extraction: dict[str, Any],
        use_llm: bool,
        output_folder: str | None = None,
        overwrite: bool | None = None,
    ) -> dict[str, Any]:
        document = extraction.get("document") or {}
        document_id = str(document.get("sha256") or "unknown")
        package_name = safe_output_folder(output_folder) if output_folder else document_id
        package_dir = self.settings.output_dir / package_name
        zip_candidate = self.settings.output_dir / f"{package_name}.zip"
        should_overwrite = (
            self.settings.overwrite_existing_package if overwrite is None else overwrite
        )

        if not should_overwrite and (package_dir.exists() or zip_candidate.exists()):
            raise FileExistsError(
                f"Output folder '{package_name}' already exists. "
                "Choose another output_folder or submit overwrite=true."
            )

        if should_overwrite:
            recreate_directory(package_dir)
            zip_candidate.unlink(missing_ok=True)
        else:
            package_dir.mkdir(parents=True, exist_ok=False)

        source_dir = package_dir / "source"
        text_dir = package_dir / "text"
        figures_dir = package_dir / "figures"
        tables_dir = package_dir / "tables"
        formulas_dir = package_dir / "formulas"
        latex_dir = package_dir / "latex"
        for directory in (
            source_dir,
            text_dir,
            figures_dir,
            tables_dir,
            formulas_dir,
            latex_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        source_pdf = source_dir / "original.pdf"
        shutil.copy2(pdf_path, source_pdf)

        if self.settings.keep_raw_extractor_response:
            atomic_write_json(source_dir / "extractor-response.json", extraction)

        docling = extraction.get("docling") or {}
        grobid = extraction.get("grobid") or {}
        docling_raw = docling.get("raw") or {}
        docling_document = docling_raw.get("document_json") or {}
        docling_parsed = docling.get("parsed") or {}
        grobid_parsed = grobid.get("parsed") or {}
        grobid_raw = grobid.get("raw") or {}

        warnings: list[str] = [str(value) for value in extraction.get("warnings") or []]
        llm_budget = self.settings.llm_max_items_per_document
        llm_used = 0
        llm_available = use_llm and self.settings.llm_enabled and await self.llm.is_alive()
        if use_llm and self.settings.llm_enabled and not llm_available:
            warnings.append(
                "LLM enrichment was requested but the configured Ollama service is unavailable."
            )

        metadata = self._metadata(grobid_parsed, docling_document, filename, document_id)
        text_content = self._text_content(docling_document, docling_raw, grobid_parsed)
        section_structure = build_section_structure(
            tei_xml=grobid_raw.get("tei_xml"),
            flat_sections=grobid_parsed.get("sections") or [],
        )
        assign_text_blocks_to_sections(
            text_content["text_blocks"],
            sections=section_structure["sections"],
            paragraphs=section_structure["paragraphs"],
        )
        atomic_write_text(text_dir / "full_text.txt", text_content["full_text"])
        atomic_write_text(text_dir / "full_text.md", text_content["markdown"])

        figures, figure_warnings, figure_llm_used = await self._build_figures(
            pdf_path=pdf_path,
            package_dir=package_dir,
            output_dir=figures_dir,
            docling_document=docling_document,
            docling_parsed=docling_parsed,
            grobid_parsed=grobid_parsed,
            llm_available=llm_available,
            llm_budget=max(0, llm_budget - llm_used),
        )
        warnings.extend(figure_warnings)
        llm_used += figure_llm_used

        tables, table_warnings, table_llm_used, combined_tables_latex = await self._build_tables(
            pdf_path=pdf_path,
            package_dir=package_dir,
            output_dir=tables_dir,
            docling_document=docling_document,
            docling_parsed=docling_parsed,
            grobid_parsed=grobid_parsed,
            llm_available=llm_available,
            llm_budget=max(0, llm_budget - llm_used),
        )
        warnings.extend(table_warnings)
        llm_used += table_llm_used

        (
            formulas,
            formula_warnings,
            formula_llm_used,
            combined_formulas_latex,
        ) = await self._build_formulas(
            pdf_path=pdf_path,
            package_dir=package_dir,
            output_dir=formulas_dir,
            docling_parsed=docling_parsed,
            grobid_parsed=grobid_parsed,
            llm_available=llm_available,
            llm_budget=max(0, llm_budget - llm_used),
        )
        warnings.extend(formula_warnings)
        llm_used += formula_llm_used

        attach_elements_to_sections(
            sections=section_structure["sections"],
            source_element_to_section=section_structure["source_element_to_section"],
            figures=figures,
            tables=tables,
            formulas=formulas,
        )
        section_tree = build_section_tree(section_structure["sections"])

        atomic_write_text(latex_dir / "tables.tex", combined_tables_latex)
        atomic_write_text(latex_dir / "formulas.tex", combined_formulas_latex)
        master_latex = self._master_latex(figures, tables, formulas)
        atomic_write_text(latex_dir / "document_assets.tex", master_latex)

        canonical: dict[str, Any] = {
            "schema_version": "1.2.0",
            "document_id": document_id,
            "created_at": datetime.now(UTC).isoformat(),
            "output": {
                "folder_name": package_name,
                "relative_path": package_name,
                "zip_name": f"{package_name}.zip" if self.settings.create_zip_package else None,
            },
            "document": {
                "filename": filename,
                "sha256": document_id,
                "size_bytes": document.get("size_bytes"),
                "source_pdf": relative_posix(source_pdf, package_dir),
            },
            "metadata": metadata,
            "content": {
                "full_text": text_content["full_text"],
                "text_blocks": text_content["text_blocks"],
                "paragraphs": section_structure["paragraphs"],
                "sections": section_structure["sections"],
                "section_tree": section_tree,
                "figures": figures,
                "tables": tables,
                "formulas": formulas,
                "references": grobid_parsed.get("references") or [],
            },
            "assets": {
                "text": {
                    "plain_text": "text/full_text.txt",
                    "markdown": "text/full_text.md",
                },
                "latex": {
                    "formulas": "latex/formulas.tex",
                    "tables": "latex/tables.tex",
                    "master": "latex/document_assets.tex",
                },
            },
            "provenance": {
                "extractor_schema_version": extraction.get("schema_version"),
                "extractor_request_id": extraction.get("request_id"),
                "extractor_status": extraction.get("status"),
                "docling": {
                    "status": docling.get("status"),
                    "version": docling.get("version"),
                    "stats": docling.get("stats") or {},
                },
                "grobid": {
                    "status": grobid.get("status"),
                    "version": grobid.get("version"),
                    "stats": grobid.get("stats") or {},
                    "section_structure_source": section_structure.get("source"),
                },
                "llm": {
                    "enabled_in_service": self.settings.llm_enabled,
                    "requested_for_document": use_llm,
                    "available": llm_available,
                    "provider": self.settings.llm_provider if self.settings.llm_enabled else None,
                    "model": self.settings.ollama_model if self.settings.llm_enabled else None,
                    "items_processed": llm_used,
                    "describe_all_elements": self.settings.llm_describe_all_elements,
                    "max_items_per_document": self.settings.llm_max_items_per_document,
                    "role": (
                        "bounded visual repair and description for figures, tables, and formulas; "
                        "parser evidence is always retained"
                    ),
                },
            },
            "warnings": list(dict.fromkeys(warnings)),
        }
        canonical["quality"] = build_quality_report(
            canonical,
            extraction=extraction,
            settings=self.settings,
        )
        canonical["counts"] = {
            "text_blocks": len(text_content["text_blocks"]),
            "paragraphs": len(canonical["content"]["paragraphs"]),
            "sections": len(canonical["content"]["sections"]),
            "root_sections": len(canonical["content"]["section_tree"]),
            "figures": len(figures),
            "tables": len(tables),
            "formulas": len(formulas),
            "references": len(canonical["content"]["references"]),
        }

        canonical_path = package_dir / "canonical_document.json"
        atomic_write_json(canonical_path, canonical)

        zip_path: Path | None = None
        if self.settings.create_zip_package:
            archive = shutil.make_archive(
                str(self.settings.output_dir / package_name),
                "zip",
                root_dir=package_dir,
            )
            zip_path = Path(archive)

        return {
            "document_id": document_id,
            "package_name": package_name,
            "package_dir": package_dir,
            "canonical_path": canonical_path,
            "zip_path": zip_path,
            "canonical": canonical,
        }

    def _metadata(
        self,
        grobid_parsed: dict[str, Any],
        docling_document: dict[str, Any],
        filename: str,
        document_id: str,
    ) -> dict[str, Any]:
        metadata = dict(grobid_parsed.get("metadata") or {})
        metadata.setdefault("title", None)
        metadata.setdefault("authors", [])
        metadata.setdefault("abstract", None)
        metadata.setdefault("doi", None)
        metadata.setdefault("journal", None)
        metadata.setdefault("publication_date", None)
        metadata.setdefault("language", None)
        if not metadata.get("title"):
            metadata["title"] = docling_document.get("name") or Path(filename).stem
        metadata["source_filename"] = filename
        metadata["document_id"] = document_id
        metadata["sources"] = {
            "primary": "grobid",
            "docling_document_name": docling_document.get("name"),
        }
        return metadata

    def _text_content(
        self,
        docling_document: dict[str, Any],
        docling_raw: dict[str, Any],
        grobid_parsed: dict[str, Any],
    ) -> dict[str, Any]:
        excluded = {"formula", "page_header", "page_footer"}
        blocks: list[dict[str, Any]] = []
        full_text_parts: list[str] = []
        for index, item in enumerate(docling_document.get("texts") or [], start=1):
            label = str(item.get("label") or "text")
            if label.lower() in excluded:
                continue
            text = item.get("text") or item.get("orig")
            if not isinstance(text, str) or not text.strip():
                continue
            clean = " ".join(text.split())
            block = {
                "id": item.get("self_ref") or f"text_{index:05d}",
                "index": index,
                "label": label,
                "text": clean,
                "original": item.get("orig"),
                "provenance": item.get("prov") or [],
            }
            blocks.append(block)
            full_text_parts.append(clean)

        if not blocks:
            fallback_index = 0
            for section in grobid_parsed.get("sections") or []:
                heading = section.get("heading")
                if heading:
                    fallback_index += 1
                    blocks.append(
                        {
                            "id": f"grobid_text_{fallback_index:05d}",
                            "index": fallback_index,
                            "label": "section_header",
                            "text": heading,
                            "original": heading,
                            "provenance": [],
                            "source": "grobid_fallback",
                        }
                    )
                    full_text_parts.append(heading)
                for paragraph in section.get("paragraphs") or []:
                    if not isinstance(paragraph, str) or not paragraph.strip():
                        continue
                    fallback_index += 1
                    clean = " ".join(paragraph.split())
                    blocks.append(
                        {
                            "id": f"grobid_text_{fallback_index:05d}",
                            "index": fallback_index,
                            "label": "paragraph",
                            "text": clean,
                            "original": paragraph,
                            "provenance": [],
                            "source": "grobid_fallback",
                        }
                    )
                    full_text_parts.append(clean)

        markdown = str(docling_raw.get("markdown") or "").strip()
        if not markdown:
            sections = grobid_parsed.get("sections") or []
            markdown = "\n\n".join(
                "\n\n".join(
                    filter(
                        None,
                        [
                            f"## {section.get('heading')}" if section.get("heading") else None,
                            "\n\n".join(section.get("paragraphs") or []),
                        ],
                    )
                )
                for section in sections
            )
        return {
            "text_blocks": blocks,
            "full_text": "\n\n".join(full_text_parts),
            "markdown": markdown + ("\n" if markdown else ""),
        }

    async def _materialize_asset(
        self,
        *,
        asset: dict[str, Any] | None,
        destination: Path,
        pdf_path: Path,
        provenance: list[dict[str, Any]] | None,
        crop_scale: float,
        crop_padding: float,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        warnings: list[str] = []
        if asset and asset.get("status") == "saved" and asset.get("url"):
            try:
                await self.extractor.download_asset(str(asset["url"]), destination)
                return (
                    {
                        "path": destination.name,
                        "width": asset.get("width"),
                        "height": asset.get("height"),
                        "size_bytes": destination.stat().st_size,
                        "source": "docling_export",
                    },
                    warnings,
                )
            except Exception as exc:
                warnings.append(f"Could not download extractor asset {asset.get('url')}: {exc}")

        crop = crop_region(
            pdf_path,
            provenance=provenance,
            destination=destination,
            scale=crop_scale,
            padding_points=crop_padding,
        )
        if crop.get("status") == "saved":
            return (
                {
                    "path": destination.name,
                    "width": crop.get("width"),
                    "height": crop.get("height"),
                    "size_bytes": crop.get("size_bytes"),
                    "source": "pdf_provenance_crop",
                    "page": crop.get("page"),
                },
                warnings,
            )
        warnings.append(str(crop.get("error") or "Asset could not be materialized."))
        return None, warnings

    def _description_record(
        self,
        payload: dict[str, Any] | None,
        *,
        element_type: str,
    ) -> dict[str, Any] | None:
        if not payload:
            return None
        text = str(payload.get("description") or "").strip()
        summary = str(payload.get("summary") or "").strip()
        if not text and not summary:
            return None
        excluded = {
            "description",
            "summary",
            "confidence",
            "warnings",
            "columns",
            "rows",
            "latex",
            "plain_text",
        }
        details = {key: value for key, value in payload.items() if key not in excluded}
        return {
            "text": text or summary,
            "summary": summary or None,
            "element_type": element_type,
            "source": "ollama_vision",
            "provider": self.settings.llm_provider,
            "model": self.settings.ollama_model,
            "confidence": payload.get("confidence"),
            "warnings": payload.get("warnings") or [],
            "details": details,
        }

    def _write_description_assets(
        self,
        *,
        output_dir: Path,
        package_dir: Path,
        stem: str,
        description: dict[str, Any] | None,
    ) -> dict[str, str]:
        if not description:
            return {}
        text_path = output_dir / f"{stem}.description.txt"
        json_path = output_dir / f"{stem}.description.json"
        parts = [
            value
            for value in (description.get("summary"), description.get("text"))
            if isinstance(value, str) and value.strip()
        ]
        atomic_write_text(text_path, "\n\n".join(dict.fromkeys(parts)) + "\n")
        atomic_write_json(json_path, description)
        return {
            "description_text": relative_posix(text_path, package_dir),
            "description_json": relative_posix(json_path, package_dir),
        }

    async def _build_figures(
        self,
        *,
        pdf_path: Path,
        package_dir: Path,
        output_dir: Path,
        docling_document: dict[str, Any],
        docling_parsed: dict[str, Any],
        grobid_parsed: dict[str, Any],
        llm_available: bool,
        llm_budget: int,
    ) -> tuple[list[dict[str, Any]], list[str], int]:
        warnings: list[str] = []
        llm_used = 0
        docling_figures = docling_parsed.get("pictures") or []
        grobid_figures = [
            item
            for item in grobid_parsed.get("figures_and_tables") or []
            if item.get("type") != "table"
        ]
        used_grobid: set[int] = set()
        output: list[dict[str, Any]] = []

        for index, item in enumerate(docling_figures, start=1):
            captions = item.get("captions") or []
            caption = captions[0] if captions else None
            match_index, match_score, match_parts = best_match(
                item,
                grobid_figures,
                source_text=lambda value: " ".join(value.get("captions") or []),
                candidate_text=lambda value: " ".join(
                    filter(None, [value.get("label"), value.get("caption")])
                ),
                used_indexes=used_grobid,
                source_index=index - 1,
            )
            grobid_item = grobid_figures[match_index] if match_index is not None else None
            if match_index is not None:
                used_grobid.add(match_index)
            if not caption and grobid_item:
                caption = grobid_item.get("caption")

            stem = f"figure_{index:03d}"
            image_path = output_dir / f"{stem}.png"
            image_asset, asset_warnings = await self._materialize_asset(
                asset=item.get("asset"),
                destination=image_path,
                pdf_path=pdf_path,
                provenance=item.get("provenance") or [],
                crop_scale=self.settings.fallback_asset_crop_scale,
                crop_padding=self.settings.fallback_asset_crop_padding_points,
            )
            warnings.extend(f"{stem}: {warning}" for warning in asset_warnings)
            if image_asset:
                image_asset["path"] = relative_posix(image_path, package_dir)

            description: dict[str, Any] | None = None
            should_describe = (
                llm_available
                and llm_used < llm_budget
                and image_path.exists()
                and (
                    self.settings.llm_describe_all_elements
                    or self.settings.llm_validate_all_figures
                    or not caption
                )
            )
            if should_describe:
                try:
                    raw_description = await self.llm.describe_figure(
                        image_path,
                        caption=caption,
                    )
                    description = self._description_record(
                        raw_description,
                        element_type="figure",
                    )
                    llm_used += 1
                except Exception as exc:
                    warnings.append(f"{stem}: LLM figure description failed: {exc}")

            description_assets = self._write_description_assets(
                output_dir=output_dir,
                package_dir=package_dir,
                stem=stem,
                description=description,
            )
            caption_path = output_dir / f"{stem}.caption.txt"
            atomic_write_text(caption_path, (caption or "") + ("\n" if caption else ""))
            region = region_from_docling(item.get("provenance") or [])
            output.append(
                {
                    "id": stem,
                    "index": index,
                    "label": grobid_item.get("label") if grobid_item else None,
                    "caption": caption,
                    "description": description,
                    "page": region.page if region else None,
                    "provenance": {
                        "docling": item.get("provenance") or [],
                        "grobid_coords": grobid_item.get("coords") if grobid_item else None,
                    },
                    "alignment": {
                        "matched": grobid_item is not None,
                        "confidence": round(match_score, 4),
                        "components": match_parts,
                        "grobid_id": grobid_item.get("id") if grobid_item else None,
                    },
                    "assets": {
                        "image": image_asset,
                        "caption_text": relative_posix(caption_path, package_dir),
                        **description_assets,
                    },
                    "sources": {
                        "docling_id": item.get("id"),
                        "grobid": grobid_item,
                    },
                }
            )

        for grobid_index, grobid_item in enumerate(grobid_figures):
            if grobid_index in used_grobid:
                continue
            index = len(output) + 1
            stem = f"figure_{index:03d}"
            image_path = output_dir / f"{stem}.png"
            crop = crop_grobid_region(
                pdf_path,
                coords=grobid_item.get("coords"),
                destination=image_path,
                scale=self.settings.fallback_asset_crop_scale,
                padding_points=self.settings.fallback_asset_crop_padding_points,
            )
            image_asset = None
            if crop.get("status") == "saved":
                image_asset = {
                    "path": relative_posix(image_path, package_dir),
                    "width": crop.get("width"),
                    "height": crop.get("height"),
                    "size_bytes": crop.get("size_bytes"),
                    "page": crop.get("page"),
                    "source": "grobid_provenance_crop",
                }
            else:
                warnings.append(f"{stem}: {crop.get('error')}")

            caption = grobid_item.get("caption")
            description = None
            if (
                llm_available
                and llm_used < llm_budget
                and image_path.exists()
                and (
                    self.settings.llm_describe_all_elements
                    or self.settings.llm_validate_all_figures
                    or not caption
                )
            ):
                try:
                    raw_description = await self.llm.describe_figure(
                        image_path,
                        caption=caption,
                    )
                    description = self._description_record(
                        raw_description,
                        element_type="figure",
                    )
                    llm_used += 1
                except Exception as exc:
                    warnings.append(f"{stem}: LLM figure description failed: {exc}")
            description_assets = self._write_description_assets(
                output_dir=output_dir,
                package_dir=package_dir,
                stem=stem,
                description=description,
            )
            caption_path = output_dir / f"{stem}.caption.txt"
            atomic_write_text(caption_path, (caption or "") + ("\n" if caption else ""))
            grobid_regions = regions_from_grobid(grobid_item.get("coords"))
            output.append(
                {
                    "id": stem,
                    "index": index,
                    "label": grobid_item.get("label"),
                    "caption": caption,
                    "description": description,
                    "page": grobid_regions[0].page if grobid_regions else None,
                    "provenance": {"docling": [], "grobid_coords": grobid_item.get("coords")},
                    "alignment": {
                        "matched": False,
                        "confidence": 0.0,
                        "components": {},
                        "grobid_id": grobid_item.get("id"),
                        "status": "grobid_only",
                    },
                    "assets": {
                        "image": image_asset,
                        "caption_text": relative_posix(caption_path, package_dir),
                        **description_assets,
                    },
                    "sources": {"docling_id": None, "grobid": grobid_item},
                }
            )
        return output, warnings, llm_used

    async def _build_tables(
        self,
        *,
        pdf_path: Path,
        package_dir: Path,
        output_dir: Path,
        docling_document: dict[str, Any],
        docling_parsed: dict[str, Any],
        grobid_parsed: dict[str, Any],
        llm_available: bool,
        llm_budget: int,
    ) -> tuple[list[dict[str, Any]], list[str], int, str]:
        warnings: list[str] = []
        llm_used = 0
        raw_tables = docling_document.get("tables") or []
        parsed_tables = docling_parsed.get("tables") or []
        grobid_tables = [
            item
            for item in grobid_parsed.get("figures_and_tables") or []
            if item.get("type") == "table"
        ]
        used_grobid: set[int] = set()
        output: list[dict[str, Any]] = []
        combined_latex: list[str] = []

        for index, raw_item in enumerate(raw_tables, start=1):
            parsed = parsed_tables[index - 1] if index <= len(parsed_tables) else {}
            captions = parsed.get("captions") or referenced_texts(
                docling_document,
                raw_item.get("captions") or [],
            )
            caption = captions[0] if captions else None
            caption_source = " ".join(captions)
            match_index, match_score, match_parts = best_match(
                parsed or raw_item,
                grobid_tables,
                source_text=lambda value, fallback=caption_source: " ".join(
                    value.get("captions") or [fallback]
                ),
                candidate_text=lambda value: " ".join(
                    filter(None, [value.get("label"), value.get("caption")])
                ),
                used_indexes=used_grobid,
                source_index=index - 1,
            )
            grobid_item = grobid_tables[match_index] if match_index is not None else None
            if match_index is not None:
                used_grobid.add(match_index)
            if not caption and grobid_item:
                caption = grobid_item.get("caption")

            stem = f"table_{index:03d}"
            image_path = output_dir / f"{stem}.png"
            image_asset, asset_warnings = await self._materialize_asset(
                asset=parsed.get("asset"),
                destination=image_path,
                pdf_path=pdf_path,
                provenance=parsed.get("provenance") or raw_item.get("prov") or [],
                crop_scale=self.settings.fallback_asset_crop_scale,
                crop_padding=self.settings.fallback_asset_crop_padding_points,
            )
            warnings.extend(f"{stem}: {warning}" for warning in asset_warnings)
            if image_asset:
                image_asset["path"] = relative_posix(image_path, package_dir)

            columns, rows, structure_warnings = table_matrix(raw_item)
            data_source = "docling_tableformer" if columns else "none"
            repair: dict[str, Any] | None = None
            if (
                not columns
                and llm_available
                and self.settings.llm_repair_empty_tables
                and llm_used < llm_budget
                and image_path.exists()
            ):
                try:
                    repair = await self.llm.repair_table(image_path, caption=caption)
                    llm_used += 1
                    repaired_columns, repaired_rows, repair_warnings = normalize_llm_table(repair)
                    if repaired_columns and repaired_rows:
                        columns, rows = repaired_columns, repaired_rows
                        data_source = "ollama_vision_repair"
                        structure_warnings.extend(repair_warnings)
                    else:
                        structure_warnings.append(
                            "The vision model returned no usable table rows or columns."
                        )
                except Exception as exc:
                    structure_warnings.append(f"LLM table repair failed: {exc}")

            description = self._description_record(
                repair,
                element_type="table",
            )
            if (
                description is None
                and llm_available
                and self.settings.llm_describe_all_elements
                and llm_used < llm_budget
                and image_path.exists()
            ):
                try:
                    raw_description = await self.llm.describe_table(
                        image_path,
                        caption=caption,
                        columns=columns,
                        rows=rows,
                    )
                    description = self._description_record(
                        raw_description,
                        element_type="table",
                    )
                    llm_used += 1
                except Exception as exc:
                    structure_warnings.append(f"LLM table description failed: {exc}")

            description_assets = self._write_description_assets(
                output_dir=output_dir,
                package_dir=package_dir,
                stem=stem,
                description=description,
            )
            asset_names = write_table_assets(
                output_dir,
                stem=stem,
                columns=columns,
                rows=rows,
                caption=caption,
                latex_label=f"tab:{stem}",
            )
            latex_text = table_to_latex(
                columns,
                rows,
                caption=caption,
                label=f"tab:{stem}",
            )
            combined_latex.append(latex_text)
            caption_path = output_dir / f"{stem}.caption.txt"
            atomic_write_text(caption_path, (caption or "") + ("\n" if caption else ""))
            region = region_from_docling(parsed.get("provenance") or raw_item.get("prov") or [])
            if columns and rows:
                quality_status = "repaired" if data_source == "ollama_vision_repair" else "accepted"
            else:
                quality_status = "failed"

            output.append(
                {
                    "id": stem,
                    "index": index,
                    "label": grobid_item.get("label") if grobid_item else None,
                    "caption": caption,
                    "description": description,
                    "page": region.page if region else None,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "column_count": len(columns),
                    "data_source": data_source,
                    "latex": latex_text,
                    "quality": {
                        "status": quality_status,
                        "warnings": list(dict.fromkeys(structure_warnings)),
                        "llm_repair": repair,
                    },
                    "provenance": {
                        "docling": parsed.get("provenance") or raw_item.get("prov") or [],
                        "grobid_coords": grobid_item.get("coords") if grobid_item else None,
                    },
                    "alignment": {
                        "matched": grobid_item is not None,
                        "confidence": round(match_score, 4),
                        "components": match_parts,
                        "grobid_id": grobid_item.get("id") if grobid_item else None,
                    },
                    "assets": {
                        "image": image_asset,
                        "caption_text": relative_posix(caption_path, package_dir),
                        **description_assets,
                        **{
                            key: relative_posix(output_dir / filename, package_dir)
                            for key, filename in asset_names.items()
                        },
                    },
                    "sources": {
                        "docling_id": raw_item.get("self_ref"),
                        "docling_structure_status": parsed.get("structure_status"),
                        "grobid": grobid_item,
                    },
                }
            )

        for grobid_index, grobid_item in enumerate(grobid_tables):
            if grobid_index in used_grobid:
                continue
            index = len(output) + 1
            stem = f"table_{index:03d}"
            image_path = output_dir / f"{stem}.png"
            crop = crop_grobid_region(
                pdf_path,
                coords=grobid_item.get("coords"),
                destination=image_path,
                scale=self.settings.fallback_asset_crop_scale,
                padding_points=self.settings.fallback_asset_crop_padding_points,
            )
            image_asset = None
            if crop.get("status") == "saved":
                image_asset = {
                    "path": relative_posix(image_path, package_dir),
                    "width": crop.get("width"),
                    "height": crop.get("height"),
                    "size_bytes": crop.get("size_bytes"),
                    "page": crop.get("page"),
                    "source": "grobid_provenance_crop",
                }
            else:
                warnings.append(f"{stem}: {crop.get('error')}")

            caption = grobid_item.get("caption")
            columns: list[str] = []
            rows: list[list[str]] = []
            structure_warnings = [
                "This table was detected only by GROBID and has no Docling cell structure."
            ]
            repair = None
            data_source = "grobid_flat_text"
            if (
                llm_available
                and self.settings.llm_repair_empty_tables
                and llm_used < llm_budget
                and image_path.exists()
            ):
                try:
                    repair = await self.llm.repair_table(image_path, caption=caption)
                    llm_used += 1
                    columns, rows, repair_warnings = normalize_llm_table(repair)
                    structure_warnings.extend(repair_warnings)
                    if columns and rows:
                        data_source = "ollama_vision_repair"
                except Exception as exc:
                    structure_warnings.append(f"LLM table repair failed: {exc}")

            description = self._description_record(
                repair,
                element_type="table",
            )
            if (
                description is None
                and llm_available
                and self.settings.llm_describe_all_elements
                and llm_used < llm_budget
                and image_path.exists()
            ):
                try:
                    raw_description = await self.llm.describe_table(
                        image_path,
                        caption=caption,
                        columns=columns,
                        rows=rows,
                    )
                    description = self._description_record(
                        raw_description,
                        element_type="table",
                    )
                    llm_used += 1
                except Exception as exc:
                    structure_warnings.append(f"LLM table description failed: {exc}")

            description_assets = self._write_description_assets(
                output_dir=output_dir,
                package_dir=package_dir,
                stem=stem,
                description=description,
            )
            asset_names = write_table_assets(
                output_dir,
                stem=stem,
                columns=columns,
                rows=rows,
                caption=caption,
                latex_label=f"tab:{stem}",
            )
            latex_text = table_to_latex(columns, rows, caption=caption, label=f"tab:{stem}")
            combined_latex.append(latex_text)
            caption_path = output_dir / f"{stem}.caption.txt"
            atomic_write_text(caption_path, (caption or "") + ("\n" if caption else ""))
            grobid_regions = regions_from_grobid(grobid_item.get("coords"))
            quality_status = "repaired" if columns and rows else "failed"
            output.append(
                {
                    "id": stem,
                    "index": index,
                    "label": grobid_item.get("label"),
                    "caption": caption,
                    "description": description,
                    "page": grobid_regions[0].page if grobid_regions else None,
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "column_count": len(columns),
                    "data_source": data_source,
                    "flattened_text": grobid_item.get("content"),
                    "latex": latex_text,
                    "quality": {
                        "status": quality_status,
                        "warnings": list(dict.fromkeys(structure_warnings)),
                        "llm_repair": repair,
                    },
                    "provenance": {"docling": [], "grobid_coords": grobid_item.get("coords")},
                    "alignment": {
                        "matched": False,
                        "confidence": 0.0,
                        "components": {},
                        "grobid_id": grobid_item.get("id"),
                        "status": "grobid_only",
                    },
                    "assets": {
                        "image": image_asset,
                        "caption_text": relative_posix(caption_path, package_dir),
                        **description_assets,
                        **{
                            key: relative_posix(output_dir / filename, package_dir)
                            for key, filename in asset_names.items()
                        },
                    },
                    "sources": {
                        "docling_id": None,
                        "docling_structure_status": "missing",
                        "grobid": grobid_item,
                    },
                }
            )
        return output, warnings, llm_used, "\n".join(combined_latex)

    async def _build_formulas(
        self,
        *,
        pdf_path: Path,
        package_dir: Path,
        output_dir: Path,
        docling_parsed: dict[str, Any],
        grobid_parsed: dict[str, Any],
        llm_available: bool,
        llm_budget: int,
    ) -> tuple[list[dict[str, Any]], list[str], int, str]:
        warnings: list[str] = []
        llm_used = 0
        docling_formulas = docling_parsed.get("formulas") or []
        grobid_formulas = grobid_parsed.get("formulas") or []
        used_grobid: set[int] = set()
        output: list[dict[str, Any]] = []
        combined_latex: list[str] = []

        for index, item in enumerate(docling_formulas, start=1):
            match_index, match_score, match_parts = best_match(
                item,
                grobid_formulas,
                source_text=lambda value: value.get("text") or value.get("original"),
                candidate_text=lambda value: value.get("text"),
                used_indexes=used_grobid,
                source_index=index - 1,
            )
            grobid_item = grobid_formulas[match_index] if match_index is not None else None
            if match_index is not None:
                used_grobid.add(match_index)

            stem = f"formula_{index:03d}"
            image_path = output_dir / f"{stem}.png"
            crop = crop_region(
                pdf_path,
                provenance=item.get("provenance") or [],
                destination=image_path,
                scale=self.settings.formula_crop_scale,
                padding_points=self.settings.formula_crop_padding_points,
            )
            image_asset: dict[str, Any] | None = None
            if crop.get("status") == "saved":
                image_asset = {
                    "path": relative_posix(image_path, package_dir),
                    "width": crop.get("width"),
                    "height": crop.get("height"),
                    "size_bytes": crop.get("size_bytes"),
                    "page": crop.get("page"),
                    "source": "docling_provenance_crop",
                }
            else:
                warnings.append(f"{stem}: {crop.get('error')}")

            parser_candidates = [
                value
                for value in [
                    item.get("text"),
                    item.get("original"),
                    grobid_item.get("text") if grobid_item else None,
                ]
                if isinstance(value, str) and value.strip()
            ]
            latex = str(item.get("text") or "").strip() or (
                str(grobid_item.get("text") or "").strip() if grobid_item else ""
            )
            plain_text = str(item.get("original") or "").strip() or (
                str(grobid_item.get("text") or "").strip() if grobid_item else latex
            )
            uncertain = not latex or "�" in latex or len(latex) < 2
            repair: dict[str, Any] | None = None
            if (
                uncertain
                and llm_available
                and self.settings.llm_repair_uncertain_formulas
                and llm_used < llm_budget
                and image_path.exists()
            ):
                try:
                    repair = await self.llm.transcribe_formula(
                        image_path,
                        parser_candidates=parser_candidates,
                    )
                    llm_used += 1
                    repaired_latex = str(repair.get("latex") or "").strip()
                    if repaired_latex:
                        latex = repaired_latex
                        plain_text = str(repair.get("plain_text") or plain_text)
                except Exception as exc:
                    warnings.append(f"{stem}: LLM formula transcription failed: {exc}")

            description = self._description_record(
                repair,
                element_type="formula",
            )
            if (
                description is None
                and llm_available
                and self.settings.llm_describe_all_elements
                and llm_used < llm_budget
                and image_path.exists()
            ):
                try:
                    raw_description = await self.llm.describe_formula(
                        image_path,
                        latex=latex or None,
                        plain_text=plain_text or None,
                        parser_candidates=parser_candidates,
                    )
                    description = self._description_record(
                        raw_description,
                        element_type="formula",
                    )
                    llm_used += 1
                except Exception as exc:
                    warnings.append(f"{stem}: LLM formula description failed: {exc}")

            description_assets = self._write_description_assets(
                output_dir=output_dir,
                package_dir=package_dir,
                stem=stem,
                description=description,
            )
            tex_path = output_dir / f"{stem}.tex"
            text_path = output_dir / f"{stem}.txt"
            atomic_write_text(tex_path, latex + ("\n" if latex else ""))
            atomic_write_text(text_path, plain_text + ("\n" if plain_text else ""))
            combined_latex.append(f"% {stem}\n\\[{latex}\\]\n" if latex else f"% {stem}: missing\n")
            region = region_from_docling(item.get("provenance") or [])
            formula_quality_status = (
                "repaired" if repair and latex else "accepted" if latex else "failed"
            )

            output.append(
                {
                    "id": stem,
                    "index": index,
                    "equation_number": grobid_item.get("label") if grobid_item else None,
                    "latex": latex or None,
                    "text": plain_text or None,
                    "description": description,
                    "original": item.get("original"),
                    "page": region.page if region else None,
                    "quality": {
                        "status": formula_quality_status,
                        "llm_repair": repair,
                        "parser_candidates": parser_candidates,
                    },
                    "provenance": {
                        "docling": item.get("provenance") or [],
                        "grobid_coords": grobid_item.get("coords") if grobid_item else None,
                    },
                    "alignment": {
                        "matched": grobid_item is not None,
                        "confidence": round(match_score, 4),
                        "components": match_parts,
                        "grobid_id": grobid_item.get("id") if grobid_item else None,
                    },
                    "assets": {
                        "image": image_asset,
                        "latex": relative_posix(tex_path, package_dir),
                        "text": relative_posix(text_path, package_dir),
                        **description_assets,
                    },
                    "sources": {
                        "docling_id": item.get("id"),
                        "grobid": grobid_item,
                    },
                }
            )

        for grobid_index, grobid_item in enumerate(grobid_formulas):
            if grobid_index in used_grobid:
                continue
            index = len(output) + 1
            stem = f"formula_{index:03d}"
            image_path = output_dir / f"{stem}.png"
            crop = crop_grobid_region(
                pdf_path,
                coords=grobid_item.get("coords"),
                destination=image_path,
                scale=self.settings.formula_crop_scale,
                padding_points=self.settings.formula_crop_padding_points,
            )
            image_asset = None
            if crop.get("status") == "saved":
                image_asset = {
                    "path": relative_posix(image_path, package_dir),
                    "width": crop.get("width"),
                    "height": crop.get("height"),
                    "size_bytes": crop.get("size_bytes"),
                    "page": crop.get("page"),
                    "source": "grobid_provenance_crop",
                }
            else:
                warnings.append(f"{stem}: {crop.get('error')}")

            plain_text = str(grobid_item.get("text") or "").strip()
            latex = plain_text
            repair = None
            if (
                llm_available
                and self.settings.llm_repair_uncertain_formulas
                and llm_used < llm_budget
                and image_path.exists()
            ):
                try:
                    repair = await self.llm.transcribe_formula(
                        image_path, parser_candidates=[plain_text] if plain_text else []
                    )
                    llm_used += 1
                    repaired_latex = str(repair.get("latex") or "").strip()
                    if repaired_latex:
                        latex = repaired_latex
                        plain_text = str(repair.get("plain_text") or plain_text)
                except Exception as exc:
                    warnings.append(f"{stem}: LLM formula transcription failed: {exc}")

            parser_candidates = [plain_text] if plain_text else []
            description = self._description_record(
                repair,
                element_type="formula",
            )
            if (
                description is None
                and llm_available
                and self.settings.llm_describe_all_elements
                and llm_used < llm_budget
                and image_path.exists()
            ):
                try:
                    raw_description = await self.llm.describe_formula(
                        image_path,
                        latex=latex or None,
                        plain_text=plain_text or None,
                        parser_candidates=parser_candidates,
                    )
                    description = self._description_record(
                        raw_description,
                        element_type="formula",
                    )
                    llm_used += 1
                except Exception as exc:
                    warnings.append(f"{stem}: LLM formula description failed: {exc}")

            description_assets = self._write_description_assets(
                output_dir=output_dir,
                package_dir=package_dir,
                stem=stem,
                description=description,
            )
            tex_path = output_dir / f"{stem}.tex"
            text_path = output_dir / f"{stem}.txt"
            atomic_write_text(tex_path, latex + ("\n" if latex else ""))
            atomic_write_text(text_path, plain_text + ("\n" if plain_text else ""))
            combined_latex.append(f"% {stem}\n\\[{latex}\\]\n" if latex else f"% {stem}: missing\n")
            grobid_regions = regions_from_grobid(grobid_item.get("coords"))
            output.append(
                {
                    "id": stem,
                    "index": index,
                    "equation_number": grobid_item.get("label"),
                    "latex": latex or None,
                    "text": plain_text or None,
                    "description": description,
                    "original": grobid_item.get("text"),
                    "page": grobid_regions[0].page if grobid_regions else None,
                    "quality": {
                        "status": "repaired" if repair and latex else "unverified",
                        "llm_repair": repair,
                        "parser_candidates": [grobid_item.get("text")],
                        "warning": (
                            "GROBID formula text is stored as a LaTeX candidate but was not "
                            "produced by Docling formula enrichment."
                        ),
                    },
                    "provenance": {"docling": [], "grobid_coords": grobid_item.get("coords")},
                    "alignment": {
                        "matched": False,
                        "confidence": 0.0,
                        "components": {},
                        "grobid_id": grobid_item.get("id"),
                        "status": "grobid_only",
                    },
                    "assets": {
                        "image": image_asset,
                        "latex": relative_posix(tex_path, package_dir),
                        "text": relative_posix(text_path, package_dir),
                        **description_assets,
                    },
                    "sources": {"docling_id": None, "grobid": grobid_item},
                }
            )
        return output, warnings, llm_used, "\n".join(combined_latex)

    def _master_latex(
        self,
        figures: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        formulas: list[dict[str, Any]],
    ) -> str:
        lines = [
            r"\documentclass{article}",
            r"\usepackage{graphicx}",
            r"\usepackage{booktabs}",
            r"\usepackage{amsmath}",
            r"\begin{document}",
            r"\input{formulas.tex}",
            r"\input{tables.tex}",
        ]
        if figures:
            lines.append("% Figure assets are relative to the package root.")
            for figure in figures:
                image = ((figure.get("assets") or {}).get("image") or {}).get("path")
                if image:
                    lines.extend(
                        [
                            r"\begin{figure}[htbp]",
                            r"\centering",
                            rf"\includegraphics[width=0.9\linewidth]{{../{image}}}",
                            rf"\caption{{{latex_escape(figure.get('caption') or '')}}}",
                            r"\end{figure}",
                        ]
                    )
        lines.extend([r"\end{document}", ""])
        return "\n".join(lines)
