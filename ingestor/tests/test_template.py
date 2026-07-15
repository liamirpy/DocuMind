from __future__ import annotations

from typing import Any

from documind_ingestor.opensearch_client import install_index_template


class _Indices:
    def __init__(self) -> None:
        self.call: dict[str, Any] | None = None

    def put_index_template(self, **kwargs: Any) -> None:
        self.call = kwargs


class _Client:
    def __init__(self) -> None:
        self.indices = _Indices()


def test_install_index_template() -> None:
    client = _Client()
    body = {"index_patterns": ["documind-chunks-*"]}

    install_index_template(
        client,
        name="documind-chunks-template",
        body=body,
        request_timeout_seconds=30,
    )

    assert client.indices.call == {
        "name": "documind-chunks-template",
        "body": body,
        "request_timeout": 30,
    }
