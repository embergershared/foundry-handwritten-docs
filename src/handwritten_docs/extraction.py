"""Ground service proposals in DI word geometry, never in model confidence."""

import math
import re
from typing import Any

from .config import Settings
from .models import Annotation, Box, Geometry, VisionResult, Word
from .storage import digest


def overlaps_span(first: dict, second: dict) -> bool:
    return (
        first["offset"] < second["offset"] + second["length"]
        and second["offset"] < first["offset"] + first["length"]
    )


def polygon_box(polygon: list[float], sx: float, sy: float) -> Box:
    if len(polygon) != 8 or not all(math.isfinite(v) for v in polygon):
        raise ValueError("expected finite quadrilateral")
    xs, ys = polygon[::2], polygon[1::2]
    return Box(x0=min(xs) * sx, y0=min(ys) * sy, x1=max(xs) * sx, y1=max(ys) * sy)


def parse_di(raw: dict[str, Any], geom: Geometry) -> list[Word]:
    """Require code-point offsets and an explicitly mapped single rendered page."""
    if raw.get("apiVersion") != "2024-11-30" or raw.get("modelId") != "prebuilt-layout":
        raise ValueError("DI requires GA 2024-11-30 prebuilt-layout")
    if raw.get("stringIndexType") != "unicodeCodePoint":
        raise ValueError("DI offsets must use unicodeCodePoint")
    pages = raw["pages"]
    if len(pages) != 1 or pages[0]["pageNumber"] != 1:
        raise ValueError("evidence must be a one-page request with explicit source mapping")
    page = pages[0]
    if page["unit"] not in ("inch", "pixel") or page["width"] <= 0 or page["height"] <= 0:
        raise ValueError("invalid DI units or page dimensions")
    if abs(page["width"] / page["height"] - geom.width / geom.height) > 0.002:
        raise ValueError("DI orientation/aspect differs from rendered page")
    content = raw["content"]
    words = []
    sx, sy = geom.width / page["width"], geom.height / page["height"]
    bounds = Box(x0=0, y0=0, x1=geom.width, y1=geom.height)
    for word in page.get("words", []):
        span = word["span"]
        offset, length = span["offset"], span["length"]
        if offset < 0 or length <= 0 or offset + length > len(content):
            raise ValueError("DI span outside code-point content")
        if content[offset : offset + length] != word["content"]:
            raise ValueError("DI word/span content mismatch")
        box = polygon_box(word["polygon"], sx, sy)
        if not bounds.contains(box):
            raise ValueError("DI word outside page")
        styles = [
            s
            for s in raw.get("styles", [])
            if s.get("isHandwritten") is True and any(overlaps_span(span, ss) for ss in s["spans"])
        ]
        covered = {
            index
            for style in styles
            for part in style["spans"]
            for index in range(
                max(offset, part["offset"]),
                min(offset + length, part["offset"] + part["length"]),
            )
        }
        words.append(
            Word(
                text=word["content"],
                box=box,
                confidence=word["confidence"],
                offset=offset,
                length=length,
                handwritten=bool(styles),
                style_confidence=(
                    min(s["confidence"] for s in styles) if len(covered) == length else 0
                ),
            )
        )
    return words


def normalized(text: str) -> str:
    """Only collapse whitespace; do not normalize punctuation, digits, case or units."""
    return " ".join(text.split())


def plain_prose(text: str) -> bool:
    """Conservative prose gate: short unit-like tokens never qualify automatically."""
    return (
        bool(text.strip())
        and len(text.split()) >= 2
        and all(c.isalpha() or c in " ,.';:!?-\n" for c in text)
        and not re.search(
            r"\b(?:mm|cm|km|kg|mg|Hz|Pa|psi|ft|in|mol|amps?|volts?|ohms?|"
            r"metres?|meters?|feet|inches|seconds?|minutes?|hours?|degrees?|"
            r"years?|days?|weeks?|months?|"
            r"january|february|march|april|may|june|july|august|september|october|"
            r"november|december|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
            r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
            r"hundred|thousand|million|billion|first|second|third|fourth|fifth|sixth|"
            r"seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|"
            r"fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|twentieth|"
            r"thirtieth|fortieth|fiftieth|sixtieth|seventieth|eightieth|ninetieth)\b",
            text,
            re.I,
        )
    )


def reconcile(
    words: list[Word],
    vision: VisionResult,
    geom: Geometry,
    settings: Settings,
) -> list[Annotation]:
    if vision.status != "complete":
        raise ValueError(f"vision response {vision.status}; no checkpoint produced")
    if vision.prompt_version != settings.prompt_version:
        raise ValueError("vision prompt version mismatch")
    bounds = Box(x0=0, y0=0, x1=geom.width, y1=geom.height)
    ids = [p.id for p in vision.proposals]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate vision proposal IDs")
    result: list[Annotation] = []
    covered: set[int] = set()
    for proposal in vision.proposals:
        if not bounds.contains(proposal.box):
            raise ValueError("vision proposal outside rendered page")
        indexes = [i for i, w in enumerate(words) if proposal.box.overlaps(w.box)]
        grounded = bool(indexes) and all(
            words[i].handwritten and proposal.box.contains(words[i].box) for i in indexes
        )
        ocr = " ".join(words[i].text for i in indexes)
        reasons = list(proposal.uncertainty)
        if not grounded:
            reasons.append("vision geometry not grounded in handwriting words")
        if normalized(ocr) != normalized(proposal.text):
            reasons.append("DI/vision transcription disagreement")
        if any(words[i].confidence < settings.ocr_threshold for i in indexes):
            reasons.append("weak OCR evidence")
        if any(words[i].style_confidence < settings.style_threshold for i in indexes):
            reasons.append("weak handwriting evidence")
        covered.update(indexes)
        b = proposal.box
        polygon = [b.x0, b.y0, b.x1, b.y0, b.x1, b.y1, b.x0, b.y1]
        result.append(
            Annotation(
                id=digest([geom.page, proposal.id, polygon])[:24],
                page=geom.page,
                box=b,
                polygon=polygon,
                word_indexes=indexes,
                ocr_text=ocr,
                text=proposal.text,
                kind=proposal.kind,
                grounded=grounded,
                reasons=reasons,
                context=" ".join(
                    w.text
                    for w in words[
                        max(0, min(indexes, default=0) - 2) : max(indexes, default=0) + 3
                    ]
                ),
                alternatives=proposal.alternatives,
            )
        )
    for i, word in enumerate(words):
        if word.handwritten and i not in covered:
            b = word.box
            result.append(
                Annotation(
                    id=digest([geom.page, i, b.model_dump()])[:24],
                    page=geom.page,
                    box=b,
                    polygon=[b.x0, b.y0, b.x1, b.y0, b.x1, b.y1, b.x0, b.y1],
                    word_indexes=[i],
                    ocr_text=word.text,
                    text=word.text,
                    kind="unknown",
                    grounded=True,
                    reasons=["DI handwriting without vision confirmation"],
                )
            )
    return result


def attach_structure(annotations: list[Annotation], raw: dict, geom: Geometry) -> None:
    """Keep row/column and literal formula context separate from transcription."""
    page = raw["pages"][0]
    sx, sy = geom.width / page["width"], geom.height / page["height"]
    for annotation in annotations:
        for table_index, table in enumerate(raw.get("tables", [])):
            for cell in table.get("cells", []):
                regions = cell.get("boundingRegions", [])
                if any(
                    region["pageNumber"] == 1
                    and annotation.box.overlaps(polygon_box(region["polygon"], sx, sy))
                    for region in regions
                ):
                    annotation.table_context.append(
                        {
                            "table": table_index,
                            "row": cell["rowIndex"],
                            "column": cell["columnIndex"],
                            "text": cell["content"],
                            "row_span": cell.get("rowSpan", 1),
                            "column_span": cell.get("columnSpan", 1),
                        }
                    )
        for formula in page.get("formulas", []):
            if annotation.box.overlaps(polygon_box(formula["polygon"], sx, sy)):
                annotation.formula_context.append(formula)
                annotation.kind = "formula"
                annotation.reasons.append("formula layout requires unsupported renderer")
