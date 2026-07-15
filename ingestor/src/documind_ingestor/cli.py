from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from documind_ingestor.opensearch_client import (
    OpenSearchChunkIngestor,
    OpenSearchIngestionError,
    build_opensearch_client,
    install_index_template,
)
from documind_ingestor.transform import (
    DocumentMetadata,
    build_opensearch_documents,
    discover_canonical_document,
    load_chunking_output,
    metadata_from_canonical,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="documind-ingestor",
        description=(
            "Read a DocuMind chunks.json file (or a directory containing it), "
            "validate it, and bulk-load it into OpenSearch."
        ),
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        type=Path,
        default=_default_input_path(),
        help=(
            "Path to chunks.json or a directory containing it. Optional when INPUT_FILE "
            "or INPUT_DIR is set."
        ),
    )
    parser.add_argument(
        "--input-filename",
        default=os.getenv("INPUT_FILENAME", "chunks.json"),
        help="Filename used when the input path is a directory (env: INPUT_FILENAME)",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("OPENSEARCH_URL", "http://localhost:9200"),
        help="OpenSearch root URL (env: OPENSEARCH_URL)",
    )
    parser.add_argument(
        "--index",
        default=os.getenv("OPENSEARCH_INDEX", "documind-chunks-v1"),
        help="Target index matching documind-chunks-* (env: OPENSEARCH_INDEX)",
    )
    parser.add_argument("--username", default=os.getenv("OPENSEARCH_USERNAME") or None)
    parser.add_argument("--password", default=os.getenv("OPENSEARCH_PASSWORD") or None)
    parser.add_argument(
        "--verify-certs",
        action=argparse.BooleanOptionalAction,
        default=_environment_bool("OPENSEARCH_VERIFY_CERTS", default=False),
    )
    parser.add_argument(
        "--ca-certs",
        type=Path,
        default=_environment_path("OPENSEARCH_CA_CERTS"),
    )
    parser.add_argument(
        "--expected-embedding-dimensions",
        type=int,
        default=int(os.getenv("OPENSEARCH_EMBEDDING_DIMENSIONS", "1024")),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("OPENSEARCH_BULK_BATCH_SIZE", "250")),
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=float(os.getenv("OPENSEARCH_REQUEST_TIMEOUT_SECONDS", "120")),
    )
    parser.add_argument(
        "--wait-timeout-seconds",
        type=float,
        default=float(os.getenv("OPENSEARCH_WAIT_TIMEOUT_SECONDS", "120")),
        help="Maximum time to wait for OpenSearch to become reachable",
    )
    parser.add_argument(
        "--wait-interval-seconds",
        type=float,
        default=float(os.getenv("OPENSEARCH_WAIT_INTERVAL_SECONDS", "2")),
        help="Delay between OpenSearch connection attempts",
    )
    parser.add_argument(
        "--install-template",
        action=argparse.BooleanOptionalAction,
        default=_environment_bool("OPENSEARCH_INSTALL_TEMPLATE", default=False),
        help="Install/update the supplied index template before ingestion",
    )
    parser.add_argument(
        "--template-name",
        default=os.getenv("OPENSEARCH_TEMPLATE_NAME", "documind-chunks-template"),
    )
    parser.add_argument(
        "--template-file",
        type=Path,
        default=_environment_path("OPENSEARCH_TEMPLATE_FILE"),
    )
    parser.add_argument(
        "--allow-missing-embeddings",
        action=argparse.BooleanOptionalAction,
        default=_environment_bool("INGESTOR_ALLOW_MISSING_EMBEDDINGS", default=False),
        help=(
            "Allow retrieval-enabled chunks without vectors "
            "(env: INGESTOR_ALLOW_MISSING_EMBEDDINGS)"
        ),
    )
    parser.add_argument(
        "--replace-document",
        action=argparse.BooleanOptionalAction,
        default=_environment_bool("INGESTOR_REPLACE_DOCUMENT", default=True),
        help=(
            "Delete stale chunks only after the new batch succeeds "
            "(env: INGESTOR_REPLACE_DOCUMENT; default: true)"
        ),
    )
    parser.add_argument(
        "--refresh",
        action=argparse.BooleanOptionalAction,
        default=_environment_bool("INGESTOR_REFRESH", default=True),
        help="Refresh the target index after ingestion (env: INGESTOR_REFRESH; default: true)",
    )
    parser.add_argument(
        "--canonical-json",
        type=Path,
        default=_environment_path("CANONICAL_JSON"),
        help=(
            "Optional canonical_document.json for title, authors, filename, and language "
            "(env: CANONICAL_JSON)"
        ),
    )
    parser.add_argument("--document-public-id", default=os.getenv("DOCUMENT_PUBLIC_ID") or None)
    parser.add_argument("--document-title", default=os.getenv("DOCUMENT_TITLE") or None)
    parser.add_argument("--document-author", action="append", default=[])
    parser.add_argument("--original-filename", default=os.getenv("ORIGINAL_FILENAME") or None)
    parser.add_argument("--file-type", default=os.getenv("FILE_TYPE") or None)
    parser.add_argument("--language", default=os.getenv("DOCUMENT_LANGUAGE") or None)
    parser.add_argument(
        "--preview-output",
        type=Path,
        default=_environment_path("PREVIEW_OUTPUT"),
        help="Write transformed OpenSearch _source documents to JSON (env: PREVIEW_OUTPUT)",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=_environment_bool("INGESTOR_DRY_RUN", default=False),
        help="Validate and transform only; do not contact OpenSearch (env: INGESTOR_DRY_RUN)",
    )
    return parser


def _environment_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Environment variable {name} must be true or false")


def _environment_path(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    return Path(value) if value else None


def _default_input_path() -> Path | None:
    return (
        _environment_path("INPUT_FILE")
        or _environment_path("INPUT_DIR")
        or _environment_path("INPUT_DIRECTORY")
    )


def _resolve_chunks_json(input_path: Path | None, *, input_filename: str) -> Path:
    if input_path is None:
        raise ValueError(
            "No input was provided. Pass a chunks.json file or directory, or set "
            "INPUT_FILE or INPUT_DIR inside the container."
        )
    if not input_filename or Path(input_filename).name != input_filename:
        raise ValueError("INPUT_FILENAME must be a filename, not a path")

    path = input_path.expanduser()
    if path.is_dir() or (not path.exists() and path.suffix.lower() != ".json"):
        path = path / input_filename

    if not path.is_file():
        raise ValueError(f"Input chunks file does not exist or is not a file: {path}")
    return path


def _load_template(path: Path | None) -> dict[str, Any]:
    if path is None:
        raise ValueError(
            "Template installation is enabled but OPENSEARCH_TEMPLATE_FILE/--template-file "
            "was not provided"
        )
    if not path.is_file():
        raise ValueError(f"OpenSearch template file does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenSearch template is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"OpenSearch template must be a JSON object: {path}")
    return payload


def _wait_for_opensearch(
    client: Any,
    *,
    url: str,
    wait_timeout_seconds: float,
    wait_interval_seconds: float,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    if wait_timeout_seconds < 0:
        raise ValueError("wait_timeout_seconds must be zero or positive")
    if wait_interval_seconds <= 0:
        raise ValueError("wait_interval_seconds must be positive")

    deadline = time.monotonic() + wait_timeout_seconds
    last_error: Exception | None = None
    attempt = 0
    while True:
        attempt += 1
        try:
            return client.info(request_timeout=request_timeout_seconds)
        except Exception as exc:  # OpenSearch client exposes several transport exception types.
            last_error = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if attempt == 1:
                print(f"Waiting for OpenSearch at {url} ...")
            time.sleep(min(wait_interval_seconds, remaining))

    raise OpenSearchIngestionError(
        f"OpenSearch at {url} did not become reachable within "
        f"{wait_timeout_seconds:g} seconds: {last_error}"
    )


def _emit_result(event: str, payload: dict[str, Any]) -> None:
    print(f"{event} {json.dumps(payload, ensure_ascii=False, sort_keys=True)}")


def run(args: argparse.Namespace) -> int:
    chunks_json = _resolve_chunks_json(args.input_path, input_filename=args.input_filename)
    output = load_chunking_output(chunks_json)
    canonical, canonical_path = discover_canonical_document(
        output,
        explicit_path=args.canonical_json,
        chunks_json_path=chunks_json,
    )
    inferred = metadata_from_canonical(canonical)
    overrides = DocumentMetadata(
        document_public_id=args.document_public_id,
        document_title=args.document_title,
        document_authors=args.document_author,
        original_filename=args.original_filename,
        file_type=args.file_type,
        language=args.language,
    )
    metadata = inferred.merged_with(overrides)
    documents = build_opensearch_documents(
        output,
        metadata=metadata,
        expected_embedding_dimensions=args.expected_embedding_dimensions,
        require_embeddings=not args.allow_missing_embeddings,
    )

    if args.preview_output is not None:
        args.preview_output.parent.mkdir(parents=True, exist_ok=True)
        args.preview_output.write_text(
            json.dumps([document.source() for document in documents], indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote transformed preview: {args.preview_output}")

    vectors = sum(document.embedding is not None for document in documents)
    print(
        f"Validated {len(documents)} chunks for user_id={output.user_id}, "
        f"document_id={output.document_id}; vectors={vectors}"
    )
    if output.references:
        print(
            f"Skipped {len(output.references)} reference records: "
            "the chunk mapping has no reference fields"
        )
    if canonical_path is not None:
        print(f"Metadata source: {canonical_path}")

    if args.dry_run:
        payload = {
            "status": "validated",
            "input_file": str(chunks_json),
            "user_id": output.user_id,
            "document_id": output.document_id,
            "chunks": len(documents),
            "vectors": vectors,
            "dry_run": True,
        }
        _emit_result("INGESTION_VALIDATED", payload)
        return 0

    client = build_opensearch_client(
        url=args.url,
        username=args.username,
        password=args.password,
        verify_certs=args.verify_certs,
        ca_certs=args.ca_certs,
        timeout_seconds=args.request_timeout_seconds,
    )
    try:
        info = _wait_for_opensearch(
            client,
            url=args.url,
            wait_timeout_seconds=args.wait_timeout_seconds,
            wait_interval_seconds=args.wait_interval_seconds,
            request_timeout_seconds=args.request_timeout_seconds,
        )
        version = info.get("version", {}).get("number", "unknown")
        print(f"Connected to OpenSearch {version} at {args.url}")

        if args.install_template:
            template = _load_template(args.template_file)
            install_index_template(
                client,
                name=args.template_name,
                body=template,
                request_timeout_seconds=args.request_timeout_seconds,
            )
            print(f"Installed/updated index template: {args.template_name}")

        result = OpenSearchChunkIngestor(
            client=client,
            index=args.index,
            expected_embedding_dimensions=args.expected_embedding_dimensions,
            batch_size=args.batch_size,
            request_timeout_seconds=args.request_timeout_seconds,
        ).ingest(
            documents,
            user_id=output.user_id,
            document_id=output.document_id,
            replace_document=args.replace_document,
            refresh=args.refresh,
        )
    finally:
        client.close()

    print(f"Indexed/upserted {result.indexed} chunks into {result.index}")
    if args.replace_document:
        print(
            f"Previous chunks={result.previous_document_chunks}; "
            f"deleted stale chunks={result.deleted_stale}"
        )

    payload = {
        "status": "done",
        "input_file": str(chunks_json),
        "opensearch_url": args.url,
        "index": result.index,
        "user_id": output.user_id,
        "document_id": output.document_id,
        "indexed": result.indexed,
        "deleted_stale": result.deleted_stale,
        "previous_document_chunks": result.previous_document_chunks,
        "refreshed": result.refreshed,
    }
    _emit_result("INGESTION_DONE", payload)
    return 0


def main() -> None:
    try:
        args = build_parser().parse_args()
        raise SystemExit(run(args))
    except (ValueError, ValidationError, OpenSearchIngestionError) as exc:
        payload = {"status": "failed", "error": str(exc)}
        print(f"ERROR: {exc}", file=sys.stderr)
        print(
            f"INGESTION_FAILED {json.dumps(payload, ensure_ascii=False, sort_keys=True)}",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    except KeyboardInterrupt:
        payload = {"status": "interrupted", "error": "Interrupted"}
        print("Interrupted", file=sys.stderr)
        print(
            f"INGESTION_FAILED {json.dumps(payload, sort_keys=True)}",
            file=sys.stderr,
        )
        raise SystemExit(130) from None
