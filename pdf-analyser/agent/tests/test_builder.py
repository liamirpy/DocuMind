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
        return False


@pytest.mark.asyncio
async def test_builder_creates_canonical_package(tmp_path: Path) -> None:
    pdf_path = tmp_path / "article.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=800)
    page.insert_text((60, 80), "Sample Paper", fontsize=18)
    page.insert_text((60, 200), "E = mc^2", fontsize=16)
    page.draw_rect(pymupdf.Rect(60, 300, 300, 400))
    page.insert_text((70, 325), "Model   Accuracy", fontsize=12)
    page.insert_text((70, 355), "A       0.91", fontsize=12)
    page.draw_rect(pymupdf.Rect(350, 300, 550, 450))
    page.insert_text((365, 330), "Figure content", fontsize=12)
    pdf.save(pdf_path)
    pdf.close()

    extraction: dict[str, Any] = {
        "schema_version": "0.2.0",
        "request_id": "request-1",
        "status": "completed",
        "document": {
            "filename": "article.pdf",
            "size_bytes": pdf_path.stat().st_size,
            "sha256": "a" * 64,
        },
        "warnings": [],
        "docling": {
            "status": "completed",
            "version": "test",
            "stats": {"tables": 1, "pictures": 1, "formulas": 1},
            "raw": {
                "markdown": "# Sample Paper\n\nBody text.\n",
                "document_json": {
                    "name": "Sample Paper",
                    "texts": [
                        {
                            "self_ref": "#/texts/0",
                            "label": "section_header",
                            "text": "Sample Paper",
                            "orig": "Sample Paper",
                            "prov": [
                                {
                                    "page_no": 1,
                                    "bbox": {
                                        "l": 50,
                                        "t": 750,
                                        "r": 250,
                                        "b": 700,
                                        "coord_origin": "BOTTOMLEFT",
                                    },
                                }
                            ],
                        },
                        {
                            "self_ref": "#/texts/1",
                            "label": "text",
                            "text": "Body text.",
                            "orig": "Body text.",
                            "prov": [],
                        },
                        {
                            "self_ref": "#/texts/2",
                            "label": "caption",
                            "text": "Table 1. Results",
                            "orig": "Table 1. Results",
                            "prov": [],
                        },
                        {
                            "self_ref": "#/texts/3",
                            "label": "caption",
                            "text": "Figure 1. Architecture",
                            "orig": "Figure 1. Architecture",
                            "prov": [],
                        },
                        {
                            "self_ref": "#/texts/4",
                            "label": "formula",
                            "text": "E = mc^2",
                            "orig": "E = mc²",
                            "prov": [
                                {
                                    "page_no": 1,
                                    "bbox": {
                                        "l": 50,
                                        "t": 630,
                                        "r": 180,
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
                            "captions": [{"$ref": "#/texts/2"}],
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
                    "pictures": [
                        {
                            "self_ref": "#/pictures/0",
                            "captions": [{"$ref": "#/texts/3"}],
                            "prov": [
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
                        }
                    ],
                },
            },
            "parsed": {
                "formulas": [
                    {
                        "id": "#/texts/4",
                        "text": "E = mc^2",
                        "original": "E = mc²",
                        "provenance": [
                            {
                                "page_no": 1,
                                "bbox": {
                                    "l": 50,
                                    "t": 630,
                                    "r": 180,
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
                        "captions": ["Table 1. Results"],
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
                        "captions": ["Figure 1. Architecture"],
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
            "stats": {"tables": 1, "figures": 1, "formulas": 1},
            "parsed": {
                "metadata": {
                    "title": "Sample Paper",
                    "authors": [{"full_name": "A. Author"}],
                    "abstract": "Abstract.",
                },
                "sections": [
                    {"id": "section-1", "heading": "Introduction", "paragraphs": ["Body text."]}
                ],
                "references": [],
                "figures_and_tables": [
                    {
                        "id": "table-1",
                        "type": "table",
                        "label": "Table 1",
                        "caption": "Results",
                        "coords": "1,60,300,240,100",
                    },
                    {
                        "id": "figure-1",
                        "type": "figure",
                        "label": "Figure 1",
                        "caption": "Architecture",
                        "coords": "1,350,300,200,150",
                    },
                ],
                "formulas": [
                    {
                        "id": "formula-1",
                        "label": "1",
                        "text": "E = mc^2",
                        "coords": "1,50,170,130,60",
                    }
                ],
                "counts": {"tables": 1, "figures": 1, "formulas": 1},
            },
        },
    }

    settings = Settings(
        _env_file=None,
        output_dir=tmp_path / "outputs",
        create_zip_package=False,
        keep_raw_extractor_response=False,
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
        use_llm=False,
    )

    package = result["package_dir"]
    canonical = result["canonical"]
    assert (package / "canonical_document.json").is_file()
    assert (package / "figures/figure_001.png").is_file()
    assert (package / "tables/table_001.csv").is_file()
    assert (package / "formulas/formula_001.png").is_file()
    assert canonical["metadata"]["title"] == "Sample Paper"
    assert canonical["content"]["tables"][0]["columns"] == ["Model", "Accuracy"]
    assert canonical["content"]["formulas"][0]["latex"] == "E = mc^2"
    assert canonical["counts"]["figures"] == 1


@pytest.mark.asyncio
async def test_builder_retains_grobid_only_elements(tmp_path: Path) -> None:
    pdf_path = tmp_path / "grobid-only.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(width=400, height=500)
    page.insert_text((40, 80), "GROBID only", fontsize=16)
    page.insert_text((40, 160), "x = y + 1", fontsize=14)
    page.draw_rect(pymupdf.Rect(40, 220, 220, 300))
    page.draw_rect(pymupdf.Rect(240, 220, 380, 360))
    pdf.save(pdf_path)
    pdf.close()

    extraction: dict[str, Any] = {
        "schema_version": "0.2.0",
        "request_id": "request-2",
        "status": "partial",
        "document": {
            "filename": "grobid-only.pdf",
            "size_bytes": pdf_path.stat().st_size,
            "sha256": "b" * 64,
        },
        "warnings": ["Docling failed"],
        "docling": {
            "status": "failed",
            "version": None,
            "stats": {},
            "raw": None,
            "parsed": None,
        },
        "grobid": {
            "status": "completed",
            "version": "0.8.2",
            "stats": {"tables": 1, "figures": 1, "formulas": 1},
            "parsed": {
                "metadata": {"title": "GROBID only", "authors": []},
                "sections": [
                    {"id": "s1", "heading": "Body", "paragraphs": ["Fallback paragraph."]}
                ],
                "references": [],
                "figures_and_tables": [
                    {
                        "id": "t1",
                        "type": "table",
                        "label": "Table 1",
                        "caption": "Only table",
                        "content": "A B 1 2",
                        "coords": "1,40,220,180,80",
                    },
                    {
                        "id": "f1",
                        "type": "figure",
                        "label": "Figure 1",
                        "caption": "Only figure",
                        "coords": "1,240,220,140,140",
                    },
                ],
                "formulas": [
                    {
                        "id": "eq1",
                        "label": "1",
                        "text": "x = y + 1",
                        "coords": "1,40,130,120,50",
                    }
                ],
                "counts": {"tables": 1, "figures": 1, "formulas": 1},
            },
        },
    }

    settings = Settings(
        _env_file=None,
        output_dir=tmp_path / "outputs",
        create_zip_package=False,
    )
    builder = CanonicalPackageBuilder(
        settings,
        extractor=FakeExtractor(),  # type: ignore[arg-type]
        llm=FakeLlm(),  # type: ignore[arg-type]
    )
    result = await builder.build(
        pdf_path=pdf_path,
        filename="grobid-only.pdf",
        extraction=extraction,
        use_llm=False,
    )
    canonical = result["canonical"]
    assert canonical["content"]["text_blocks"][0]["source"] == "grobid_fallback"
    assert canonical["counts"]["figures"] == 1
    assert canonical["counts"]["tables"] == 1
    assert canonical["counts"]["formulas"] == 1
    assert canonical["content"]["formulas"][0]["quality"]["status"] == "unverified"


@pytest.mark.asyncio
async def test_builder_uses_custom_output_folder_and_protects_existing_package(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "custom.pdf"
    pdf = pymupdf.open()
    pdf.new_page(width=200, height=200)
    pdf.save(pdf_path)
    pdf.close()

    extraction: dict[str, Any] = {
        "schema_version": "0.2.0",
        "request_id": "custom-output",
        "status": "completed",
        "document": {
            "filename": "custom.pdf",
            "size_bytes": pdf_path.stat().st_size,
            "sha256": "c" * 64,
        },
        "warnings": [],
        "docling": {
            "status": "completed",
            "version": "test",
            "stats": {},
            "raw": {"document_json": {"texts": []}},
            "parsed": {},
        },
        "grobid": {
            "status": "completed",
            "version": "test",
            "stats": {},
            "raw": {"tei_xml": None},
            "parsed": {"metadata": {}, "sections": [], "references": []},
        },
    }

    settings = Settings(
        _env_file=None,
        output_dir=tmp_path / "outputs",
        create_zip_package=False,
        overwrite_existing_package=False,
    )
    builder = CanonicalPackageBuilder(
        settings,
        extractor=FakeExtractor(),  # type: ignore[arg-type]
        llm=FakeLlm(),  # type: ignore[arg-type]
    )

    result = await builder.build(
        pdf_path=pdf_path,
        filename="custom.pdf",
        extraction=extraction,
        use_llm=False,
        output_folder="VRX_case_001",
    )

    assert result["package_name"] == "VRX_case_001"
    assert result["package_dir"] == settings.output_dir / "VRX_case_001"
    assert result["canonical"]["output"]["folder_name"] == "VRX_case_001"

    with pytest.raises(FileExistsError):
        await builder.build(
            pdf_path=pdf_path,
            filename="custom.pdf",
            extraction=extraction,
            use_llm=False,
            output_folder="VRX_case_001",
        )
