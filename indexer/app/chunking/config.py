from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WindowConfig(FrozenConfigModel):
    """Token window used for parent or child paragraph chunks."""

    enabled: bool = True
    target_tokens: int = Field(ge=20)
    max_tokens: int = Field(ge=20)
    overlap_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_window(self) -> WindowConfig:
        if self.target_tokens > self.max_tokens:
            raise ValueError("target_tokens must be less than or equal to max_tokens")
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be smaller than target_tokens")
        return self


class HierarchicalTextConfig(FrozenConfigModel):
    """Settings for paragraph parent/child chunking."""

    parent: WindowConfig = Field(
        default_factory=lambda: WindowConfig(
            target_tokens=900,
            max_tokens=1100,
            overlap_tokens=0,
        )
    )
    child: WindowConfig = Field(
        default_factory=lambda: WindowConfig(
            target_tokens=300,
            max_tokens=420,
            overlap_tokens=50,
        )
    )
    parent_retrieval_enabled: bool = False
    child_retrieval_enabled: bool = True

    @model_validator(mode="after")
    def validate_hierarchy(self) -> HierarchicalTextConfig:
        if not self.parent.enabled and not self.child.enabled:
            raise ValueError("at least one of text.parent or text.child must be enabled")
        if (
            self.parent.enabled
            and self.child.enabled
            and self.child.max_tokens > self.parent.max_tokens
        ):
            raise ValueError("child.max_tokens must not exceed parent.max_tokens")
        return self


class PackageAssetConfig(FrozenConfigModel):
    """How canonical fields and sidecar files are combined."""

    prefer_sidecar_files: bool = True
    infer_standard_sidecar_paths: bool = True
    canonical_filename: str = Field(default="canonical_document.json", min_length=1)


class SpecialElementConfig(FrozenConfigModel):
    """Settings for one-piece table, figure, and formula chunks."""

    enabled: bool = True
    max_tokens: int = Field(default=1800, ge=20)
    oversize_policy: Literal["allow", "truncate", "error"] = "allow"

    include_caption: bool = True
    include_description_text: bool = True
    include_summary: bool = True
    include_description_details: bool = True

    include_table_data: bool = True
    include_table_latex: bool = False
    include_formula_latex: bool = True
    include_formula_text: bool = True

    retrieval_enabled: bool = True


class ReferenceConfig(FrozenConfigModel):
    """Settings for bibliography/reference records."""

    enabled: bool = True
    exclude_reference_sections_from_text_chunks: bool = True
    section_names: list[str] = Field(
        default_factory=lambda: [
            "reference",
            "references",
            "bibliography",
            "works cited",
            "literature cited",
            "cited references",
        ]
    )
    retrieval_enabled: bool = False
    generate_retrieval_text: bool = False
    include_raw_text: bool = True
    include_structured_metadata: bool = True

    @model_validator(mode="after")
    def validate_names(self) -> ReferenceConfig:
        if not any(name.strip() for name in self.section_names):
            raise ValueError("references.section_names must contain at least one non-empty name")
        return self


class EmbeddingConfig(FrozenConfigModel):
    """Dense embedding settings for the generated chunks.

    `sentence_transformers` is the production provider. `development_hash` is
    deterministic and dependency-light, but it is not semantic and must only be
    used for tests and pipeline smoke checks.
    """

    enabled: bool = True
    provider: Literal["sentence_transformers", "development_hash"] = "sentence_transformers"
    model_name: str = Field(default="BAAI/bge-m3", min_length=1)

    # Embed precise retrievable chunks by default: children, tables, figures,
    # and formulas. Parent chunks remain available for context expansion.
    selection: Literal["retrieval_enabled", "all"] = "retrieval_enabled"

    batch_size: int = Field(default=8, ge=1)
    device: str | None = "auto"
    normalize_embeddings: bool = True
    use_document_encoder: bool = True
    use_query_encoder: bool = True
    show_progress_bar: bool = True

    # Model loading controls.
    cache_folder: str | None = None
    revision: str | None = None
    trust_remote_code: bool = False
    local_files_only: bool = False

    # Optional safety checks and limits.
    expected_dimensions: int | None = Field(default=1024, ge=1)
    max_sequence_length: int | None = Field(default=None, ge=1)
    max_input_tokens: int | None = Field(default=None, ge=1)
    overlong_policy: Literal["error", "truncate"] = "error"

    # Used only by the non-semantic development provider.
    development_hash_dimensions: int = Field(default=32, ge=2)

    @model_validator(mode="after")
    def validate_provider_settings(self) -> EmbeddingConfig:
        if self.provider == "development_hash" and self.expected_dimensions not in (
            None,
            self.development_hash_dimensions,
        ):
            raise ValueError(
                "For provider=development_hash, expected_dimensions must be null or equal "
                "to development_hash_dimensions"
            )
        return self


class ChunkingConfig(FrozenConfigModel):
    """Top-level configuration for directory-to-chunks-and-embeddings pipeline."""

    chunker_version: str = Field(default="hierarchical-assets-v3", min_length=1)
    package_assets: PackageAssetConfig = Field(default_factory=PackageAssetConfig)
    text: HierarchicalTextConfig = Field(default_factory=HierarchicalTextConfig)
    special_elements: SpecialElementConfig = Field(default_factory=SpecialElementConfig)
    references: ReferenceConfig = Field(default_factory=ReferenceConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)

    @classmethod
    def from_json_file(cls, path: str | Path) -> ChunkingConfig:
        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(f"Chunking config file not found: {config_path}")
        return cls.model_validate_json(config_path.read_bytes())

    def write_json(self, path: str | Path) -> None:
        config_path = Path(path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
