from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.chunking.config import ChunkingConfig
from app.chunking.models import IngestionContext
from app.chunking.pipeline import DirectoryChunkingPipeline
from app.chunking.token_counter import RegexTokenCounter
from app.embedding import ChunkEmbeddingService, build_embedding_provider
from app.input_package.reader import load_input_package


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create chunks and embeddings from a PDF output directory"
    )
    parser.add_argument("input_directory", type=Path)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--output", type=Path, default=Path("chunks.json"))
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--skip-embedding", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ChunkingConfig.from_json_file(args.config) if args.config else ChunkingConfig()
    if args.skip_embedding:
        config = config.model_copy(
            update={"embedding": config.embedding.model_copy(update={"enabled": False})}
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
    ).run(package=package, context=context)
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
    print(f"Created {output.counts.total} chunks and {output.counts.references} references")
    print(f"Embedded {output.embedding.embedded_chunk_count} chunks")
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    main()
