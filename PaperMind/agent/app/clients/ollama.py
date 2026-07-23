import base64
import json
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.ollama_timeout_seconds),
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def is_alive(self) -> bool:
        try:
            response = await self._client.get("/api/tags")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def _vision_json(
        self,
        *,
        image_path: Path,
        prompt: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload = {
            "model": self.settings.ollama_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [encoded],
                }
            ],
            "format": schema,
            "stream": False,
            "keep_alive": self.settings.ollama_keep_alive,
            "options": {"temperature": self.settings.ollama_temperature},
        }
        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        body = response.json()
        content = ((body.get("message") or {}).get("content") or "").strip()
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Ollama structured response is not a JSON object.")
        return parsed

    async def describe_figure(
        self,
        image_path: Path,
        *,
        caption: str | None,
    ) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "summary": {"type": "string"},
                "figure_type": {"type": "string"},
                "visible_text": {"type": "array", "items": {"type": "string"}},
                "key_observations": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "description",
                "summary",
                "figure_type",
                "visible_text",
                "key_observations",
                "confidence",
                "warnings",
            ],
        }
        prompt = (
            "Analyze this scientific-article figure. Describe only visible evidence and the "
            "relationship between visible components. Do not invent values, causes, or "
            "conclusions. "
            "Identify whether it is a chart, diagram, photo, plot, workflow, or other figure. "
            f"The parser caption is: {caption or '[missing]'} ."
        )
        return await self._vision_json(image_path=image_path, prompt=prompt, schema=schema)

    async def describe_table(
        self,
        image_path: Path,
        *,
        caption: str | None,
        columns: list[str],
        rows: list[list[str]],
    ) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "summary": {"type": "string"},
                "key_observations": {"type": "array", "items": {"type": "string"}},
                "visible_headers": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "description",
                "summary",
                "key_observations",
                "visible_headers",
                "confidence",
                "warnings",
            ],
        }
        prompt = (
            "Describe this scientific table using only information visible in the image. "
            "Explain what is compared or reported, identify the visible headers, and summarize "
            "obvious patterns only when directly supported by the cells. Do not calculate, infer "
            "missing values, or claim statistical significance unless explicitly shown. "
            f"Parser caption: {caption or '[missing]'}. "
            f"Parser columns: {columns}. Parser row count: {len(rows)}."
        )
        return await self._vision_json(image_path=image_path, prompt=prompt, schema=schema)

    async def repair_table(
        self,
        image_path: Path,
        *,
        caption: str | None,
    ) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "columns": {"type": "array", "items": {"type": "string"}},
                "rows": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "notes": {"type": "array", "items": {"type": "string"}},
                "description": {"type": "string"},
                "summary": {"type": "string"},
                "key_observations": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "columns",
                "rows",
                "notes",
                "description",
                "summary",
                "key_observations",
                "confidence",
                "warnings",
            ],
        }
        prompt = (
            "Transcribe this scientific table exactly. Preserve column order and values. "
            "Use an empty string for unreadable cells and report uncertainty in warnings. "
            "Do not calculate or infer missing numbers. Also provide a grounded description and "
            "brief summary of what the visible table reports. "
            f"The parser caption is: {caption or '[missing]'} ."
        )
        return await self._vision_json(image_path=image_path, prompt=prompt, schema=schema)

    async def describe_formula(
        self,
        image_path: Path,
        *,
        latex: str | None,
        plain_text: str | None,
        parser_candidates: list[str],
    ) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "summary": {"type": "string"},
                "visible_structure": {"type": "array", "items": {"type": "string"}},
                "symbols": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "visible_role": {"type": "string"},
                        },
                        "required": ["symbol", "visible_role"],
                    },
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "description",
                "summary",
                "visible_structure",
                "symbols",
                "confidence",
                "warnings",
            ],
        }
        prompt = (
            "Describe the visible mathematical formula without inventing domain meaning that is "
            "not shown. "
            "Explain its visible structure, operators, terms, indices, fractions, matrices, "
            "or delimiters. A symbol's role should be visual/syntactic unless its meaning is "
            "explicit. "
            f"Current LaTeX candidate: {latex or '[missing]'}. "
            f"Plain-text candidate: {plain_text or '[missing]'}. "
            f"Other parser candidates: {parser_candidates}."
        )
        return await self._vision_json(image_path=image_path, prompt=prompt, schema=schema)

    async def transcribe_formula(
        self,
        image_path: Path,
        *,
        parser_candidates: list[str],
    ) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "latex": {"type": "string"},
                "plain_text": {"type": "string"},
                "description": {"type": "string"},
                "summary": {"type": "string"},
                "visible_structure": {"type": "array", "items": {"type": "string"}},
                "symbols": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "visible_role": {"type": "string"},
                        },
                        "required": ["symbol", "visible_role"],
                    },
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "latex",
                "plain_text",
                "description",
                "summary",
                "visible_structure",
                "symbols",
                "confidence",
                "warnings",
            ],
        }
        prompt = (
            "Transcribe the displayed mathematical formula into valid LaTeX. Preserve subscripts, "
            "superscripts, Greek letters, delimiters, operators, matrices, and equation structure. "
            "Do not add explanatory prose to the LaTeX field. Also provide a grounded description "
            "of the visible mathematical structure without inventing domain meaning. "
            f"Parser candidates: {parser_candidates}."
        )
        return await self._vision_json(image_path=image_path, prompt=prompt, schema=schema)
