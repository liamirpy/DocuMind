from pathlib import Path
from typing import Any

import pymupdf

from app.canonical.coordinates import Region, region_from_docling, regions_from_grobid


def _fitz_rect(page: pymupdf.Page, region: Region, padding: float) -> pymupdf.Rect:
    if region.origin == "BOTTOMLEFT":
        x0 = region.left
        y0 = page.rect.height - region.top
        x1 = region.right
        y1 = page.rect.height - region.bottom
    elif region.origin.startswith("TOPLEFT"):
        x0 = region.left
        y0 = region.top
        x1 = region.right
        y1 = region.bottom
    else:
        raise ValueError(f"Unsupported coordinate origin: {region.origin}")

    rect = pymupdf.Rect(
        min(x0, x1) - padding,
        min(y0, y1) - padding,
        max(x0, x1) + padding,
        max(y0, y1) + padding,
    )
    return rect & page.rect


def crop_explicit_region(
    pdf_path: Path,
    *,
    region: Region | None,
    destination: Path,
    scale: float,
    padding_points: float,
) -> dict[str, Any]:
    if not region or region.page <= 0:
        return {"status": "not_available", "error": "Missing valid page region."}

    destination.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf_path) as document:
        if region.page > document.page_count:
            return {
                "status": "not_available",
                "error": f"Page {region.page} is outside the PDF page range.",
            }
        page = document[region.page - 1]
        clip = _fitz_rect(page, region, padding_points)
        if clip.is_empty or clip.width <= 0 or clip.height <= 0:
            return {"status": "not_available", "error": "Computed crop rectangle is empty."}
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(scale, scale),
            clip=clip,
            alpha=False,
        )
        pixmap.save(destination)
        return {
            "status": "saved",
            "filename": destination.name,
            "width": pixmap.width,
            "height": pixmap.height,
            "size_bytes": destination.stat().st_size,
            "page": region.page,
            "source_region": region.to_dict(),
        }


def crop_region(
    pdf_path: Path,
    *,
    provenance: list[dict[str, Any]] | None,
    destination: Path,
    scale: float,
    padding_points: float,
) -> dict[str, Any]:
    return crop_explicit_region(
        pdf_path,
        region=region_from_docling(provenance),
        destination=destination,
        scale=scale,
        padding_points=padding_points,
    )


def crop_grobid_region(
    pdf_path: Path,
    *,
    coords: str | None,
    destination: Path,
    scale: float,
    padding_points: float,
) -> dict[str, Any]:
    regions = regions_from_grobid(coords)
    return crop_explicit_region(
        pdf_path,
        region=regions[0] if regions else None,
        destination=destination,
        scale=scale,
        padding_points=padding_points,
    )
