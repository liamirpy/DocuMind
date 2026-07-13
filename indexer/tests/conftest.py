from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_directory() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "sample_pdf_output"


@pytest.fixture
def sample_path(sample_directory: Path) -> Path:
    return sample_directory / "canonical_document.json"


@pytest.fixture
def sample_data(sample_path: Path) -> dict:
    return json.loads(sample_path.read_text(encoding="utf-8"))
