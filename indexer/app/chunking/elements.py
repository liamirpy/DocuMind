from __future__ import annotations

from typing import Any, Literal

from app.canonical.models import (
    CanonicalFigure,
    CanonicalFormula,
    CanonicalTable,
)
from app.chunking.common import (
    clean_text,
    detail_lines,
    make_chunk_id,
    merge_description,
    path_text,
    sha256_text,
)
from app.chunking.config import ChunkingConfig
from app.chunking.models import ChunkRecord, IngestionContext
from app.chunking.token_counter import TokenCounter
from app.input_package.reader import InputPackage


class SpecialElementChunker:
    """Create one rich standalone chunk for every table, figure, and formula."""

    def __init__(self, *, config: ChunkingConfig, token_counter: TokenCounter) -> None:
        self.config = config
        self.token_counter = token_counter

    def chunk(
        self,
        *,
        package: InputPackage,
        context: IngestionContext,
        start_ordinal: int = 1,
    ) -> list[ChunkRecord]:
        if not self.config.special_elements.enabled:
            return []

        records: list[ChunkRecord] = []
        ordinal = start_ordinal

        for figure in package.canonical.content.figures:
            records.append(
                self._figure_record(
                    package=package,
                    context=context,
                    figure=figure,
                    ordinal=ordinal,
                )
            )
            ordinal += 1

        for table in package.canonical.content.tables:
            records.append(
                self._table_record(
                    package=package,
                    context=context,
                    table=table,
                    ordinal=ordinal,
                )
            )
            ordinal += 1

        for formula in package.canonical.content.formulas:
            records.append(
                self._formula_record(
                    package=package,
                    context=context,
                    formula=formula,
                    ordinal=ordinal,
                )
            )
            ordinal += 1

        return records

    def _figure_record(
        self,
        *,
        package: InputPackage,
        context: IngestionContext,
        figure: CanonicalFigure,
        ordinal: int,
    ) -> ChunkRecord:
        caption, caption_source = self._caption(
            package=package,
            element=figure,
            folder="figures",
            canonical_caption=figure.caption,
        )
        description, description_source = self._description(
            package=package,
            element=figure,
            folder="figures",
        )
        text, summary, details = self._description_fields(description)

        label = clean_text(figure.label) or figure.id
        content_lines = [f"Figure: {label}"]
        self._append_semantic_lines(
            content_lines,
            caption=caption,
            summary=summary,
            text=text,
            details=details,
        )
        content = "\n\n".join(content_lines)
        retrieval_text = self._retrieval_text(
            document_title=package.canonical.metadata.title,
            section_path=tuple(figure.section_path),
            element_type="figure",
            heading=label,
            caption=caption,
            summary=summary,
            text=text,
            details=details,
        )

        return self._build_record(
            package=package,
            context=context,
            ordinal=ordinal,
            source_type="figure",
            source_id=figure.id,
            section_id=figure.section_id,
            section_path=tuple(figure.section_path),
            page=figure.page,
            caption=caption,
            text=text,
            summary=summary,
            details=details,
            table_text=None,
            formula_text=None,
            formula_latex=None,
            content=content,
            retrieval_text=retrieval_text,
            metadata={
                "label": figure.label,
                "description_present": bool(description),
                "description_source": description_source,
                "caption_source": caption_source,
                "description_provenance": self._description_provenance(description),
                "assets": figure.assets,
            },
        )

    def _table_record(
        self,
        *,
        package: InputPackage,
        context: IngestionContext,
        table: CanonicalTable,
        ordinal: int,
    ) -> ChunkRecord:
        caption, caption_source = self._caption(
            package=package,
            element=table,
            folder="tables",
            canonical_caption=table.caption,
        )
        description, description_source = self._description(
            package=package,
            element=table,
            folder="tables",
        )
        text, summary, details = self._description_fields(description)
        table_text, table_text_source = self._table_text(package=package, table=table)

        label = clean_text(table.label) or table.id
        content_lines = [f"Table: {label}"]
        self._append_semantic_lines(
            content_lines,
            caption=caption,
            summary=summary,
            text=text,
            details=details,
        )
        if self.config.special_elements.include_table_data and table_text:
            content_lines.append(f"Table data:\n{table_text}")
        if self.config.special_elements.include_table_latex:
            latex = self._table_latex(package=package, table=table)
            if latex:
                content_lines.append(f"LaTeX:\n{latex}")
        content = "\n\n".join(content_lines)

        retrieval_text = self._retrieval_text(
            document_title=package.canonical.metadata.title,
            section_path=tuple(table.section_path),
            element_type="table",
            heading=label,
            caption=caption,
            summary=summary,
            text=text,
            details=details,
            table_text=(table_text if self.config.special_elements.include_table_data else None),
        )

        return self._build_record(
            package=package,
            context=context,
            ordinal=ordinal,
            source_type="table",
            source_id=table.id,
            section_id=table.section_id,
            section_path=tuple(table.section_path),
            page=table.page,
            caption=caption,
            text=text,
            summary=summary,
            details=details,
            table_text=table_text,
            formula_text=None,
            formula_latex=None,
            content=content,
            retrieval_text=retrieval_text,
            metadata={
                "label": table.label,
                "description_present": bool(description),
                "description_source": description_source,
                "caption_source": caption_source,
                "table_text_source": table_text_source,
                "description_provenance": self._description_provenance(description),
                "row_count": table.row_count if table.row_count is not None else len(table.rows),
                "column_count": (
                    table.column_count if table.column_count is not None else len(table.columns)
                ),
                "data_source": table.data_source,
                "quality": table.quality,
                "assets": table.assets,
            },
        )

    def _formula_record(
        self,
        *,
        package: InputPackage,
        context: IngestionContext,
        formula: CanonicalFormula,
        ordinal: int,
    ) -> ChunkRecord:
        description, description_source = self._description(
            package=package,
            element=formula,
            folder="formulas",
        )
        text, summary, details = self._description_fields(description)
        formula_latex, latex_source = self._formula_latex(package=package, formula=formula)
        formula_text, formula_text_source = self._formula_text(package=package, formula=formula)

        heading = clean_text(formula.equation_number) or formula.id
        content_lines = [f"Formula: {heading}"]
        self._append_semantic_lines(
            content_lines,
            caption=None,
            summary=summary,
            text=text,
            details=details,
        )
        if self.config.special_elements.include_formula_latex and formula_latex:
            content_lines.append(f"LaTeX:\n{formula_latex}")
        if self.config.special_elements.include_formula_text and formula_text:
            content_lines.append(f"Formula text:\n{formula_text}")
        content = "\n\n".join(content_lines)

        retrieval_text = self._retrieval_text(
            document_title=package.canonical.metadata.title,
            section_path=tuple(formula.section_path),
            element_type="formula",
            heading=heading,
            caption=None,
            summary=summary,
            text=text,
            details=details,
            formula_latex=(
                formula_latex if self.config.special_elements.include_formula_latex else None
            ),
            formula_text=(
                formula_text if self.config.special_elements.include_formula_text else None
            ),
        )

        return self._build_record(
            package=package,
            context=context,
            ordinal=ordinal,
            source_type="formula",
            source_id=formula.id,
            section_id=formula.section_id,
            section_path=tuple(formula.section_path),
            page=formula.page,
            caption=None,
            text=text,
            summary=summary,
            details=details,
            table_text=None,
            formula_text=formula_text,
            formula_latex=formula_latex,
            content=content,
            retrieval_text=retrieval_text,
            metadata={
                "equation_number": formula.equation_number,
                "description_present": bool(description),
                "description_source": description_source,
                "formula_latex_source": latex_source,
                "formula_text_source": formula_text_source,
                "description_provenance": self._description_provenance(description),
                "quality": formula.quality,
                "assets": formula.assets,
            },
        )

    def _build_record(
        self,
        *,
        package: InputPackage,
        context: IngestionContext,
        ordinal: int,
        source_type: Literal["table", "figure", "formula"],
        source_id: str,
        section_id: str | None,
        section_path: tuple[str, ...],
        page: int | None,
        caption: str | None,
        text: str | None,
        summary: str | None,
        details: dict[str, Any],
        table_text: str | None,
        formula_text: str | None,
        formula_latex: str | None,
        content: str,
        retrieval_text: str,
        metadata: dict[str, Any],
    ) -> ChunkRecord:
        final_content, final_retrieval_text, token_count, oversized, warnings = (
            self._apply_oversize_policy(content=content, retrieval_text=retrieval_text)
        )
        content_hash = sha256_text(final_retrieval_text)
        chunk_id = make_chunk_id(
            user_id=context.user_id,
            document_id=context.document_id,
            source_type=source_type,
            chunk_role="standalone",
            source_ids=[source_id],
            section_id=section_id,
            parent_chunk_id=None,
            content_hash=content_hash,
            chunker_version=self.config.chunker_version,
        )
        return ChunkRecord(
            user_id=context.user_id,
            document_id=context.document_id,
            source_document_id=package.canonical.document_id,
            chunk_id=chunk_id,
            chunk_ordinal=ordinal,
            chunk_role="standalone",
            source_type=source_type,
            parent_chunk_id=None,
            child_chunk_ids=[],
            retrieval_enabled=self.config.special_elements.retrieval_enabled,
            source_ids=[source_id],
            title=package.canonical.metadata.title,
            section_id=section_id,
            section_path=path_text(section_path),
            section_path_parts=list(section_path),
            page_start=page,
            page_end=page,
            caption=caption,
            text=text,
            summary=summary,
            details=details,
            table_text=table_text,
            formula_text=formula_text,
            formula_latex=formula_latex,
            content=final_content,
            retrieval_text=final_retrieval_text,
            content_token_count=self.token_counter.count(final_content),
            token_count=token_count,
            configured_max_tokens=self.config.special_elements.max_tokens,
            oversized=oversized,
            warnings=warnings,
            content_hash=content_hash,
            chunker_version=self.config.chunker_version,
            tokenizer_name=self.token_counter.name,
            metadata=metadata,
        )

    def _caption(
        self,
        *,
        package: InputPackage,
        element: CanonicalFigure | CanonicalTable,
        folder: str,
        canonical_caption: str | None,
    ) -> tuple[str | None, str | None]:
        asset = self._asset_path(element.assets, "caption_text")
        candidates = [asset]
        if self.config.package_assets.infer_standard_sidecar_paths:
            candidates.append(f"{folder}/{element.id}.caption.txt")
        file_caption, source = package.first_existing_text(candidates)
        canonical_value = clean_text(canonical_caption) or None
        if self.config.package_assets.prefer_sidecar_files:
            if file_caption:
                return file_caption, source
            return canonical_value, "canonical" if canonical_value else None
        if canonical_value:
            return canonical_value, "canonical"
        return file_caption, source

    def _description(
        self,
        *,
        package: InputPackage,
        element: CanonicalFigure | CanonicalTable | CanonicalFormula,
        folder: str,
    ) -> tuple[dict[str, Any], str | None]:
        asset = self._asset_path(element.assets, "description_json")
        candidates = [asset]
        if self.config.package_assets.infer_standard_sidecar_paths:
            candidates.append(f"{folder}/{element.id}.description.json")
        sidecar, source = package.first_existing_json(candidates)

        # The PDF package also writes a .description.txt file. Use it as a
        # last-resort description when the structured JSON sidecar is absent.
        if sidecar is None:
            text_asset = self._asset_path(element.assets, "description_text")
            text_candidates = [text_asset]
            if self.config.package_assets.infer_standard_sidecar_paths:
                text_candidates.append(f"{folder}/{element.id}.description.txt")
            fallback_text, fallback_source = package.first_existing_text(text_candidates)
            if fallback_text:
                sidecar = {"text": fallback_text}
                source = fallback_source

        merged = merge_description(
            element.description,
            sidecar,
            prefer_sidecar=self.config.package_assets.prefer_sidecar_files,
        )
        if source and sidecar:
            return merged, source
        if element.description is not None:
            return merged, "canonical"
        return merged, None

    @staticmethod
    def _description_fields(
        description: dict[str, Any],
    ) -> tuple[str | None, str | None, dict[str, Any]]:
        text = clean_text(description.get("text")) or None
        summary = clean_text(description.get("summary")) or None
        details = description.get("details")
        return text, summary, dict(details) if isinstance(details, dict) else {}

    @staticmethod
    def _description_provenance(description: dict[str, Any]) -> dict[str, Any]:
        return {
            key: description.get(key)
            for key in ("element_type", "source", "provider", "model", "confidence", "warnings")
            if description.get(key) not in (None, "", [], {})
        }

    def _append_semantic_lines(
        self,
        parts: list[str],
        *,
        caption: str | None,
        summary: str | None,
        text: str | None,
        details: dict[str, Any],
    ) -> None:
        if self.config.special_elements.include_caption and caption:
            parts.append(f"Caption: {caption}")
        if self.config.special_elements.include_summary and summary:
            parts.append(f"Summary: {summary}")
        if self.config.special_elements.include_description_text and text:
            parts.append(f"Description: {text}")
        if self.config.special_elements.include_description_details:
            parts.extend(detail_lines(details))

    def _retrieval_text(
        self,
        *,
        document_title: str | None,
        section_path: tuple[str, ...],
        element_type: Literal["figure", "table", "formula"],
        heading: str,
        caption: str | None,
        summary: str | None,
        text: str | None,
        details: dict[str, Any],
        table_text: str | None = None,
        formula_text: str | None = None,
        formula_latex: str | None = None,
    ) -> str:
        lines: list[str] = []
        if clean_text(document_title):
            lines.append(f"Document: {clean_text(document_title)}")
        section = path_text(section_path)
        if section:
            lines.append(f"Section: {section}")
        lines.append(f"{element_type.capitalize()}: {heading}")
        if self.config.special_elements.include_caption and caption:
            lines.append(f"Caption: {caption}")
        if self.config.special_elements.include_summary and summary:
            lines.append(f"Summary: {summary}")
        if self.config.special_elements.include_description_text and text:
            lines.append(f"Description: {text}")
        if self.config.special_elements.include_description_details:
            lines.extend(detail_lines(details))
        if table_text:
            lines.append(f"Table data:\n{table_text}")
        if formula_text:
            lines.append(f"Formula text: {formula_text}")
        if formula_latex:
            lines.append(f"Formula LaTeX: {formula_latex}")
        blocks = [block.strip() for block in lines if block and block.strip()]
        return "\n".join(dict.fromkeys(blocks))

    def _table_text(
        self,
        *,
        package: InputPackage,
        table: CanonicalTable,
    ) -> tuple[str | None, str | None]:
        asset = self._asset_path(table.assets, "markdown")
        candidates = [asset]
        if self.config.package_assets.infer_standard_sidecar_paths:
            candidates.append(f"tables/{table.id}.md")
        sidecar, source = package.first_existing_text(candidates)
        canonical = self._render_table(table)
        if self.config.package_assets.prefer_sidecar_files:
            if sidecar:
                return sidecar, source
            return canonical, "canonical" if canonical else None
        if canonical:
            return canonical, "canonical"
        return sidecar, source

    def _table_latex(self, *, package: InputPackage, table: CanonicalTable) -> str | None:
        asset = self._asset_path(table.assets, "latex")
        candidates = [asset]
        if self.config.package_assets.infer_standard_sidecar_paths:
            candidates.append(f"tables/{table.id}.tex")
        sidecar, _ = package.first_existing_text(candidates)
        canonical = clean_text(table.latex) or None
        if self.config.package_assets.prefer_sidecar_files:
            return sidecar or canonical
        return canonical or sidecar

    def _formula_latex(
        self,
        *,
        package: InputPackage,
        formula: CanonicalFormula,
    ) -> tuple[str | None, str | None]:
        asset = self._asset_path(formula.assets, "latex")
        candidates = [asset]
        if self.config.package_assets.infer_standard_sidecar_paths:
            candidates.append(f"formulas/{formula.id}.tex")
        sidecar, source = package.first_existing_text(candidates)
        canonical = clean_text(formula.latex) or None
        if self.config.package_assets.prefer_sidecar_files:
            if sidecar:
                return sidecar, source
            return canonical, "canonical" if canonical else None
        if canonical:
            return canonical, "canonical"
        return sidecar, source

    def _formula_text(
        self,
        *,
        package: InputPackage,
        formula: CanonicalFormula,
    ) -> tuple[str | None, str | None]:
        asset = self._asset_path(formula.assets, "text")
        candidates = [asset]
        if self.config.package_assets.infer_standard_sidecar_paths:
            candidates.append(f"formulas/{formula.id}.txt")
        sidecar, source = package.first_existing_text(candidates)
        canonical = clean_text(formula.text) or None
        if self.config.package_assets.prefer_sidecar_files:
            if sidecar:
                return sidecar, source
            return canonical, "canonical" if canonical else None
        if canonical:
            return canonical, "canonical"
        return sidecar, source

    @staticmethod
    def _asset_path(assets: dict[str, Any], key: str) -> str | None:
        value = assets.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            path = value.get("path")
            return str(path) if path else None
        return None

    @staticmethod
    def _render_table(table: CanonicalTable) -> str | None:
        columns = [clean_text(value) for value in table.columns]
        rows = [
            [clean_text(value) for value in row]
            for row in table.rows
            if isinstance(row, list | tuple)
        ]
        if columns:
            width = len(columns)
            lines = [
                "| " + " | ".join(columns) + " |",
                "| " + " | ".join("---" for _ in columns) + " |",
            ]
            for row in rows:
                normalized = (row + [""] * width)[:width]
                lines.append("| " + " | ".join(normalized) + " |")
            return "\n".join(lines)
        flattened = clean_text(table.flattened_text)
        return flattened or None

    def _apply_oversize_policy(
        self,
        *,
        content: str,
        retrieval_text: str,
    ) -> tuple[str, str, int, bool, list[str]]:
        token_count = self.token_counter.count(retrieval_text)
        max_tokens = self.config.special_elements.max_tokens
        if token_count <= max_tokens:
            return content, retrieval_text, token_count, False, []

        policy = self.config.special_elements.oversize_policy
        warning = (
            f"Standalone element has {token_count} tokens, above configured "
            f"max_tokens={max_tokens}."
        )
        if policy == "allow":
            return content, retrieval_text, token_count, True, [warning]
        if policy == "error":
            raise ValueError(warning)

        truncated_retrieval = self.token_counter.truncate(retrieval_text, max_tokens)
        truncated_content = self.token_counter.truncate(content, max_tokens)
        return (
            truncated_content,
            truncated_retrieval,
            self.token_counter.count(truncated_retrieval),
            True,
            [warning + " Retrieval text was truncated."],
        )
