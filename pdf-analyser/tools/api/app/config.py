from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Scientific PDF Extraction API"
    app_version: str = "0.2.0"
    log_level: str = "INFO"

    max_upload_size_mb: int = Field(default=100, gt=0)
    serve_assets: bool = True
    assets_dir: Path = Path("/data/assets")
    assets_url_prefix: str = "/assets"

    grobid_base_url: str = "http://grobid:8070"
    grobid_timeout_seconds: float = Field(default=300.0, gt=0)
    grobid_max_retries: int = Field(default=2, ge=1, le=10)
    grobid_tei_coordinates: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "persName",
            "figure",
            "ref",
            "biblStruct",
            "formula",
            "s",
            "p",
            "title",
            "affiliation",
            "note",
        ]
    )

    docling_preload_on_startup: bool = True
    docling_max_num_pages: int = Field(default=300, gt=0)
    docling_max_concurrency: int = Field(default=1, gt=0, le=8)
    docling_document_timeout_seconds: float = Field(default=1800.0, gt=0)
    docling_accelerator_device: str = "cpu"
    docling_accelerator_num_threads: int = Field(default=4, gt=0, le=64)

    docling_ocr_backend: Literal["onnxruntime", "torch"] = "onnxruntime"
    docling_do_ocr: bool = True
    docling_ocr_force_full_page: bool = False
    docling_ocr_bitmap_area_threshold: float = Field(default=0.05, ge=0.0, le=1.0)

    docling_do_table_structure: bool = True
    docling_table_mode: Literal["fast", "accurate"] = "accurate"
    docling_table_do_cell_matching: bool = True
    docling_do_formula_enrichment: bool = True

    docling_generate_page_images: bool = True
    docling_generate_picture_images: bool = True
    docling_images_scale: float = Field(default=2.0, ge=0.5, le=4.0)
    docling_export_pictures: bool = True
    docling_export_tables: bool = True

    @field_validator("grobid_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("assets_url_prefix")
    @classmethod
    def normalize_assets_prefix(cls, value: str) -> str:
        cleaned = "/" + value.strip("/")
        return cleaned if cleaned != "/" else "/assets"

    @field_validator("grobid_tei_coordinates", mode="before")
    @classmethod
    def parse_coordinate_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("docling_accelerator_device")
    @classmethod
    def validate_accelerator_device(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"auto", "cpu", "cuda"}:
            return normalized
        if normalized.startswith("cuda:") and normalized[5:].isdigit():
            return normalized
        raise ValueError("Expected auto, cpu, cuda, or cuda:<index>.")

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
