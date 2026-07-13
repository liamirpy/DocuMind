from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "PDF Canonicalization Agent"
    app_version: str = "0.3.0"
    log_level: str = "INFO"
    max_upload_size_mb: int = Field(default=100, gt=0, le=2000)
    max_concurrency: int = Field(default=1, gt=0, le=16)

    tools_base_url: str = "http://host.docker.internal:8090"
    tools_extract_path: str = "/v1/extract"
    tools_ready_path: str = "/health/ready"
    tools_timeout_seconds: float = Field(default=1800.0, gt=1)
    tools_verify_tls: bool = True

    output_dir: Path = Path("/data/outputs")
    packages_url_prefix: str = "/packages"
    keep_raw_extractor_response: bool = False
    overwrite_existing_package: bool = False
    create_zip_package: bool = True

    formula_crop_scale: float = Field(default=3.0, ge=1.0, le=8.0)
    formula_crop_padding_points: float = Field(default=8.0, ge=0.0, le=100.0)
    fallback_asset_crop_scale: float = Field(default=2.5, ge=1.0, le=8.0)
    fallback_asset_crop_padding_points: float = Field(default=5.0, ge=0.0, le=100.0)

    llm_enabled: bool = False
    llm_provider: Literal["ollama"] = "ollama"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2-vision:11b"
    ollama_timeout_seconds: float = Field(default=600.0, gt=1)
    ollama_keep_alive: str = "10m"
    ollama_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_validate_all_figures: bool = False
    llm_describe_all_elements: bool = True
    llm_repair_empty_tables: bool = True
    llm_repair_uncertain_formulas: bool = True
    llm_max_items_per_document: int = Field(default=500, ge=0, le=5000)

    metadata_required_fields: tuple[str, ...] = ("title",)
    quality_green_threshold: float = Field(default=0.90, ge=0.0, le=1.0)
    quality_yellow_threshold: float = Field(default=0.65, ge=0.0, le=1.0)

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
