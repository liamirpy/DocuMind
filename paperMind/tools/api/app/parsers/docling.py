from typing import Any


def _ref_value(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("$ref", "cref", "ref"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
    return None


def _resolve_ref(document: dict[str, Any], reference: object) -> dict[str, Any] | None:
    value = _ref_value(reference)
    if not value or not value.startswith("#/"):
        return None

    node: object = document
    for part in value[2:].split("/"):
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, list) and part.isdigit():
            index = int(part)
            if index >= len(node):
                return None
            node = node[index]
        else:
            return None

    return node if isinstance(node, dict) else None


def _caption_texts(document: dict[str, Any], item: dict[str, Any]) -> list[str]:
    captions: list[str] = []
    for reference in item.get("captions") or []:
        resolved = _resolve_ref(document, reference)
        if not resolved:
            continue
        text = resolved.get("text") or resolved.get("orig")
        if isinstance(text, str) and text.strip():
            captions.append(" ".join(text.split()))
    return captions


def _first_provenance(item: dict[str, Any]) -> dict[str, Any] | None:
    provenance = item.get("prov") or []
    if provenance and isinstance(provenance[0], dict):
        return provenance[0]
    return None


def parse_docling_document(
    document: dict[str, Any],
    *,
    picture_assets: list[dict[str, Any]] | None = None,
    table_assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    picture_assets = picture_assets or []
    table_assets = table_assets or []
    picture_assets_by_id = {
        asset["element_id"]: asset
        for asset in picture_assets
        if isinstance(asset.get("element_id"), str) and asset["element_id"]
    }
    table_assets_by_id = {
        asset["element_id"]: asset
        for asset in table_assets
        if isinstance(asset.get("element_id"), str) and asset["element_id"]
    }

    formulas: list[dict[str, Any]] = []
    for item in document.get("texts") or []:
        if str(item.get("label", "")).lower() != "formula":
            continue
        formulas.append(
            {
                "id": item.get("self_ref"),
                "text": item.get("text"),
                "original": item.get("orig"),
                "provenance": item.get("prov") or [],
            }
        )

    tables: list[dict[str, Any]] = []
    table_issues: list[dict[str, Any]] = []
    for index, item in enumerate(document.get("tables") or [], start=1):
        data = item.get("data") or {}
        cells = data.get("table_cells") or []
        rows = int(data.get("num_rows") or 0)
        columns = int(data.get("num_cols") or 0)
        structure_status = (
            "structured" if rows > 0 and columns > 0 and len(cells) > 0 else "empty_structure"
        )
        item_id = item.get("self_ref") or f"table-{index}"
        parsed = {
            "id": item_id,
            "index": index,
            "captions": _caption_texts(document, item),
            "provenance": item.get("prov") or [],
            "rows": rows,
            "columns": columns,
            "cell_count": len(cells),
            "orientation": data.get("orientation"),
            "structure_status": structure_status,
            "asset": table_assets_by_id.get(item_id)
            or (table_assets[index - 1] if index <= len(table_assets) else None),
        }
        tables.append(parsed)
        if structure_status != "structured":
            table_issues.append(
                {
                    "type": "table_empty_structure",
                    "table_id": parsed["id"],
                    "index": index,
                    "provenance": parsed["provenance"],
                }
            )

    pictures: list[dict[str, Any]] = []
    for index, item in enumerate(document.get("pictures") or [], start=1):
        item_id = item.get("self_ref") or f"picture-{index}"
        pictures.append(
            {
                "id": item_id,
                "index": index,
                "captions": _caption_texts(document, item),
                "provenance": item.get("prov") or [],
                "asset": picture_assets_by_id.get(item_id)
                or (picture_assets[index - 1] if index <= len(picture_assets) else None),
            }
        )

    return {
        "formulas": formulas,
        "tables": tables,
        "pictures": pictures,
        "quality_flags": table_issues,
        "counts": {
            "formulas": len(formulas),
            "tables": len(tables),
            "tables_structured": sum(
                1 for table in tables if table["structure_status"] == "structured"
            ),
            "tables_empty_structure": len(table_issues),
            "pictures": len(pictures),
        },
    }
