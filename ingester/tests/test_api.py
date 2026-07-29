from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient

from documind_ingestor.api import app

client = TestClient(app)


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ingest_accepts_direct_chunks_upload(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("OPENSEARCH_EMBEDDING_DIMENSIONS", "32")

    def fake_ingest(config):
        captured["content"] = config.input_path.read_bytes()
        captured["index"] = config.index
        captured["dimensions"] = config.expected_embedding_dimensions
        captured["dry_run"] = config.dry_run
        captured["title"] = config.metadata.document_title
        captured["allowed_root"] = config.allowed_input_root
        assert config.input_path.is_relative_to(config.allowed_input_root)
        return {
            "status": "validated",
            "input_file": str(config.input_path),
            "canonical_file": None,
            "document_id": "doc-123",
        }

    monkeypatch.setattr("documind_ingestor.api.ingest_chunks", fake_ingest)
    response = client.post(
        "/ingest",
        files={"payload": ("chunks.json", b'{"hello":"world"}', "application/json")},
        data={
            "parameters": json.dumps(
                {
                    "index": "documind-chunks-test",
                    "dry_run": True,
                    "document_title": "API title",
                }
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "validated"
    assert body["uploaded_file"] == "chunks.json"
    assert body["input_file"] == "chunks.json"
    assert captured["content"] == b'{"hello":"world"}'
    assert captured["index"] == "documind-chunks-test"
    assert captured["dimensions"] == 32
    assert captured["dry_run"] is True
    assert captured["title"] == "API title"


def test_ingest_accepts_zip_and_auto_discovers_chunks(monkeypatch) -> None:
    captured: dict[str, object] = {}
    archive = _zip_bytes(
        {
            "doc-457/chunks.json": b'{"kind":"chunks"}',
            "doc-457/canonical_document.json": b'{"kind":"canonical"}',
        }
    )

    def fake_ingest(config):
        captured["chunks_name"] = config.input_path.name
        captured["chunks_parent"] = config.input_path.parent.name
        captured["content"] = config.input_path.read_bytes()
        captured["root"] = config.allowed_input_root
        return {
            "status": "validated",
            "input_file": str(config.input_path),
            "canonical_file": str(config.input_path.parent / "canonical_document.json"),
        }

    monkeypatch.setattr("documind_ingestor.api.ingest_chunks", fake_ingest)
    response = client.post(
        "/ingest",
        files={"payload": ("doc-457.zip", archive, "application/zip")},
        data={"parameters": '{"dry_run":true}'},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["uploaded_file"] == "doc-457.zip"
    assert body["input_file"] == "doc-457.zip!/doc-457/chunks.json"
    assert body["canonical_file"] == "doc-457.zip!/doc-457/canonical_document.json"
    assert captured["chunks_name"] == "chunks.json"
    assert captured["chunks_parent"] == "doc-457"
    assert captured["content"] == b'{"kind":"chunks"}'


def test_ingest_selects_directory_inside_zip(monkeypatch) -> None:
    selected: dict[str, str] = {}
    archive = _zip_bytes(
        {
            "first/chunks.json": b"first",
            "second/chunks.json": b"second",
        }
    )

    def fake_ingest(config):
        selected["value"] = config.input_path.read_text()
        return {
            "status": "validated",
            "input_file": str(config.input_path),
            "canonical_file": None,
        }

    monkeypatch.setattr("documind_ingestor.api.ingest_chunks", fake_ingest)
    response = client.post(
        "/ingest",
        files={"payload": ("documents.zip", archive, "application/zip")},
        data={"parameters": '{"chunks_path":"second","dry_run":true}'},
    )

    assert response.status_code == 200
    assert selected["value"] == "second"


def test_ingest_rejects_zip_path_traversal(monkeypatch) -> None:
    monkeypatch.setattr(
        "documind_ingestor.api.ingest_chunks",
        lambda config: {"status": "validated"},
    )
    archive = _zip_bytes({"../secret.json": b"secret", "chunks.json": b"{}"})

    response = client.post(
        "/ingest",
        files={"payload": ("unsafe.zip", archive, "application/zip")},
        data={"parameters": "{}"},
    )

    assert response.status_code == 400
    assert "relative path" in response.json()["detail"]


def test_ingest_requires_chunks_path_when_zip_contains_multiple_files(monkeypatch) -> None:
    monkeypatch.setattr(
        "documind_ingestor.api.ingest_chunks",
        lambda config: {"status": "validated"},
    )
    archive = _zip_bytes(
        {
            "first/chunks.json": b"first",
            "second/chunks.json": b"second",
        }
    )

    response = client.post(
        "/ingest",
        files={"payload": ("documents.zip", archive, "application/zip")},
        data={"parameters": "{}"},
    )

    assert response.status_code == 400
    assert "Multiple chunks.json files" in response.json()["detail"]


def test_ingest_requires_configured_api_key(monkeypatch) -> None:
    monkeypatch.setenv("INGESTOR_API_KEY", "test-secret")

    response = client.post(
        "/ingest",
        files={"payload": ("chunks.json", b"{}", "application/json")},
        data={"parameters": '{"dry_run":true}'},
    )
    assert response.status_code == 401

    monkeypatch.setattr(
        "documind_ingestor.api.ingest_chunks",
        lambda config: {
            "status": "validated",
            "input_file": str(config.input_path),
            "canonical_file": None,
        },
    )
    response = client.post(
        "/ingest",
        headers={"X-API-Key": "test-secret"},
        files={"payload": ("chunks.json", b"{}", "application/json")},
        data={"parameters": '{"dry_run":true}'},
    )
    assert response.status_code == 200


def test_direct_json_can_include_separate_canonical_file(monkeypatch) -> None:
    captured: dict[str, bytes] = {}

    def fake_ingest(config):
        captured["chunks"] = config.input_path.read_bytes()
        captured["canonical"] = config.canonical_json.read_bytes()
        return {
            "status": "validated",
            "input_file": str(config.input_path),
            "canonical_file": str(config.canonical_json),
        }

    monkeypatch.setattr("documind_ingestor.api.ingest_chunks", fake_ingest)
    response = client.post(
        "/ingest",
        files={
            "payload": ("chunks.json", b'{"chunks":[]}', "application/json"),
            "canonical_file": (
                "canonical_document.json",
                b'{"document_id":"doc"}',
                "application/json",
            ),
        },
        data={"parameters": '{"dry_run":true}'},
    )

    assert response.status_code == 200
    assert captured["chunks"] == b'{"chunks":[]}'
    assert captured["canonical"] == b'{"document_id":"doc"}'
