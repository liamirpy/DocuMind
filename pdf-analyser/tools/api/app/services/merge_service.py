from typing import Any


def build_merged_preview(
    *,
    docling_result: dict[str, Any] | None,
    grobid_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a conservative preview without hiding either parser's raw output."""
    grobid_parsed = (grobid_result or {}).get("parsed") or {}
    docling_parsed = (docling_result or {}).get("parsed") or {}

    return {
        "merge_status": "preview_only",
        "metadata": grobid_parsed.get("metadata") or {},
        "extraction_summary": {
            "docling": (docling_result or {}).get("stats") or {},
            "grobid": (grobid_result or {}).get("stats") or {},
        },
        "docling_quality_flags": docling_parsed.get("quality_flags", []),
        "grobid_sections": grobid_parsed.get("sections", []),
        "grobid_references": grobid_parsed.get("references", []),
        "note": (
            "This is intentionally a conservative preview. Element-level alignment, "
            "quality scoring, and agentic repair belong in the next pipeline stage."
        ),
    }
