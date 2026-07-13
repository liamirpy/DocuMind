from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.canonical.models import CanonicalDocument
from app.canonical.reader import load_canonical_document


@dataclass(frozen=True)
class InputPackage:
    """Read-only view of one output directory produced by the PDF package."""

    root: Path
    canonical_path: Path
    canonical: CanonicalDocument

    def resolve_asset(self, relative_path: str | Path | None) -> Path | None:
        """Resolve a canonical asset path while preventing directory traversal."""

        if relative_path is None:
            return None
        raw = str(relative_path).strip()
        if not raw:
            return None

        root = self.root.resolve()
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve()

        if candidate != root and root not in candidate.parents:
            raise ValueError(f"Asset path escapes the input directory: {relative_path}")
        return candidate

    def read_text(self, relative_path: str | Path | None) -> str | None:
        path = self.resolve_asset(relative_path)
        if path is None or not path.is_file():
            return None
        value = path.read_text(encoding="utf-8", errors="replace").strip()
        return value or None

    def read_json(self, relative_path: str | Path | None) -> dict[str, Any] | None:
        path = self.resolve_asset(relative_path)
        if path is None or not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Expected a JSON object in asset file: {path}")
        return payload

    def first_existing_text(
        self,
        candidates: list[str | Path | None],
    ) -> tuple[str | None, str | None]:
        """Return the first non-empty text plus the relative source path used."""

        for candidate in candidates:
            if candidate is None:
                continue
            value = self.read_text(candidate)
            if value:
                return value, str(candidate)
        return None, None

    def first_existing_json(
        self,
        candidates: list[str | Path | None],
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Return the first JSON object plus the relative source path used."""

        for candidate in candidates:
            if candidate is None:
                continue
            path = self.resolve_asset(candidate)
            if path is None or not path.is_file():
                continue
            return self.read_json(candidate), str(candidate)
        return None, None


def load_input_package(
    directory: str | Path,
    *,
    canonical_filename: str = "canonical_document.json",
) -> InputPackage:
    """Load a PDF output directory without modifying any file in it."""

    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"PDF output directory not found: {root}")

    canonical_path = root / canonical_filename
    canonical = load_canonical_document(canonical_path)
    return InputPackage(
        root=root,
        canonical_path=canonical_path.resolve(),
        canonical=canonical,
    )
