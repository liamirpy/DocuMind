import re
from collections.abc import Callable
from difflib import SequenceMatcher
from typing import Any

from app.canonical.coordinates import region_from_docling, regions_from_grobid

_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def normalize_text(value: str | None) -> str:
    return _TOKEN_RE.sub(" ", (value or "").lower()).strip()


def text_similarity(left: str | None, right: str | None) -> float:
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def first_page_from_docling(item: dict[str, Any]) -> int | None:
    region = region_from_docling(item.get("provenance") or item.get("prov") or [])
    return region.page if region else None


def first_page_from_grobid(item: dict[str, Any]) -> int | None:
    regions = regions_from_grobid(item.get("coords"))
    return regions[0].page if regions else None


def best_match(
    source: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    source_text: Callable[[dict[str, Any]], str | None],
    candidate_text: Callable[[dict[str, Any]], str | None],
    source_page: Callable[[dict[str, Any]], int | None] = first_page_from_docling,
    candidate_page: Callable[[dict[str, Any]], int | None] = first_page_from_grobid,
    used_indexes: set[int] | None = None,
    source_index: int | None = None,
) -> tuple[int | None, float, dict[str, float]]:
    used_indexes = used_indexes or set()
    best_index: int | None = None
    best_score = -1.0
    best_parts: dict[str, float] = {}

    for index, candidate in enumerate(candidates):
        if index in used_indexes:
            continue

        similarity = text_similarity(source_text(source), candidate_text(candidate))
        left_page = source_page(source)
        right_page = candidate_page(candidate)
        page_score = 0.0
        if left_page is not None and right_page is not None:
            page_score = (
                1.0
                if left_page == right_page
                else max(
                    0.0,
                    1.0 - 0.5 * abs(left_page - right_page),
                )
            )

        order_score = 0.0
        if source_index is not None:
            order_score = max(0.0, 1.0 - 0.25 * abs(source_index - index))

        score = (0.60 * similarity) + (0.25 * page_score) + (0.15 * order_score)
        if score > best_score:
            best_index = index
            best_score = score
            best_parts = {
                "text_similarity": round(similarity, 4),
                "page_score": round(page_score, 4),
                "order_score": round(order_score, 4),
            }

    if best_score < 0.25:
        return None, max(best_score, 0.0), best_parts
    return best_index, best_score, best_parts
