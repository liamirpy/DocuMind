from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.chunking.config import ChunkingConfig
from app.chunking.models import IngestionContext, QueryEmbeddingOutput
from app.chunking.pipeline import DirectoryChunkingPipeline
from app.chunking.token_counter import RegexTokenCounter
from app.embedding import ChunkEmbeddingService, build_embedding_provider
from app.input_package.reader import load_input_package


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="documind-indexer",
        description=(
            "Read an existing PDF output directory, create hierarchical and special-element "
            "chunks, generate dense embeddings, and write a single JSON payload ready for "
            "OpenSearch indexing."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    chunk_parser = subparsers.add_parser(
        "chunk",
        help="Create chunks and embeddings from a PDF output directory",
    )
    chunk_parser.add_argument(
        "input_directory",
        type=Path,
        help="Directory containing canonical_document.json and figures/tables/formulas folders",
    )
    chunk_parser.add_argument("--user-id", required=True)
    chunk_parser.add_argument("--document-id", required=True)
    chunk_parser.add_argument("--output", type=Path, required=True)
    chunk_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional JSON configuration file. Production defaults are used when omitted.",
    )
    chunk_parser.add_argument(
        "--skip-embedding",
        action="store_true",
        help="Create chunks without loading an embedding model or generating vectors.",
    )

    query_parser = subparsers.add_parser(
        "embed-query",
        help="Generate a query vector with the same configured embedding model",
    )
    query_parser.add_argument("query_text")
    query_parser.add_argument("--output", type=Path, required=True)
    query_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional JSON configuration file. Production defaults are used when omitted.",
    )

    config_parser = subparsers.add_parser(
        "write-default-config",
        help="Write the default chunking and embedding configuration JSON file",
    )
    config_parser.add_argument("--output", type=Path, default=Path("chunking_config.json"))

    return parser


def _load_config(path: Path | None) -> ChunkingConfig:
    return ChunkingConfig.from_json_file(path) if path else ChunkingConfig()


def run_chunk(args: argparse.Namespace) -> None:
    config = _load_config(args.config)
    if args.skip_embedding:
        config = config.model_copy(
            update={
                "embedding": config.embedding.model_copy(update={"enabled": False}),
            }
        )

    provider = build_embedding_provider(config.embedding) if config.embedding.enabled else None
    token_counter = provider.token_counter if provider is not None else RegexTokenCounter()

    package = load_input_package(
        args.input_directory,
        canonical_filename=config.package_assets.canonical_filename,
    )
    context = IngestionContext(user_id=args.user_id, document_id=args.document_id)
    chunk_output = DirectoryChunkingPipeline(
        config=config,
        token_counter=token_counter,
    ).run(
        package=package,
        context=context,
    )
    output = ChunkEmbeddingService(
        config=config.embedding,
        provider=provider,
    ).run(chunk_output)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Validated canonical document: {package.canonical.document_id}")
    print(f"Input directory: {package.root}")
    print(
        "Created "
        f"{output.counts.total} chunks "
        f"({output.counts.parent} parent, "
        f"{output.counts.child} child, "
        f"{output.counts.standalone} standalone)"
    )
    print(
        "Special elements: "
        f"{output.counts.table} table, "
        f"{output.counts.figure} figure, "
        f"{output.counts.formula} formula"
    )
    print(f"References preserved separately: {output.counts.references}")
    if output.embedding.enabled:
        print(
            "Embeddings: "
            f"{output.embedding.embedded_chunk_count} embedded, "
            f"{output.embedding.skipped_chunk_count} skipped; "
            f"model={output.embedding.model}, "
            f"dimensions={output.embedding.dimensions}"
        )
    else:
        print("Embeddings: disabled")
    if output.counts.oversized:
        print(
            f"Warning: {output.counts.oversized} standalone chunks exceed the configured "
            "special-element token maximum. See each chunk's warnings field."
        )
    print(f"Wrote: {args.output}")


def run_embed_query(args: argparse.Namespace) -> None:
    config = _load_config(args.config)
    if not config.embedding.enabled:
        raise ValueError("Embedding is disabled in the selected configuration")

    provider = build_embedding_provider(config.embedding)
    text = args.query_text.strip()
    if not text:
        raise ValueError("query_text must not be empty")
    vector = provider.embed_query(text)
    if len(vector) != provider.dimensions:
        raise RuntimeError(
            f"Embedding provider returned {len(vector)} values; expected {provider.dimensions}"
        )

    output = QueryEmbeddingOutput(
        provider=provider.provider_name,
        model=provider.model_name,
        dimensions=provider.dimensions,
        normalized=provider.normalized,
        device=provider.device,
        tokenizer_name=provider.token_counter.name,
        token_count=provider.token_counter.count(text),
        query_text=text,
        embedding=vector,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Generated query embedding with {output.model} ({output.dimensions} dimensions)")
    print(f"Wrote: {args.output}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "write-default-config":
        ChunkingConfig().write_json(args.output)
        print(f"Wrote default configuration: {args.output}")
        return

    if args.command == "chunk":
        run_chunk(args)
        return

    if args.command == "embed-query":
        run_embed_query(args)
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
