from pathlib import Path
from typing import Any

import pymupdf
import pytest

from app.canonical.builder import CanonicalPackageBuilder
from app.config import Settings


class FakeExtractor:
    async def download_asset(self, asset_url: str, destination: Path) -> None:
        raise AssertionError(f"Unexpected asset download: {asset_url} -> {destination}")


class FakeLlm:
    async def is_alive(self) -> bool:
        return True

    async def describe_figure(self, image_path: Path, *, caption: str | None) -> dict[str, Any]:
        return {
            "description": "A visible workflow diagram.",
            "summary": "Workflow diagram.",
            "figure_type": "diagram",
            "visible_text": [],
            "key_observations": ["Two connected blocks are visible."],
            "confidence": 0.9,
            "warnings": [],
        }

    async def describe_table(
        self,
        image_path: Path,
        *,
        caption: str | None,
        columns: list[str],
        rows: list[list[str]],
    ) -> dict[str, Any]:
        return {
            "description": "A table comparing model accuracy.",
            "summary": "Model comparison table.",
            "key_observations": ["Model A has an accuracy value of 0.91."],
            "visible_headers": columns,
            "confidence": 0.95,
            "warnings": [],
        }

    async def describe_formula(
        self,
        image_path: Path,
        *,
        latex: str | None,
        plain_text: str | None,
        parser_candidates: list[str],
    ) -> dict[str, Any]:
        return {
            "description": "An equality between energy and mass times the square of c.",
            "summary": "A single equality.",
            "visible_structure": ["Equality", "Superscript 2"],
            "symbols": [{"symbol": "c", "visible_role": "Squared factor"}],
            "confidence": 0.9,
            "warnings": [],
        }

    async def repair_table(self, image_path: Path, *, caption: str | None) -> dict[str, Any]:
        raise AssertionError("Structured table should not be repaired")

    async def transcribe_formula(
        self,
        image_path: Path,
        *,
        parser_candidates: list[str],
    ) -> dict[str, Any]:
        raise AssertionError("Valid formula should not be retranscribed")


@pytest.mark.asyncio
async def test_llm_describes_every_visual_element(tmp_path: Path) -> None:
    pdf_path = tmp_path / "article.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=800)
    page.insert_text((60, 100), "Body", fontsize=12)
    page.insert_text((60, 200), "E = mc^2", fontsize=16)
    page.draw_rect(pymupdf.Rect(60, 300, 300, 400))
    page.insert_text((70, 325), "Model Accuracy", fontsize=12)
    page.insert_text((70, 355), "A 0.91", fontsize=12)
    page.draw_rect(pymupdf.Rect(350, 300, 550, 450))
    page.insert_text((365, 330), "Figure", fontsize=12)
    pdf.save(pdf_path)
    pdf.close()

    extraction: dict[str, Any] = {
        "schema_version": "0.2.0",
        "request_id": "request-llm",
        "status": "completed",
        "document": {
            "filename": "article.pdf",
            "size_bytes": pdf_path.stat().st_size,
            "sha256": "c" * 64,
        },
        "warnings": [],
        "docling": {
            "status": "completed",
            "version": "test",
            "stats": {"tables": 1, "pictures": 1, "formulas": 1},
            "raw": {
                "markdown": "Body\n",
                "document_json": {
                    "name": "Article",
                    "texts": [
                        {"self_ref": "#/texts/0", "label": "text", "text": "Body", "prov": []},
                        {
                            "self_ref": "#/texts/1",
                            "label": "formula",
                            "text": "E = mc^2",
                            "orig": "E = mc²",
                            "prov": [
                                {
                                    "page_no": 1,
                                    "bbox": {
                                        "l": 50,
                                        "t": 630,
                                        "r": 190,
                                        "b": 570,
                                        "coord_origin": "BOTTOMLEFT",
                                    },
                                }
                            ],
                        },
                    ],
                    "tables": [
                        {
                            "self_ref": "#/tables/0",
                            "captions": [],
                            "prov": [
                                {
                                    "page_no": 1,
                                    "bbox": {
                                        "l": 60,
                                        "t": 500,
                                        "r": 300,
                                        "b": 400,
                                        "coord_origin": "BOTTOMLEFT",
                                    },
                                }
                            ],
                            "data": {
                                "num_rows": 2,
                                "num_cols": 2,
                                "table_cells": [
                                    {
                                        "text": "Model",
                                        "start_row_offset_idx": 0,
                                        "end_row_offset_idx": 1,
                                        "start_col_offset_idx": 0,
                                        "end_col_offset_idx": 1,
                                        "column_header": True,
                                    },
                                    {
                                        "text": "Accuracy",
                                        "start_row_offset_idx": 0,
                                        "end_row_offset_idx": 1,
                                        "start_col_offset_idx": 1,
                                        "end_col_offset_idx": 2,
                                        "column_header": True,
                                    },
                                    {
                                        "text": "A",
                                        "start_row_offset_idx": 1,
                                        "end_row_offset_idx": 2,
                                        "start_col_offset_idx": 0,
                                        "end_col_offset_idx": 1,
                                    },
                                    {
                                        "text": "0.91",
                                        "start_row_offset_idx": 1,
                                        "end_row_offset_idx": 2,
                                        "start_col_offset_idx": 1,
                                        "end_col_offset_idx": 2,
                                    },
                                ],
                            },
                        }
                    ],
                    "pictures": [],
                },
            },
            "parsed": {
                "formulas": [
                    {
                        "id": "#/texts/1",
                        "text": "E = mc^2",
                        "original": "E = mc²",
                        "provenance": [
                            {
                                "page_no": 1,
                                "bbox": {
                                    "l": 50,
                                    "t": 630,
                                    "r": 190,
                                    "b": 570,
                                    "coord_origin": "BOTTOMLEFT",
                                },
                            }
                        ],
                    }
                ],
                "tables": [
                    {
                        "id": "#/tables/0",
                        "captions": [],
                        "provenance": [
                            {
                                "page_no": 1,
                                "bbox": {
                                    "l": 60,
                                    "t": 500,
                                    "r": 300,
                                    "b": 400,
                                    "coord_origin": "BOTTOMLEFT",
                                },
                            }
                        ],
                        "structure_status": "structured",
                        "asset": None,
                    }
                ],
                "pictures": [
                    {
                        "id": "#/pictures/0",
                        "captions": [],
                        "provenance": [
                            {
                                "page_no": 1,
                                "bbox": {
                                    "l": 350,
                                    "t": 500,
                                    "r": 550,
                                    "b": 350,
                                    "coord_origin": "BOTTOMLEFT",
                                },
                            }
                        ],
                        "asset": None,
                    }
                ],
                "counts": {"tables": 1, "pictures": 1, "formulas": 1},
            },
        },
        "grobid": {
            "status": "completed",
            "version": "0.8.2",
            "stats": {},
            "raw": {
                "tei_xml": "<TEI xmlns='http://www.tei-c.org/ns/1.0'><text><body/></text></TEI>"
            },
            "parsed": {
                "metadata": {"title": "Article", "authors": []},
                "sections": [],
                "references": [],
                "figures_and_tables": [],
                "formulas": [],
                "counts": {},
            },
        },
    }

    settings = Settings(
        _env_file=None,
        output_dir=tmp_path / "outputs",
        create_zip_package=False,
        llm_enabled=True,
        llm_describe_all_elements=True,
    )
    builder = CanonicalPackageBuilder(
        settings,
        extractor=FakeExtractor(),  # type: ignore[arg-type]
        llm=FakeLlm(),  # type: ignore[arg-type]
    )
    result = await builder.build(
        pdf_path=pdf_path,
        filename="article.pdf",
        extraction=extraction,
        use_llm=True,
    )

    canonical = result["canonical"]
    figure = canonical["content"]["figures"][0]
    table = canonical["content"]["tables"][0]
    formula = canonical["content"]["formulas"][0]
    assert figure["description"]["source"] == "ollama_vision"
    assert table["description"]["text"] == "A table comparing model accuracy."
    assert formula["description"]["summary"] == "A single equality."
    package = result["package_dir"]
    assert (package / "figures/figure_001.description.json").is_file()
    assert (package / "tables/table_001.description.txt").is_file()
    assert (package / "formulas/formula_001.description.json").is_file()
    assert canonical["provenance"]["llm"]["items_processed"] == 3
