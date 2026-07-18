from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from app.canonical.models import CanonicalDocument

_NORMALIZE_PATTERN = re.compile(r"[^a-z0-9]+")


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _NORMALIZE_PATTERN.sub(" ", value.casefold()).strip()


def _deduplicate_locations(locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for location in locations:
        identity = json.dumps(
            location,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(location)
    return unique


def source_locations_from_text_block(block: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert one canonical Docling text block into stored source locations."""

    provenance = block.get("provenance")
    if not isinstance(provenance, list):
        return []

    locations: list[dict[str, Any]] = []
    for item in provenance:
        if not isinstance(item, dict):
            continue

        bbox = item.get("bbox")
        location: dict[str, Any] = {
            "source": "docling",
            "source_block_id": block.get("id"),
            "source_block_index": block.get("index"),
            "label": block.get("label"),
            "page": item.get("page_no"),
        }
        if isinstance(bbox, dict):
            location["bbox"] = dict(bbox)
        charspan = item.get("charspan")
        if isinstance(charspan, (list, tuple)):
            location["charspan"] = list(charspan)

        # Keep the source block text so a later citation service can narrow a
        # chunk-level highlight to the exact source block when possible.
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            location["text"] = text.strip()

        location = {
            key: value for key, value in location.items() if value not in (None, "", [], {})
        }
        if "bbox" in location or "page" in location:
            locations.append(location)

    return locations


def paragraph_source_locations(
    canonical: CanonicalDocument,
) -> dict[str, tuple[dict[str, Any], ...]]:
    """Return Docling source locations grouped by canonical paragraph ID.

    New analyzer outputs place locations in ``paragraph.provenance``. Older
    outputs already contain the same geometry in ``content.text_blocks`` and
    may include a ``paragraph_id`` assigned by the analyzer. This function
    supports both forms and also uses a conservative unique text match as a
    fallback.
    """

    locations_by_paragraph: dict[str, list[dict[str, Any]]] = {
        paragraph.id: [] for paragraph in canonical.content.paragraphs
    }

    paragraph_ids = set(locations_by_paragraph)
    normalized_paragraphs: dict[str, list[str]] = defaultdict(list)
    paragraph_text: dict[str, str] = {}
    for paragraph in canonical.content.paragraphs:
        normalized = _normalize_text(paragraph.text)
        paragraph_text[paragraph.id] = normalized
        if normalized:
            normalized_paragraphs[normalized].append(paragraph.id)

        raw_locations = paragraph.provenance.get("source_locations")
        if isinstance(raw_locations, list):
            locations_by_paragraph[paragraph.id].extend(
                dict(location) for location in raw_locations if isinstance(location, dict)
            )

    for raw_block in canonical.content.text_blocks:
        if not isinstance(raw_block, dict):
            continue

        paragraph_id = raw_block.get("paragraph_id")
        if not isinstance(paragraph_id, str) or paragraph_id not in paragraph_ids:
            normalized_block = _normalize_text(raw_block.get("text"))
            exact_matches = normalized_paragraphs.get(normalized_block, [])
            if len(exact_matches) == 1:
                paragraph_id = exact_matches[0]
            elif len(normalized_block) >= 40:
                containing = [
                    candidate_id
                    for candidate_id, normalized_paragraph in paragraph_text.items()
                    if normalized_block in normalized_paragraph
                    or normalized_paragraph in normalized_block
                ]
                if len(containing) == 1:
                    paragraph_id = containing[0]

        if isinstance(paragraph_id, str) and paragraph_id in paragraph_ids:
            locations_by_paragraph[paragraph_id].extend(source_locations_from_text_block(raw_block))

    return {
        paragraph_id: tuple(_deduplicate_locations(locations))
        for paragraph_id, locations in locations_by_paragraph.items()
    }


def details_for_source_locations(
    locations: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    unique = _deduplicate_locations([dict(location) for location in locations])
    return {"source_locations": unique} if unique else {}


def merge_element_provenance(
    details: dict[str, Any],
    *,
    provenance: dict[str, Any],
    source_id: str,
) -> dict[str, Any]:
    """Preserve element geometry without adding it to semantic retrieval text."""

    merged = dict(details)
    existing = merged.get("source_locations")
    locations = (
        [dict(item) for item in existing if isinstance(item, dict)]
        if isinstance(existing, list)
        else []
    )

    docling = provenance.get("docling")
    if isinstance(docling, list):
        block = {
            "id": source_id,
            "label": "element",
            "provenance": docling,
        }
        locations.extend(source_locations_from_text_block(block))

    grobid_coords = provenance.get("grobid_coords")
    if isinstance(grobid_coords, str) and grobid_coords.strip():
        locations.append(
            {
                "source": "grobid",
                "source_element_id": source_id,
                "coords": grobid_coords.strip(),
            }
        )

    unique = _deduplicate_locations(locations)
    if unique:
        merged["source_locations"] = unique
    return merged
