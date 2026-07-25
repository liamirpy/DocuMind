from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Region:
    page: int
    left: float
    top: float
    right: float
    bottom: float
    origin: str = "BOTTOMLEFT"

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.top - self.bottom)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "bbox": {
                "left": self.left,
                "top": self.top,
                "right": self.right,
                "bottom": self.bottom,
                "coord_origin": self.origin,
            },
        }


def region_from_docling(provenance: list[dict[str, Any]] | None) -> Region | None:
    if not provenance:
        return None
    item = provenance[0]
    bbox = item.get("bbox") or {}
    try:
        return Region(
            page=int(item.get("page_no") or 0),
            left=float(bbox["l"]),
            top=float(bbox["t"]),
            right=float(bbox["r"]),
            bottom=float(bbox["b"]),
            origin=str(bbox.get("coord_origin") or "BOTTOMLEFT").upper(),
        )
    except (KeyError, TypeError, ValueError):
        return None


def regions_from_grobid(coords: str | None) -> list[Region]:
    if not coords:
        return []
    regions: list[Region] = []
    for fragment in coords.split(";"):
        parts = [part.strip() for part in fragment.split(",")]
        if len(parts) != 5:
            continue
        try:
            page = int(float(parts[0]))
            x = float(parts[1])
            y = float(parts[2])
            width = float(parts[3])
            height = float(parts[4])
        except ValueError:
            continue
        # GROBID coordinates are serialized as page,x,y,width,height. Keep the
        # source convention explicit rather than pretending they are Docling boxes.
        regions.append(
            Region(
                page=page,
                left=x,
                top=y,
                right=x + width,
                bottom=y + height,
                origin="TOPLEFT_XYWH",
            )
        )
    return regions
