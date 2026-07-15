from __future__ import annotations

from pathlib import Path

import pytest

from documind_ingestor.cli import _resolve_chunks_json, build_parser, run


def test_cli_defaults() -> None:
    args = build_parser().parse_args(["examples/chunks.json", "--dry-run"])
    assert args.input_path == Path("examples/chunks.json")
    assert args.input_filename == "chunks.json"
    assert args.index == "documind-chunks-v1"
    assert args.expected_embedding_dimensions == 1024
    assert args.dry_run is True


def test_cli_reads_input_file_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INPUT_FILE", "/input/document-123/chunks.json")
    args = build_parser().parse_args([])
    assert args.input_path == Path("/input/document-123/chunks.json")


def test_cli_reads_input_directory_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INPUT_FILE", raising=False)
    monkeypatch.setenv("INPUT_DIR", "/input/document-123")
    args = build_parser().parse_args([])
    assert args.input_path == Path("/input/document-123")


def test_cli_argument_overrides_input_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INPUT_FILE", "/input/from-env/chunks.json")
    args = build_parser().parse_args(["/input/from-cli/chunks.json"])
    assert args.input_path == Path("/input/from-cli/chunks.json")


def test_resolve_directory_to_chunks_json(tmp_path: Path) -> None:
    chunks = tmp_path / "chunks.json"
    chunks.write_text("{}", encoding="utf-8")
    assert _resolve_chunks_json(tmp_path, input_filename="chunks.json") == chunks


def test_run_rejects_missing_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INPUT_FILE", raising=False)
    monkeypatch.delenv("INPUT_DIR", raising=False)
    monkeypatch.delenv("INPUT_DIRECTORY", raising=False)
    args = build_parser().parse_args([])
    with pytest.raises(ValueError, match="No input was provided"):
        run(args)
