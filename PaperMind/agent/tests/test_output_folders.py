from pathlib import Path

import pytest

from app.utils import safe_output_folder, validate_output_folder


def test_safe_output_folder_normalizes_spaces() -> None:
    assert safe_output_folder("VRX analysis 01") == "VRX_analysis_01"


@pytest.mark.parametrize(
    "value",
    ["../escape", "nested/name", r"nested\\name", ".", "..", "   ", "CON", "lpt1"],
)
def test_safe_output_folder_rejects_paths(value: str) -> None:
    with pytest.raises(ValueError):
        safe_output_folder(value)


def test_validate_output_folder_requires_canonical_name() -> None:
    assert validate_output_folder("VRX_analysis-01") == "VRX_analysis-01"
    with pytest.raises(ValueError):
        validate_output_folder("VRX analysis")


def test_custom_output_folder_stays_below_root(tmp_path: Path) -> None:
    root = tmp_path / "outputs"
    folder = safe_output_folder("case 001")
    target = (root / folder).resolve()
    assert target.is_relative_to(root.resolve())
