from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.canonical.reader import load_canonical_document
from app.input_package.reader import load_input_package


def test_loads_typed_canonical_elements(sample_directory) -> None:
    package = load_input_package(sample_directory)
    document = package.canonical

    assert document.schema_version == "1.2.0"
    assert len(document.content.paragraphs) == 5
    assert document.content.figures[0].id == "figure_001"
    assert document.content.tables[0].columns == ["Method", "Recall", "Precision"]
    assert document.content.formulas[0].latex.startswith("score")
    assert len(document.content.references) == 2


def test_reads_sidecar_assets_from_input_directory(sample_directory) -> None:
    package = load_input_package(sample_directory)

    caption = package.read_text("figures/figure_001.caption.txt")
    description = package.read_json("figures/figure_001.description.json")

    assert caption == "VR training workflow"
    assert description is not None
    assert description["summary"].startswith("The figure shows")


def test_rejects_unknown_paragraph_section(sample_data, tmp_path) -> None:
    sample_data["content"]["paragraphs"][0]["section_id"] = "missing_section"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(sample_data), encoding="utf-8")

    with pytest.raises(ValidationError, match="unknown section IDs"):
        load_canonical_document(path)


def test_accepts_reference_coords_as_string(sample_data, tmp_path) -> None:
    sample_data["content"]["references"][0]["coords"] = (
        "10,329.74,589.67,233.29,6.91;10,329.74,607.60,176.94,6.91"
    )
    path = tmp_path / "string_coords.json"
    path.write_text(json.dumps(sample_data), encoding="utf-8")

    document = load_canonical_document(path)

    assert isinstance(document.content.references[0].coords, str)
    assert document.content.references[0].coords.startswith("10,329.74")


def test_accepts_reference_coords_as_list(sample_data, tmp_path) -> None:
    sample_data["content"]["references"][0]["coords"] = [
        "10,329.74,589.67,233.29,6.91",
        "10,329.74,607.60,176.94,6.91",
    ]
    path = tmp_path / "list_coords.json"
    path.write_text(json.dumps(sample_data), encoding="utf-8")

    document = load_canonical_document(path)

    assert isinstance(document.content.references[0].coords, list)
    assert len(document.content.references[0].coords) == 2
