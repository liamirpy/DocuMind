from __future__ import annotations

import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.settings import ApiSettings


def _settings(tmp_path: Path) -> ApiSettings:
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    input_root.mkdir()
    output_root.mkdir()
    sample = Path(__file__).parents[1] / "examples" / "sample_pdf_output"
    shutil.copytree(sample, input_root / "VRU_without_LLM")
    return ApiSettings(
        indexer_input_root=input_root,
        indexer_output_root=output_root,
        documind_input_root_host=Path("/srv/DocuMind"),
        documind_output_root_host=Path("/srv/DocuMind/indexer-output"),
        embedding_provider="development_hash",
        embedding_model_name="development-hash-v1",
        embedding_expected_dimensions=32,
        embedding_development_hash_dimensions=32,
        embedding_show_progress_bar=False,
        max_concurrent_jobs=1,
        model_preload=False,
    )


def _wait(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/v1/indexing/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_indexing_job_accepts_host_paths_and_writes_output(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/v1/indexing/jobs",
            json={
                "user_name": "user_123",
                "document_id": "doc_456",
                "input_directory": "/srv/DocuMind/VRU_without_LLM",
                "output_directory": "/srv/DocuMind/indexer-output/doc_456",
            },
        )
        assert response.status_code == 202, response.text
        payload = _wait(client, response.json()["job_id"])
        assert payload["status"] == "succeeded", payload
        assert payload["result"]["embedding_dimensions"] == 32
        output_file = tmp_path / "output" / "doc_456" / "chunks.json"
        assert output_file.is_file()


def test_query_embedding_endpoint_uses_configured_provider(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/v1/embeddings/query",
            json={"query_text": "How does the VR workflow work?"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["dimensions"] == 32
        assert len(payload["embedding"]) == 32


def test_health_ready_reports_storage_paths(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["details"]["storage_ready"] is True
        assert payload["details"]["job_state_root"] == str(settings.job_state_root)


def test_rejects_paths_outside_mounted_roots(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/v1/indexing/jobs",
            json={
                "user_id": "user_123",
                "document_id": "doc_456",
                "input_directory": "/etc",
                "output_directory": "/srv/DocuMind/indexer-output/doc_456",
            },
        )
        assert response.status_code == 422


def test_recreates_missing_job_state_directory_before_persisting(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)

    with TestClient(app) as client:
        shutil.rmtree(settings.job_state_root)

        response = client.post(
            "/v1/indexing/jobs",
            json={
                "user_id": "user_123",
                "document_id": "doc_456",
                "input_directory": "/srv/DocuMind/VRU_without_LLM",
                "output_directory": "/srv/DocuMind/indexer-output/doc_456",
            },
        )

        assert response.status_code == 202, response.text
        payload = _wait(client, response.json()["job_id"])
        assert payload["status"] == "succeeded", payload
        assert settings.job_state_root.is_dir()
