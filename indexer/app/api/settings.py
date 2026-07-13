from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.chunking.config import (
    ChunkingConfig,
    EmbeddingConfig,
    HierarchicalTextConfig,
    PackageAssetConfig,
    ReferenceConfig,
    SpecialElementConfig,
    WindowConfig,
)


class ApiSettings(BaseSettings):
    """Environment-driven settings for the API and indexing pipeline."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API runtime.
    api_title: str = "DocuMind Indexer API"
    api_version: str = "4.1.0"
    api_log_level: str = "info"
    api_key: str | None = None
    api_cors_origins: str = ""
    max_concurrent_jobs: int = Field(default=1, ge=1, le=8)
    job_history_limit: int = Field(default=1000, ge=10)
    model_preload: bool = False

    # Container-visible roots and their optional host-side equivalents.
    indexer_input_root: Path = Path("/data/input")
    indexer_output_root: Path = Path("/data/output")
    documind_input_root_host: Path | None = None
    documind_output_root_host: Path | None = None
    job_state_directory: str = ".jobs"

    # Canonical package settings.
    chunker_version: str = "hierarchical-assets-v3"
    canonical_filename: str = "canonical_document.json"
    prefer_sidecar_files: bool = True
    infer_standard_sidecar_paths: bool = True

    # Parent chunks.
    parent_enabled: bool = True
    parent_target_tokens: int = Field(default=900, ge=20)
    parent_max_tokens: int = Field(default=1100, ge=20)
    parent_overlap_tokens: int = Field(default=0, ge=0)
    parent_retrieval_enabled: bool = False

    # Child chunks.
    child_enabled: bool = True
    child_target_tokens: int = Field(default=300, ge=20)
    child_max_tokens: int = Field(default=420, ge=20)
    child_overlap_tokens: int = Field(default=50, ge=0)
    child_retrieval_enabled: bool = True

    # Tables, figures, and formulas.
    special_elements_enabled: bool = True
    special_elements_max_tokens: int = Field(default=1800, ge=20)
    special_elements_oversize_policy: Literal["allow", "truncate", "error"] = "allow"
    special_elements_include_caption: bool = True
    special_elements_include_description_text: bool = True
    special_elements_include_summary: bool = True
    special_elements_include_description_details: bool = True
    special_elements_include_table_data: bool = True
    special_elements_include_table_latex: bool = False
    special_elements_include_formula_latex: bool = True
    special_elements_include_formula_text: bool = True
    special_elements_retrieval_enabled: bool = True

    # References.
    references_enabled: bool = True
    references_exclude_sections_from_text_chunks: bool = True
    references_section_names: str = (
        "reference,references,bibliography,works cited,literature cited,cited references"
    )
    references_retrieval_enabled: bool = False
    references_generate_retrieval_text: bool = False
    references_include_raw_text: bool = True
    references_include_structured_metadata: bool = True

    # Embeddings.
    embedding_enabled: bool = True
    embedding_provider: Literal["sentence_transformers", "development_hash"] = (
        "sentence_transformers"
    )
    embedding_model_name: str = "BAAI/bge-m3"
    embedding_selection: Literal["retrieval_enabled", "all"] = "retrieval_enabled"
    embedding_batch_size: int = Field(default=8, ge=1)
    embedding_device: str | None = "auto"
    embedding_normalize: bool = True
    embedding_use_document_encoder: bool = True
    embedding_use_query_encoder: bool = True
    embedding_show_progress_bar: bool = False
    embedding_cache_folder: str | None = "/models/huggingface"
    embedding_revision: str | None = None
    embedding_trust_remote_code: bool = False
    embedding_local_files_only: bool = False
    embedding_expected_dimensions: int | None = Field(default=1024, ge=1)
    embedding_max_sequence_length: int | None = Field(default=None, ge=1)
    embedding_max_input_tokens: int | None = Field(default=None, ge=1)
    embedding_overlong_policy: Literal["error", "truncate"] = "error"
    embedding_development_hash_dimensions: int = Field(default=32, ge=2)

    @field_validator("api_key", "embedding_revision", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "embedding_expected_dimensions",
        "embedding_max_sequence_length",
        "embedding_max_input_tokens",
        mode="before",
    )
    @classmethod
    def nullable_integer(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().lower() in {"", "none", "null"}:
            return None
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.api_cors_origins.split(",") if item.strip()]

    @property
    def reference_section_name_list(self) -> list[str]:
        return [item.strip() for item in self.references_section_names.split(",") if item.strip()]

    @property
    def job_state_root(self) -> Path:
        return self.indexer_output_root / self.job_state_directory

    @property
    def embedding_cache_root(self) -> Path | None:
        if not self.embedding_cache_folder:
            return None
        return Path(self.embedding_cache_folder)

    def build_chunking_config(self) -> ChunkingConfig:
        """Build the existing chunker configuration entirely from environment values."""

        return ChunkingConfig(
            chunker_version=self.chunker_version,
            package_assets=PackageAssetConfig(
                prefer_sidecar_files=self.prefer_sidecar_files,
                infer_standard_sidecar_paths=self.infer_standard_sidecar_paths,
                canonical_filename=self.canonical_filename,
            ),
            text=HierarchicalTextConfig(
                parent=WindowConfig(
                    enabled=self.parent_enabled,
                    target_tokens=self.parent_target_tokens,
                    max_tokens=self.parent_max_tokens,
                    overlap_tokens=self.parent_overlap_tokens,
                ),
                child=WindowConfig(
                    enabled=self.child_enabled,
                    target_tokens=self.child_target_tokens,
                    max_tokens=self.child_max_tokens,
                    overlap_tokens=self.child_overlap_tokens,
                ),
                parent_retrieval_enabled=self.parent_retrieval_enabled,
                child_retrieval_enabled=self.child_retrieval_enabled,
            ),
            special_elements=SpecialElementConfig(
                enabled=self.special_elements_enabled,
                max_tokens=self.special_elements_max_tokens,
                oversize_policy=self.special_elements_oversize_policy,
                include_caption=self.special_elements_include_caption,
                include_description_text=self.special_elements_include_description_text,
                include_summary=self.special_elements_include_summary,
                include_description_details=self.special_elements_include_description_details,
                include_table_data=self.special_elements_include_table_data,
                include_table_latex=self.special_elements_include_table_latex,
                include_formula_latex=self.special_elements_include_formula_latex,
                include_formula_text=self.special_elements_include_formula_text,
                retrieval_enabled=self.special_elements_retrieval_enabled,
            ),
            references=ReferenceConfig(
                enabled=self.references_enabled,
                exclude_reference_sections_from_text_chunks=(
                    self.references_exclude_sections_from_text_chunks
                ),
                section_names=self.reference_section_name_list,
                retrieval_enabled=self.references_retrieval_enabled,
                generate_retrieval_text=self.references_generate_retrieval_text,
                include_raw_text=self.references_include_raw_text,
                include_structured_metadata=self.references_include_structured_metadata,
            ),
            embedding=EmbeddingConfig(
                enabled=self.embedding_enabled,
                provider=self.embedding_provider,
                model_name=self.embedding_model_name,
                selection=self.embedding_selection,
                batch_size=self.embedding_batch_size,
                device=self.embedding_device,
                normalize_embeddings=self.embedding_normalize,
                use_document_encoder=self.embedding_use_document_encoder,
                use_query_encoder=self.embedding_use_query_encoder,
                show_progress_bar=self.embedding_show_progress_bar,
                cache_folder=self.embedding_cache_folder,
                revision=self.embedding_revision,
                trust_remote_code=self.embedding_trust_remote_code,
                local_files_only=self.embedding_local_files_only,
                expected_dimensions=self.embedding_expected_dimensions,
                max_sequence_length=self.embedding_max_sequence_length,
                max_input_tokens=self.embedding_max_input_tokens,
                overlong_policy=self.embedding_overlong_policy,
                development_hash_dimensions=self.embedding_development_hash_dimensions,
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> ApiSettings:
    return ApiSettings()
