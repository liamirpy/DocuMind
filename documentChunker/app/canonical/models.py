from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CanonicalBaseModel(BaseModel):
    """Base model that preserves forward-compatible fields."""

    model_config = ConfigDict(extra="allow")


class CanonicalDocumentInfo(CanonicalBaseModel):
    filename: str | None = None
    sha256: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    source_pdf: str | None = None


class CanonicalMetadata(CanonicalBaseModel):
    title: str | None = None
    authors: list[Any] = Field(default_factory=list)
    abstract: str | None = None
    doi: str | None = None
    journal: str | None = None
    publication_date: str | None = None
    language: str | None = None
    source_filename: str | None = None


class CanonicalDescription(CanonicalBaseModel):
    text: str | None = None
    summary: str | None = None
    element_type: str | None = None
    source: str | None = None
    provider: str | None = None
    model: str | None = None
    confidence: float | None = None
    warnings: list[Any] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text", "summary")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CanonicalParagraph(CanonicalBaseModel):
    id: str = Field(min_length=1)
    source_id: str | None = None
    section_id: str = Field(min_length=1)
    section_path: list[str] = Field(default_factory=list)
    order: int = Field(ge=1)
    text: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "section_id", "text")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("section_path")
    @classmethod
    def clean_section_path(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    @model_validator(mode="after")
    def validate_page_range(self) -> CanonicalParagraph:
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class CanonicalSection(CanonicalBaseModel):
    id: str = Field(min_length=1)
    source_id: str | None = None
    title: str | None = None
    heading: str | None = None
    number: str | None = None
    level: int = Field(default=1, ge=1)
    parent_id: str | None = None
    path: list[str] = Field(default_factory=list)
    paragraph_ids: list[str] = Field(default_factory=list)
    figure_ids: list[str] = Field(default_factory=list)
    table_ids: list[str] = Field(default_factory=list)
    formula_ids: list[str] = Field(default_factory=list)
    order: int | None = Field(default=None, ge=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)


class CanonicalElement(CanonicalBaseModel):
    id: str = Field(min_length=1)
    index: int | None = Field(default=None, ge=1)
    page: int | None = Field(default=None, ge=1)
    description: CanonicalDescription | str | None = None
    section_id: str | None = None
    section_title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    section_assignment: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    assets: dict[str, Any] = Field(default_factory=dict)
    sources: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def clean_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("section_path")
    @classmethod
    def clean_element_section_path(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]


class CanonicalFigure(CanonicalElement):
    label: str | None = None
    caption: str | None = None


class CanonicalTable(CanonicalElement):
    label: str | None = None
    caption: str | None = None
    columns: list[Any] = Field(default_factory=list)
    rows: list[Any] = Field(default_factory=list)
    row_count: int | None = Field(default=None, ge=0)
    column_count: int | None = Field(default=None, ge=0)
    data_source: str | None = None
    flattened_text: str | None = None
    latex: str | None = None
    quality: dict[str, Any] = Field(default_factory=dict)


class CanonicalFormula(CanonicalElement):
    equation_number: str | None = None
    latex: str | None = None
    text: str | None = None
    original: Any = None
    quality: dict[str, Any] = Field(default_factory=dict)


class CanonicalReference(CanonicalBaseModel):
    """Reference metadata emitted by the GROBID-backed PDF pipeline.

    GROBID coordinate data is not completely uniform across extraction
    paths. Some canonical documents contain a JSON array, while others
    contain the original comma-separated coordinate string. Preserve both
    representations so indexing does not fail on valid PDF-pipeline output.
    """

    id: str | None = None
    title: str | None = None
    authors: list[Any] = Field(default_factory=list)
    year: str | int | None = None
    doi: str | None = None
    raw: str | None = None
    coords: str | list[Any] | None = None

    @field_validator("coords", mode="before")
    @classmethod
    def normalize_coords(cls, value: Any) -> str | list[Any] | None:
        """Accept string or array coordinates and preserve their meaning."""

        if value is None:
            return None

        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None

        if isinstance(value, tuple):
            return list(value)

        return value


class CanonicalContent(CanonicalBaseModel):
    full_text: str = ""
    text_blocks: list[dict[str, Any]] = Field(default_factory=list)
    paragraphs: list[CanonicalParagraph] = Field(default_factory=list)
    sections: list[CanonicalSection] = Field(default_factory=list)
    section_tree: list[dict[str, Any]] = Field(default_factory=list)
    figures: list[CanonicalFigure] = Field(default_factory=list)
    tables: list[CanonicalTable] = Field(default_factory=list)
    formulas: list[CanonicalFormula] = Field(default_factory=list)
    references: list[CanonicalReference] = Field(default_factory=list)


class CanonicalDocument(CanonicalBaseModel):
    schema_version: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    created_at: str | None = None
    document: CanonicalDocumentInfo = Field(default_factory=CanonicalDocumentInfo)
    metadata: CanonicalMetadata = Field(default_factory=CanonicalMetadata)
    content: CanonicalContent

    @field_validator("schema_version", "document_id")
    @classmethod
    def strip_root_strings(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("schema_version")
    @classmethod
    def require_supported_schema_major(cls, value: str) -> str:
        if value.split(".", maxsplit=1)[0] != "1":
            raise ValueError("unsupported canonical schema version; expected major version 1")
        return value

    @model_validator(mode="after")
    def validate_chunking_contract(self) -> CanonicalDocument:
        section_ids = [section.id for section in self.content.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("content.sections contains duplicate section IDs")

        paragraph_ids = [paragraph.id for paragraph in self.content.paragraphs]
        if len(paragraph_ids) != len(set(paragraph_ids)):
            raise ValueError("content.paragraphs contains duplicate paragraph IDs")

        orders = [paragraph.order for paragraph in self.content.paragraphs]
        if len(orders) != len(set(orders)):
            raise ValueError("content.paragraphs contains duplicate paragraph order values")

        if self.document.sha256 and self.document.sha256 != self.document_id:
            raise ValueError("document.sha256 must match the canonical document_id")

        known_sections = set(section_ids)
        missing_sections = sorted(
            {
                paragraph.section_id
                for paragraph in self.content.paragraphs
                if paragraph.section_id not in known_sections
            }
        )
        if missing_sections:
            raise ValueError(
                "paragraphs reference unknown section IDs: " + ", ".join(missing_sections)
            )

        element_groups = {
            "figures": self.content.figures,
            "tables": self.content.tables,
            "formulas": self.content.formulas,
        }
        for group_name, elements in element_groups.items():
            ids = [element.id for element in elements]
            if len(ids) != len(set(ids)):
                raise ValueError(f"content.{group_name} contains duplicate IDs")

        reference_ids = [reference.id for reference in self.content.references if reference.id]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("content.references contains duplicate non-empty IDs")

        return self
