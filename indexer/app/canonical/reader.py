from __future__ import annotations

from pathlib import Path

from app.canonical.models import CanonicalDocument


def load_canonical_document(path: str | Path) -> CanonicalDocument:
    """Read and validate a canonical_document.json file."""

    canonical_path = Path(path)
    if not canonical_path.is_file():
        raise FileNotFoundError(f"Canonical JSON file not found: {canonical_path}")

    return CanonicalDocument.model_validate_json(canonical_path.read_bytes())
