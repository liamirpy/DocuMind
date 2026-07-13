from typing import Any

from app.config import Settings


def build_quality_report(
    canonical: dict[str, Any],
    *,
    extraction: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    score = 1.0

    docling_status = (extraction.get("docling") or {}).get("status") or "failed"
    grobid_status = (extraction.get("grobid") or {}).get("status") or "failed"
    if docling_status != "completed":
        issues.append(
            {
                "severity": "critical",
                "type": "docling_failed",
                "message": "Docling extraction did not complete.",
            }
        )
        score -= 0.45
    if grobid_status != "completed":
        issues.append(
            {
                "severity": "warning",
                "type": "grobid_failed",
                "message": (
                    "GROBID extraction did not complete; scholarly metadata may be incomplete."
                ),
            }
        )
        score -= 0.20

    metadata = canonical.get("metadata") or {}
    for field in settings.metadata_required_fields:
        if not metadata.get(field):
            issues.append(
                {
                    "severity": "warning",
                    "type": "missing_metadata",
                    "field": field,
                    "message": f"Required metadata field '{field}' is missing.",
                }
            )
            score -= 0.05

    content = canonical.get("content") or {}
    text_blocks = content.get("text_blocks") or []
    if not text_blocks:
        issues.append(
            {
                "severity": "critical",
                "type": "missing_text",
                "message": "No canonical text blocks were produced.",
            }
        )
        score -= 0.30

    sections = content.get("sections") or []
    paragraphs = content.get("paragraphs") or []
    if not sections:
        issues.append(
            {
                "severity": "warning",
                "type": "missing_section_hierarchy",
                "message": "No article section hierarchy could be constructed.",
            }
        )
        score -= 0.05
    section_ids = {section.get("id") for section in sections}
    for section in sections:
        parent_id = section.get("parent_id")
        if parent_id and parent_id not in section_ids:
            issues.append(
                {
                    "severity": "warning",
                    "type": "invalid_section_parent",
                    "element_id": section.get("id"),
                    "message": "A section points to a parent that is not present.",
                }
            )
            score -= 0.025
    if sections and not paragraphs:
        issues.append(
            {
                "severity": "info",
                "type": "section_paragraphs_missing",
                "message": "Sections were found but no section-linked paragraphs were produced.",
            }
        )

    tables = content.get("tables") or []
    for table in tables:
        quality = table.get("quality") or {}
        if quality.get("status") == "failed":
            issues.append(
                {
                    "severity": "warning",
                    "type": "table_failed",
                    "element_id": table.get("id"),
                    "message": "A detected table has no usable row/column structure.",
                }
            )
            score -= 0.05
        elif quality.get("status") == "repaired":
            issues.append(
                {
                    "severity": "info",
                    "type": "table_repaired_by_llm",
                    "element_id": table.get("id"),
                    "message": (
                        "An empty table structure was reconstructed by the configured vision model."
                    ),
                }
            )
        if not ((table.get("assets") or {}).get("image")):
            issues.append(
                {
                    "severity": "info",
                    "type": "table_image_missing",
                    "element_id": table.get("id"),
                    "message": "A detected table has no local image asset.",
                }
            )

    formulas = (canonical.get("content") or {}).get("formulas") or []
    for formula in formulas:
        if not formula.get("latex"):
            issues.append(
                {
                    "severity": "warning",
                    "type": "formula_missing_latex",
                    "element_id": formula.get("id"),
                    "message": "A formula has no LaTeX representation.",
                }
            )
            score -= 0.025
        if (formula.get("quality") or {}).get("status") == "unverified":
            issues.append(
                {
                    "severity": "info",
                    "type": "formula_latex_unverified",
                    "element_id": formula.get("id"),
                    "message": (
                        "The formula was found only by GROBID; its text is retained as an "
                        "unverified LaTeX candidate."
                    ),
                }
            )
        if not ((formula.get("assets") or {}).get("image")):
            issues.append(
                {
                    "severity": "info",
                    "type": "formula_image_missing",
                    "element_id": formula.get("id"),
                    "message": "A formula image crop could not be generated.",
                }
            )

    figures = (canonical.get("content") or {}).get("figures") or []
    for figure in figures:
        if not figure.get("caption"):
            issues.append(
                {
                    "severity": "info",
                    "type": "figure_caption_missing",
                    "element_id": figure.get("id"),
                    "message": "A detected figure has no parser caption.",
                }
            )
        if not ((figure.get("assets") or {}).get("image")):
            issues.append(
                {
                    "severity": "warning",
                    "type": "figure_image_missing",
                    "element_id": figure.get("id"),
                    "message": "A detected figure has no local image asset.",
                }
            )
            score -= 0.025

    llm_info = (canonical.get("provenance") or {}).get("llm") or {}
    llm_descriptions_expected = bool(
        llm_info.get("requested_for_document")
        and llm_info.get("available")
        and settings.llm_describe_all_elements
    )
    for element_type in ("figures", "tables", "formulas"):
        for element in content.get(element_type) or []:
            alignment = element.get("alignment") or {}
            confidence = float(alignment.get("confidence") or 0.0)
            if alignment.get("matched") and confidence < 0.45:
                issues.append(
                    {
                        "severity": "info",
                        "type": "low_cross_parser_alignment",
                        "element_type": element_type,
                        "element_id": element.get("id"),
                        "confidence": confidence,
                        "message": "Docling/GROBID alignment confidence is low.",
                    }
                )
            if sections and not element.get("section_id"):
                issues.append(
                    {
                        "severity": "info",
                        "type": "element_section_unresolved",
                        "element_type": element_type,
                        "element_id": element.get("id"),
                        "message": "The element could not be linked to an article section.",
                    }
                )
            if (
                llm_descriptions_expected
                and ((element.get("assets") or {}).get("image"))
                and not element.get("description")
            ):
                issues.append(
                    {
                        "severity": "info",
                        "type": "llm_description_missing",
                        "element_type": element_type,
                        "element_id": element.get("id"),
                        "message": "An image asset exists but no Llama description was generated.",
                    }
                )

    docling_counts = ((extraction.get("docling") or {}).get("parsed") or {}).get("counts") or {}
    grobid_counts = ((extraction.get("grobid") or {}).get("parsed") or {}).get("counts") or {}
    for key in ("tables", "formulas"):
        left = int(docling_counts.get(key) or 0)
        right = int(grobid_counts.get(key) or 0)
        if max(left, right) > 0 and abs(left - right) > max(1, int(0.25 * max(left, right))):
            issues.append(
                {
                    "severity": "info",
                    "type": "cross_parser_count_mismatch",
                    "element_type": key,
                    "docling_count": left,
                    "grobid_count": right,
                    "message": f"Docling and GROBID disagree on the number of {key}.",
                }
            )

    score = round(max(0.0, min(1.0, score)), 4)
    if score >= settings.quality_green_threshold and not any(
        issue["severity"] == "critical" for issue in issues
    ):
        status = "green"
    elif score >= settings.quality_yellow_threshold:
        status = "yellow"
    else:
        status = "red"

    return {
        "status": status,
        "score": score,
        "thresholds": {
            "green": settings.quality_green_threshold,
            "yellow": settings.quality_yellow_threshold,
        },
        "issue_count": len(issues),
        "issues": issues,
        "parser_status": {
            "docling": docling_status,
            "grobid": grobid_status,
        },
    }
