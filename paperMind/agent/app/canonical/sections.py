from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any
from xml.etree import ElementTree as ET

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI_NS}


def _tag(name: str) -> str:
    return f"{{{TEI_NS}}}{name}"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _node_text(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    return _clean(" ".join(node.itertext()))


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _pages_from_coords(coords: str | None) -> list[int]:
    pages: list[int] = []
    if not coords:
        return pages
    for region in coords.split(";"):
        first = region.strip().split(",", 1)[0].strip()
        try:
            page = int(float(first))
        except (TypeError, ValueError):
            continue
        if page > 0 and page not in pages:
            pages.append(page)
    return pages


def _infer_number_and_title(title: str | None, number: str | None) -> tuple[str | None, str | None]:
    clean_title = _clean(title)
    clean_number = _clean(number)
    if clean_number or not clean_title:
        return clean_number, clean_title
    match = re.match(r"^\s*((?:\d+\.)*\d+)\s*[.)]?\s+(.+)$", clean_title)
    if not match:
        return None, clean_title
    return match.group(1), _clean(match.group(2))


def _level_from_number(number: str | None) -> int:
    if not number:
        return 1
    components = [part for part in re.split(r"[.\-]", number) if part]
    return max(1, len(components))


def _new_section(
    *,
    index: int,
    source_id: str | None,
    title: str | None,
    number: str | None,
    level: int,
    parent_id: str | None,
    path: list[str],
    head_coords: str | None,
    source: str,
) -> dict[str, Any]:
    pages = _pages_from_coords(head_coords)
    return {
        "id": f"sec_{index:03d}",
        "source_id": source_id,
        "title": title,
        "heading": title,
        "number": number,
        "level": level,
        "parent_id": parent_id,
        "path": path,
        "child_section_ids": [],
        "paragraph_ids": [],
        "figure_ids": [],
        "table_ids": [],
        "formula_ids": [],
        "text": "",
        "order": index,
        "page_start": min(pages) if pages else None,
        "page_end": max(pages) if pages else None,
        "provenance": {
            "source": source,
            "head_coords": head_coords,
        },
    }


def _finalize_ranges_and_text(
    sections: list[dict[str, Any]],
    paragraphs: list[dict[str, Any]],
) -> None:
    paragraph_by_id = {paragraph["id"]: paragraph for paragraph in paragraphs}
    section_by_id = {section["id"]: section for section in sections}

    for section in sections:
        section_paragraphs = [
            paragraph_by_id[paragraph_id]
            for paragraph_id in section.get("paragraph_ids") or []
            if paragraph_id in paragraph_by_id
        ]
        section["text"] = "\n\n".join(
            paragraph["text"] for paragraph in section_paragraphs if paragraph.get("text")
        )
        pages = [
            page
            for paragraph in section_paragraphs
            for page in (paragraph.get("page_start"), paragraph.get("page_end"))
            if isinstance(page, int)
        ]
        if pages:
            section["page_start"] = min(
                [section["page_start"]] + pages
                if isinstance(section.get("page_start"), int)
                else pages
            )
            section["page_end"] = max(
                [section["page_end"]] + pages if isinstance(section.get("page_end"), int) else pages
            )

    for section in sorted(sections, key=lambda value: int(value.get("level") or 1), reverse=True):
        parent_id = section.get("parent_id")
        if not parent_id or parent_id not in section_by_id:
            continue
        parent = section_by_id[parent_id]
        child_pages = [
            page
            for page in (section.get("page_start"), section.get("page_end"))
            if isinstance(page, int)
        ]
        if child_pages:
            existing = [
                page
                for page in (parent.get("page_start"), parent.get("page_end"))
                if isinstance(page, int)
            ]
            all_pages = existing + child_pages
            parent["page_start"] = min(all_pages)
            parent["page_end"] = max(all_pages)


def _parse_tei_structure(tei_xml: str) -> dict[str, Any]:
    root = ET.fromstring(tei_xml)
    body = root.find(".//tei:text/tei:body", NS)
    if body is None:
        return {
            "sections": [],
            "paragraphs": [],
            "source_element_to_section": {},
            "source": "grobid_tei",
        }

    sections: list[dict[str, Any]] = []
    paragraphs: list[dict[str, Any]] = []
    source_element_to_section: dict[str, str] = {}
    paragraph_index = 0

    def map_source_elements(node: ET.Element, section_id: str) -> None:
        for child in list(node):
            if child.tag == _tag("div"):
                continue
            for descendant in child.iter():
                if descendant.tag not in {_tag("figure"), _tag("formula")}:
                    continue
                source_id = descendant.get(f"{{{XML_NS}}}id")
                if source_id:
                    source_element_to_section[source_id] = section_id

    def visit_div(
        div: ET.Element,
        *,
        parent_id: str | None,
        parent_path: list[str],
        level: int,
    ) -> None:
        nonlocal paragraph_index

        head = div.find("./tei:head", NS)
        number, title = _infer_number_and_title(
            _node_text(head),
            head.get("n") if head is not None else None,
        )
        direct_paragraphs = [
            paragraph for paragraph in div.findall("./tei:p", NS) if _node_text(paragraph)
        ]
        nested_divs = div.findall("./tei:div", NS)

        # GROBID occasionally emits wrapper divs without a heading or direct text.
        # Preserve the real nested sections instead of creating a meaningless node.
        if not title and not direct_paragraphs and nested_divs:
            for nested in nested_divs:
                visit_div(
                    nested,
                    parent_id=parent_id,
                    parent_path=parent_path,
                    level=level,
                )
            return

        section_index = len(sections) + 1
        section_title = title or "Untitled section"
        path = [*parent_path, section_title]
        section = _new_section(
            index=section_index,
            source_id=div.get(f"{{{XML_NS}}}id"),
            title=section_title,
            number=number,
            level=level,
            parent_id=parent_id,
            path=path,
            head_coords=head.get("coords") if head is not None else None,
            source="grobid_tei",
        )
        sections.append(section)
        if parent_id:
            parent = next((item for item in sections if item["id"] == parent_id), None)
            if parent is not None:
                parent["child_section_ids"].append(section["id"])

        map_source_elements(div, section["id"])

        for paragraph in direct_paragraphs:
            text = _node_text(paragraph)
            if not text:
                continue
            paragraph_index += 1
            coords = paragraph.get("coords")
            pages = _pages_from_coords(coords)
            paragraph_id = f"para_{paragraph_index:05d}"
            paragraph_record = {
                "id": paragraph_id,
                "source_id": paragraph.get(f"{{{XML_NS}}}id"),
                "section_id": section["id"],
                "section_path": path,
                "order": paragraph_index,
                "text": text,
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
                "provenance": {
                    "source": "grobid_tei",
                    "coords": coords,
                },
            }
            paragraphs.append(paragraph_record)
            section["paragraph_ids"].append(paragraph_id)

            for descendant in paragraph.iter():
                if descendant.tag not in {_tag("figure"), _tag("formula")}:
                    continue
                source_id = descendant.get(f"{{{XML_NS}}}id")
                if source_id:
                    source_element_to_section[source_id] = section["id"]

        for nested in nested_divs:
            visit_div(
                nested,
                parent_id=section["id"],
                parent_path=path,
                level=level + 1,
            )

    direct_body_paragraphs = [
        paragraph for paragraph in body.findall("./tei:p", NS) if _node_text(paragraph)
    ]
    if direct_body_paragraphs:
        section = _new_section(
            index=1,
            source_id=None,
            title="Body",
            number=None,
            level=1,
            parent_id=None,
            path=["Body"],
            head_coords=None,
            source="grobid_tei_synthetic",
        )
        sections.append(section)
        for paragraph in direct_body_paragraphs:
            paragraph_index += 1
            text = _node_text(paragraph)
            if not text:
                continue
            coords = paragraph.get("coords")
            pages = _pages_from_coords(coords)
            paragraph_id = f"para_{paragraph_index:05d}"
            paragraphs.append(
                {
                    "id": paragraph_id,
                    "source_id": paragraph.get(f"{{{XML_NS}}}id"),
                    "section_id": section["id"],
                    "section_path": ["Body"],
                    "order": paragraph_index,
                    "text": text,
                    "page_start": min(pages) if pages else None,
                    "page_end": max(pages) if pages else None,
                    "provenance": {
                        "source": "grobid_tei",
                        "coords": coords,
                    },
                }
            )
            section["paragraph_ids"].append(paragraph_id)

    for div in body.findall("./tei:div", NS):
        visit_div(div, parent_id=None, parent_path=[], level=1)

    _finalize_ranges_and_text(sections, paragraphs)
    return {
        "sections": sections,
        "paragraphs": paragraphs,
        "source_element_to_section": source_element_to_section,
        "source": "grobid_tei",
    }


def _fallback_structure(flat_sections: list[dict[str, Any]]) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    paragraphs: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    paragraph_index = 0

    for source_index, source in enumerate(flat_sections, start=1):
        number, title = _infer_number_and_title(
            source.get("heading") or source.get("title"),
            source.get("number"),
        )
        level = _level_from_number(number)
        while stack and int(stack[-1].get("level") or 1) >= level:
            stack.pop()
        parent = stack[-1] if stack else None
        parent_path = list(parent.get("path") or []) if parent else []
        section_title = title or f"Untitled section {source_index}"
        section = _new_section(
            index=len(sections) + 1,
            source_id=source.get("id"),
            title=section_title,
            number=number,
            level=level,
            parent_id=parent.get("id") if parent else None,
            path=[*parent_path, section_title],
            head_coords=source.get("coords"),
            source="grobid_flat_fallback",
        )
        sections.append(section)
        if parent:
            parent["child_section_ids"].append(section["id"])
        stack.append(section)

        for value in source.get("paragraphs") or []:
            if not isinstance(value, str) or not value.strip():
                continue
            paragraph_index += 1
            paragraph_id = f"para_{paragraph_index:05d}"
            paragraphs.append(
                {
                    "id": paragraph_id,
                    "source_id": None,
                    "section_id": section["id"],
                    "section_path": list(section["path"]),
                    "order": paragraph_index,
                    "text": " ".join(value.split()),
                    "page_start": None,
                    "page_end": None,
                    "provenance": {
                        "source": "grobid_flat_fallback",
                        "coords": None,
                    },
                }
            )
            section["paragraph_ids"].append(paragraph_id)

    _finalize_ranges_and_text(sections, paragraphs)
    return {
        "sections": sections,
        "paragraphs": paragraphs,
        "source_element_to_section": {},
        "source": "grobid_flat_fallback",
    }


def build_section_structure(
    *,
    tei_xml: str | None,
    flat_sections: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if tei_xml and tei_xml.strip():
        try:
            parsed = _parse_tei_structure(tei_xml)
            if parsed["sections"]:
                return parsed
        except ET.ParseError:
            pass
    return _fallback_structure(flat_sections or [])


def build_section_tree(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for section in sections:
        node = {key: value for key, value in section.items() if key not in {"child_section_ids"}}
        node["children"] = []
        by_id[str(section["id"])] = node

    for section in sections:
        node = by_id[str(section["id"])]
        parent_id = section.get("parent_id")
        if parent_id and str(parent_id) in by_id:
            by_id[str(parent_id)]["children"].append(node)
        else:
            roots.append(node)
    return roots


def _best_title_match(title: str, sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized = _normalize(title)
    if not normalized:
        return None
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for section in sections:
        candidate = _normalize(section.get("title"))
        if not candidate:
            continue
        score = (
            1.0 if normalized == candidate else SequenceMatcher(None, normalized, candidate).ratio()
        )
        if score > best[0]:
            best = (score, section)
    return best[1] if best[0] >= 0.72 else None


def assign_text_blocks_to_sections(
    text_blocks: list[dict[str, Any]],
    *,
    sections: list[dict[str, Any]],
    paragraphs: list[dict[str, Any]],
) -> None:
    if not sections:
        return

    paragraph_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paragraph in paragraphs:
        normalized = _normalize(paragraph.get("text"))
        if normalized:
            paragraph_candidates[normalized].append(paragraph)

    section_by_id = {section["id"]: section for section in sections}
    current_section: dict[str, Any] | None = None
    used_paragraphs: set[str] = set()

    for block in text_blocks:
        label = str(block.get("label") or "").casefold()
        text = str(block.get("text") or "")
        if "section" in label and "header" in label:
            matched_section = _best_title_match(text, sections)
            if matched_section:
                current_section = matched_section

        paragraph_match: dict[str, Any] | None = None
        normalized = _normalize(text)
        for candidate in paragraph_candidates.get(normalized, []):
            if candidate["id"] not in used_paragraphs:
                paragraph_match = candidate
                break
        if paragraph_match is None and normalized:
            for paragraph in paragraphs:
                if paragraph["id"] in used_paragraphs:
                    continue
                candidate = _normalize(paragraph.get("text"))
                if not candidate:
                    continue
                if len(normalized) >= 40 and (normalized in candidate or candidate in normalized):
                    paragraph_match = paragraph
                    break

        if paragraph_match:
            used_paragraphs.add(paragraph_match["id"])
            current_section = section_by_id.get(paragraph_match["section_id"], current_section)
            block["paragraph_id"] = paragraph_match["id"]

        if current_section:
            block["section_id"] = current_section["id"]
            block["section_title"] = current_section.get("title")
            block["section_path"] = list(current_section.get("path") or [])


def _section_for_page(page: int | None, sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    if page is None:
        return None
    within = [
        section
        for section in sections
        if isinstance(section.get("page_start"), int)
        and isinstance(section.get("page_end"), int)
        and int(section["page_start"]) <= page <= int(section["page_end"])
    ]
    if within:
        return max(
            within,
            key=lambda value: (
                int(value.get("level") or 1),
                int(value.get("order") or 0),
            ),
        )
    before = [
        section
        for section in sections
        if isinstance(section.get("page_start"), int) and int(section["page_start"]) <= page
    ]
    if before:
        return max(
            before,
            key=lambda value: (
                int(value.get("page_start") or 0),
                int(value.get("level") or 1),
                int(value.get("order") or 0),
            ),
        )
    return None


def attach_elements_to_sections(
    *,
    sections: list[dict[str, Any]],
    source_element_to_section: dict[str, str],
    figures: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    formulas: list[dict[str, Any]],
) -> None:
    section_by_id = {section["id"]: section for section in sections}

    def attach(elements: list[dict[str, Any]], bucket: str) -> None:
        for element in elements:
            grobid = (element.get("sources") or {}).get("grobid") or {}
            grobid_id = grobid.get("id")
            section_id = source_element_to_section.get(str(grobid_id)) if grobid_id else None
            section = section_by_id.get(section_id) if section_id else None
            method = "grobid_tei_element_id" if section is not None else None
            confidence = 1.0 if section is not None else 0.0
            if section is None:
                page = element.get("page")
                section = _section_for_page(int(page) if isinstance(page, int) else None, sections)
                if section is not None:
                    method = "section_page_range"
                    confidence = 0.55
            if section is None:
                element["section_id"] = None
                element["section_title"] = None
                element["section_path"] = []
                element["section_assignment"] = {
                    "method": "unresolved",
                    "confidence": 0.0,
                }
                continue
            element["section_id"] = section["id"]
            element["section_title"] = section.get("title")
            element["section_path"] = list(section.get("path") or [])
            element["section_assignment"] = {
                "method": method,
                "confidence": confidence,
            }
            section.setdefault(bucket, []).append(element["id"])

    attach(figures, "figure_ids")
    attach(tables, "table_ids")
    attach(formulas, "formula_ids")
