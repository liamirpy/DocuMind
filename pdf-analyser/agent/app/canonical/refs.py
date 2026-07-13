from typing import Any


def ref_value(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("$ref", "cref", "ref"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
    return None


def resolve_ref(document: dict[str, Any], reference: object) -> dict[str, Any] | None:
    value = ref_value(reference)
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


def referenced_texts(document: dict[str, Any], references: list[object] | None) -> list[str]:
    values: list[str] = []
    for reference in references or []:
        node = resolve_ref(document, reference)
        if not node:
            continue
        value = node.get("text") or node.get("orig")
        if isinstance(value, str) and value.strip():
            values.append(" ".join(value.split()))
    return values
