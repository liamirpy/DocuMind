from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any

from app.canonical.models import CanonicalDescription


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def unique_nonempty(values: Iterable[Any]) -> list[str]:
    cleaned = [clean_text(value) for value in values]
    return list(dict.fromkeys(value for value in cleaned if value))


def description_to_dict(
    description: CanonicalDescription | str | dict[str, Any] | None,
) -> dict[str, Any]:
    if description is None:
        return {}
    if isinstance(description, CanonicalDescription):
        return description.model_dump(mode="json", exclude_none=True)
    if isinstance(description, str):
        value = clean_text(description)
        return {"text": value} if value else {}
    if isinstance(description, dict):
        return dict(description)
    return {}


def merge_description(
    canonical_description: CanonicalDescription | str | None,
    sidecar_description: dict[str, Any] | None,
    *,
    prefer_sidecar: bool,
) -> dict[str, Any]:
    """Merge canonical and sidecar descriptions without discarding nested details."""

    canonical_payload = description_to_dict(canonical_description)
    sidecar_payload = description_to_dict(sidecar_description)
    first, second = (
        (canonical_payload, sidecar_payload)
        if prefer_sidecar
        else (sidecar_payload, canonical_payload)
    )
    merged = dict(first)
    for key, value in second.items():
        if key == "details" and isinstance(value, dict):
            existing = merged.get("details")
            details = dict(existing) if isinstance(existing, dict) else {}
            details.update(value)
            merged["details"] = details
        elif value not in (None, "", [], {}):
            merged[key] = value
    return merged


def make_chunk_id(
    *,
    user_id: str,
    document_id: str,
    source_type: str,
    chunk_role: str,
    source_ids: list[str],
    section_id: str | None,
    parent_chunk_id: str | None,
    content_hash: str,
    chunker_version: str,
) -> str:
    return sha256_text(
        "|".join(
            [
                user_id,
                document_id,
                source_type,
                chunk_role,
                ",".join(source_ids),
                section_id or "",
                parent_chunk_id or "",
                content_hash,
                chunker_version,
            ]
        )
    )


def page_range(pages: Iterable[int | None]) -> tuple[int | None, int | None]:
    valid = [page for page in pages if page is not None]
    if not valid:
        return None, None
    return min(valid), max(valid)


def path_text(parts: Iterable[str]) -> str:
    return " > ".join(unique_nonempty(parts))


def humanize_key(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return clean_text(value)


def format_detail_value(value: Any) -> str:
    """Render LLM detail values into compact, embedding-friendly text."""

    if value in (None, "", [], {}):
        return ""
    if isinstance(value, list):
        rendered: list[str] = []
        for item in value:
            if isinstance(item, dict):
                if "symbol" in item:
                    symbol = clean_text(item.get("symbol"))
                    role = clean_text(item.get("visible_role") or item.get("role"))
                    rendered.append(f"{symbol} ({role})" if role else symbol)
                else:
                    pairs: list[str] = []
                    for key, nested in item.items():
                        nested_text = format_detail_value(nested)
                        if nested_text:
                            pairs.append(f"{humanize_key(str(key))}: {nested_text}")
                    if pairs:
                        rendered.append(", ".join(pairs))
            else:
                text = _format_scalar(item)
                if text:
                    rendered.append(text)
        return "; ".join(unique_nonempty(rendered))
    if isinstance(value, dict):
        pairs: list[str] = []
        for key, nested in value.items():
            nested_text = format_detail_value(nested)
            if nested_text:
                pairs.append(f"{humanize_key(str(key))}: {nested_text}")
        return "; ".join(pairs)
    return _format_scalar(value)


def detail_lines(details: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in details.items():
        rendered = format_detail_value(value)
        if rendered:
            lines.append(f"{humanize_key(str(key))}: {rendered}")
    return lines


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


_REFERENCE_NUMBER_PREFIX = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[ivxlcdm]+)[\s.):-]+", re.IGNORECASE)


def normalize_section_name(value: str) -> str:
    cleaned = _REFERENCE_NUMBER_PREFIX.sub("", clean_text(value)).lower()
    return re.sub(r"[^a-z0-9]+", " ", cleaned).strip()


def is_reference_section(section_path: Iterable[str], configured_names: Iterable[str]) -> bool:
    names = {normalize_section_name(name) for name in configured_names if clean_text(name)}
    for part in section_path:
        normalized = normalize_section_name(part)
        if normalized in names:
            return True
    return False
