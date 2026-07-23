import argparse
import asyncio
import json
from pathlib import Path

from app.config import get_settings
from app.pipeline import AgentPipeline


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    pipeline = AgentPipeline(settings)
    try:
        result = await pipeline.process(
            pdf_path=Path(args.pdf).resolve(),
            filename=Path(args.pdf).name,
            use_llm=args.use_llm,
            output_folder=args.output_folder,
            overwrite=args.overwrite,
        )
    finally:
        await pipeline.close()

    summary = {
        "document_id": result["document_id"],
        "output_folder": result["package_name"],
        "package_dir": str(result["package_dir"]),
        "canonical_json": str(result["canonical_path"]),
        "zip": str(result["zip_path"]) if result["zip_path"] else None,
        "quality": result["canonical"].get("quality"),
        "counts": result["canonical"].get("counts"),
        "processing": result.get("processing"),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process a PDF through the extraction tools and build a canonical package."
    )
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Enable the configured bounded Ollama/Llama fallback.",
    )
    parser.add_argument(
        "--output-folder",
        help="Safe folder name to create below the configured output root.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing package with the same output folder name.",
    )
    args = parser.parse_args()
    path = Path(args.pdf)
    if not path.is_file():
        parser.error(f"PDF does not exist: {path}")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
