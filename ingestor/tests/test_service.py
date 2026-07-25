from __future__ import annotations

from pathlib import Path

from documind_ingestor.service import IngestionConfig, ingest_chunks

ROOT = Path(__file__).resolve().parents[1]


def test_service_dry_run_returns_structured_result() -> None:
    payload = ingest_chunks(
        IngestionConfig(
            input_path=ROOT / "examples" / "chunks.json",
            expected_embedding_dimensions=32,
            dry_run=True,
        )
    )

    assert payload["status"] == "validated"
    assert payload["dry_run"] is True
    assert payload["chunks"] > 0
    assert payload["vectors"] > 0


def test_service_does_not_auto_read_canonical_outside_allowed_root(tmp_path: Path) -> None:
    import json
    input_root = tmp_path / "input"
    document_dir = input_root / "doc"
    document_dir.mkdir(parents=True)
    chunks_path = document_dir / "chunks.json"
    payload = json.loads((ROOT / "examples" / "chunks.json").read_text(encoding="utf-8"))

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "canonical_document.json").write_text(
        json.dumps({"schema_version": "1.2.0", "document_id": payload["document_id"]}),
        encoding="utf-8",
    )
    payload["input_directory"] = str(outside)
    chunks_path.write_text(json.dumps(payload), encoding="utf-8")

    result = ingest_chunks(
        IngestionConfig(
            input_path=chunks_path,
            allowed_input_root=input_root,
            expected_embedding_dimensions=32,
            dry_run=True,
        )
    )

    assert result["canonical_file"] is None
