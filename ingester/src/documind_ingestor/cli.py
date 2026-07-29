from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from documind_ingestor.opensearch_client import OpenSearchIngestionError
from documind_ingestor.service import IngestionConfig, ingest_chunks, resolve_chunks_json
from documind_ingestor.transform import DocumentMetadata

# Backwards-compatible private alias used by existing callers/tests.
_resolve_chunks_json = resolve_chunks_json


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
    )
    parser.add_argument(
        "--wait-interval-seconds",
        type=float,
        default=float(os.getenv("OPENSEARCH_WAIT_INTERVAL_SECONDS", "2")),
    )
    parser.add_argument(
        "--install-template",
        action=argparse.BooleanOptionalAction,
        default=_environment_bool("OPENSEARCH_INSTALL_TEMPLATE", default=False),
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
    )
    parser.add_argument(
        "--replace-document",
        action=argparse.BooleanOptionalAction,
        default=_environment_bool("INGESTOR_REPLACE_DOCUMENT", default=True),
    )
    parser.add_argument(
        "--refresh",
        action=argparse.BooleanOptionalAction,
        default=_environment_bool("INGESTOR_REFRESH", default=True),
    )
    parser.add_argument(
        "--canonical-json",
        type=Path,
        default=_environment_path("CANONICAL_JSON"),
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
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=_environment_bool("INGESTOR_DRY_RUN", default=False),
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


def _emit_result(event: str, payload: dict[str, object]) -> None:
    print(f"{event} {json.dumps(payload, ensure_ascii=False, sort_keys=True)}")


def run(args: argparse.Namespace) -> int:
    payload = ingest_chunks(
        IngestionConfig(
            input_path=args.input_path,
            input_filename=args.input_filename,
            url=args.url,
            index=args.index,
            username=args.username,
            password=args.password,
            verify_certs=args.verify_certs,
            ca_certs=args.ca_certs,
            expected_embedding_dimensions=args.expected_embedding_dimensions,
            batch_size=args.batch_size,
            request_timeout_seconds=args.request_timeout_seconds,
            wait_timeout_seconds=args.wait_timeout_seconds,
            wait_interval_seconds=args.wait_interval_seconds,
            install_template=args.install_template,
            template_name=args.template_name,
            template_file=args.template_file,
            allow_missing_embeddings=args.allow_missing_embeddings,
            replace_document=args.replace_document,
            refresh=args.refresh,
            canonical_json=args.canonical_json,
            metadata=DocumentMetadata(
                document_public_id=args.document_public_id,
                document_title=args.document_title,
                document_authors=args.document_author,
                original_filename=args.original_filename,
                file_type=args.file_type,
                language=args.language,
            ),
            preview_output=args.preview_output,
            dry_run=args.dry_run,
        )
    )
    event = "INGESTION_VALIDATED" if args.dry_run else "INGESTION_DONE"
    _emit_result(event, payload)
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
