from __future__ import annotations

import json
import subprocess
import sys

from app.chunking.config import ChunkingConfig


def test_config_round_trip(tmp_path) -> None:
    path = tmp_path / "config.json"
    expected = ChunkingConfig()
    expected.write_json(path)

    actual = ChunkingConfig.from_json_file(path)
    assert actual == expected


def test_cli_writes_chunks_and_embeddings_from_directory(sample_directory, tmp_path) -> None:
    output_path = tmp_path / "chunks.json"
    config_path = tmp_path / "config.json"
    config = ChunkingConfig()
    config = config.model_copy(
        update={
            "embedding": config.embedding.model_copy(
                update={
                    "provider": "development_hash",
                    "model_name": "development-hash-v1",
                    "expected_dimensions": 16,
                    "development_hash_dimensions": 16,
                    "show_progress_bar": False,
                }
            )
        }
    )
    config.write_json(config_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.cli",
            "chunk",
            str(sample_directory),
            "--user-id",
            "user_123",
            "--document-id",
            "doc_456",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["user_id"] == "user_123"
    assert payload["output_schema_version"] == "3.0.0"
    assert payload["counts"]["standalone"] == 3
    assert payload["counts"]["references"] == 2
    assert payload["counts"]["parent"] >= 1
    assert payload["embedding"]["enabled"] is True
    assert payload["embedding"]["dimensions"] == 16
    assert payload["embedding"]["embedded_chunk_count"] > 0
    assert any(chunk["embedding"] for chunk in payload["chunks"])
    assert "References preserved separately: 2" in result.stdout
    assert "Embeddings:" in result.stdout


def test_cli_can_skip_embeddings(sample_directory, tmp_path) -> None:
    output_path = tmp_path / "chunks.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.cli",
            "chunk",
            str(sample_directory),
            "--user-id",
            "user_123",
            "--document-id",
            "doc_456",
            "--skip-embedding",
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["embedding"]["enabled"] is False
    assert all(chunk["embedding"] is None for chunk in payload["chunks"])
    assert all(chunk["embedding_status"] == "disabled" for chunk in payload["chunks"])
    assert "Embeddings: disabled" in result.stdout


def test_cli_writes_query_embedding(tmp_path) -> None:
    output_path = tmp_path / "query.json"
    config_path = tmp_path / "config.json"
    config = ChunkingConfig()
    config = config.model_copy(
        update={
            "embedding": config.embedding.model_copy(
                update={
                    "provider": "development_hash",
                    "model_name": "development-hash-v1",
                    "expected_dimensions": 10,
                    "development_hash_dimensions": 10,
                    "show_progress_bar": False,
                }
            )
        }
    )
    config.write_json(config_path)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "app.cli",
            "embed-query",
            "How does the training workflow work?",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["model"] == "development-hash-v1"
    assert payload["dimensions"] == 10
    assert len(payload["embedding"]) == 10
