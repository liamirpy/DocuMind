from pathlib import Path

import pytest

from app.utils import (
    parse_output_directories,
    resolve_output_directory,
    safe_output_folder,
    validate_output_folder,
)


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


def test_parse_output_directories_supports_commas_and_newlines(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert parse_output_directories(f"{first},\n{second}") == (
        first.resolve(),
        second.resolve(),
    )


def test_resolve_output_directory_enforces_allowed_roots(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    selected = resolve_output_directory(
        allowed_root / "case-a",
        allowed_roots=[allowed_root],
        require_absolute=True,
    )
    assert selected == (allowed_root / "case-a").resolve()

    with pytest.raises(ValueError, match="not allowed"):
        resolve_output_directory(
            tmp_path / "blocked",
            allowed_roots=[allowed_root],
            require_absolute=True,
        )


def test_resolve_output_directory_rejects_relative_api_paths() -> None:
    with pytest.raises(ValueError, match="absolute path"):
        resolve_output_directory(
            "relative/output",
            allowed_roots=[Path("/data/outputs")],
            require_absolute=True,
        )


def test_resolve_input_pdf_reads_file_below_allowed_root(tmp_path: Path) -> None:
    from app.utils import resolve_input_pdf

    allowed_root = tmp_path / "mounted"
    input_dir = allowed_root / "papers"
    input_dir.mkdir(parents=True)
    pdf = input_dir / "article.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    resolved = resolve_input_pdf(
        input_dir,
        "article.pdf",
        allowed_roots=[allowed_root],
        max_bytes=1024,
    )
    assert resolved == pdf.resolve()


@pytest.mark.parametrize(
    "filename",
    ["../article.pdf", "nested/article.pdf", r"nested\\article.pdf", "article.txt"],
)
def test_resolve_input_pdf_rejects_invalid_filename(
    tmp_path: Path,
    filename: str,
) -> None:
    from app.utils import resolve_input_pdf

    allowed_root = tmp_path / "mounted"
    allowed_root.mkdir()
    with pytest.raises(ValueError):
        resolve_input_pdf(
            allowed_root,
            filename,
            allowed_roots=[allowed_root],
        )


def test_resolve_input_pdf_rejects_directory_outside_allowlist(tmp_path: Path) -> None:
    from app.utils import resolve_input_pdf

    allowed_root = tmp_path / "allowed"
    blocked_root = tmp_path / "blocked"
    allowed_root.mkdir()
    blocked_root.mkdir()
    (blocked_root / "article.pdf").write_bytes(b"%PDF-1.4\n")

    with pytest.raises(ValueError, match="not allowed"):
        resolve_input_pdf(
            blocked_root,
            "article.pdf",
            allowed_roots=[allowed_root],
        )


def test_resolve_input_pdf_enforces_size_limit(tmp_path: Path) -> None:
    from app.utils import resolve_input_pdf

    allowed_root = tmp_path / "mounted"
    allowed_root.mkdir()
    (allowed_root / "article.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 32)

    with pytest.raises(ValueError, match="byte limit"):
        resolve_input_pdf(
            allowed_root,
            "article.pdf",
            allowed_roots=[allowed_root],
            max_bytes=8,
        )
