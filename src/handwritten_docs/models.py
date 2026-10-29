"""Versioned contracts. Unknown fields and invalid geometry fail at the boundary."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Box(Record):
    """Axis-aligned display-space bounds in points, top-left origin."""

    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def ordered(self) -> "Box":
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("box must have positive area")
        return self

    def overlaps(self, other: "Box") -> bool:
        return (
            self.x0 < other.x1 and self.x1 > other.x0 and self.y0 < other.y1 and self.y1 > other.y0
        )

    def contains(self, other: "Box") -> bool:
        return (
            self.x0 <= other.x0
            and self.y0 <= other.y0
            and self.x1 >= other.x1
            and self.y1 >= other.y1
        )


class Geometry(Record):
    page: int = Field(ge=1)
    media: tuple[float, float, float, float]
    crop: tuple[float, float, float, float]
    rotation: Literal[0, 90, 180, 270]
    width: float = Field(gt=0)
    height: float = Field(gt=0)

    def pdf_to_display(self, x: float, y: float) -> tuple[float, float]:
        left, bottom, right, top = self.crop
        u, v = x - left, y - bottom
        w, h = right - left, top - bottom
        return {
            0: (u, h - v),
            90: (v, u),
            180: (w - u, v),
            270: (h - v, w - u),
        }[self.rotation]

    def display_to_pdf(self, x: float, y: float) -> tuple[float, float]:
        left, bottom, right, top = self.crop
        w, h = right - left, top - bottom
        u, v = {
            0: (x, h - y),
            90: (y, x),
            180: (w - x, y),
            270: (w - y, h - x),
        }[self.rotation]
        return u + left, v + bottom

    def pixels(self, box: Box, size: tuple[int, int]) -> tuple[int, int, int, int]:
        sx, sy = size[0] / self.width, size[1] / self.height
        return (
            math.floor(box.x0 * sx),
            math.floor(box.y0 * sy),
            math.ceil(box.x1 * sx),
            math.ceil(box.y1 * sy),
        )


class Word(Record):
    text: str = Field(min_length=1, max_length=1000)
    box: Box
    confidence: float = Field(ge=0, le=1)
    offset: int = Field(ge=0)
    length: int = Field(ge=1)
    handwritten: StrictBool
    style_confidence: float = Field(ge=0, le=1)


class Annotation(Record):
    id: str = Field(pattern=r"^[a-f0-9]{24}$")
    page: int = Field(ge=1)
    box: Box
    polygon: list[float]
    word_indexes: list[int]
    ocr_text: str
    text: str = Field(max_length=4000)
    kind: Literal["text", "number", "unit", "date", "formula", "signature", "drawing", "unknown"]
    grounded: StrictBool
    reasons: list[str]
    context: str = ""
    table_context: list[dict] = Field(default_factory=list)
    formula_context: list[dict] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)


class PageAnalysis(Record):
    geometry: Geometry
    raster_sha256: str
    words: list[Word]
    annotations: list[Annotation]
    protected: list[Box] = Field(default_factory=list)
    protection_complete: StrictBool = False
    ocr_complete: StrictBool = False
    tables: list[dict] = Field(default_factory=list)
    formulas: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_regions(self) -> "PageAnalysis":
        bounds = Box(x0=0, y0=0, x1=self.geometry.width, y1=self.geometry.height)
        ids = [a.id for a in self.annotations]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate annotation IDs")
        if any(not bounds.contains(w.box) for w in self.words):
            raise ValueError("word outside page")
        if any(not bounds.contains(b) for b in self.protected):
            raise ValueError("protected region outside page")
        for annotation in self.annotations:
            if annotation.page != self.geometry.page or not bounds.contains(annotation.box):
                raise ValueError("annotation page/geometry mismatch")
            indexes = annotation.word_indexes
            if len(set(indexes)) != len(indexes) or any(
                i < 0 or i >= len(self.words) for i in indexes
            ):
                raise ValueError("invalid annotation word indexes")
        return self


class Analysis(Record):
    schema_version: Literal["1"] = "1"
    source_sha256: str
    config_sha256: str
    evidence_sha256: str
    run_id: str
    provenance: dict
    pages: list[PageAnalysis]

    @model_validator(mode="after")
    def unique_pages(self) -> "Analysis":
        pages = [p.geometry.page for p in self.pages]
        if not pages or len(set(pages)) != len(pages):
            raise ValueError("analysis must contain unique selected pages")
        ids = [a.id for p in self.pages for a in p.annotations]
        if len(set(ids)) != len(ids):
            raise ValueError("analysis must contain unique annotation IDs")
        return self


class Decision(Record):
    annotation_id: str
    binding: str
    text: str = Field(max_length=4000)
    state: Literal["pending", "approved", "rejected"] = "pending"
    cleanup_reviewed: StrictBool = False
    reviewer: str = Field(default="", max_length=100)
    reviewed_at: str = ""

    @model_validator(mode="after")
    def signed(self) -> "Decision":
        if (self.state == "approved" or self.cleanup_reviewed) and (
            not self.reviewer.strip() or not self.reviewed_at.strip()
        ):
            raise ValueError("approved decisions require reviewer and reviewed_at")
        return self


class Review(Record):
    schema_version: Literal["1"] = "1"
    analysis_sha256: str
    decisions: list[Decision]

    @model_validator(mode="after")
    def unique(self) -> "Review":
        ids = [d.annotation_id for d in self.decisions]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate review decisions")
        return self


class Proposal(Record):
    id: str
    box: Box
    text: str = Field(max_length=4000)
    kind: Literal["text", "number", "unit", "date", "formula", "signature", "drawing", "unknown"]
    uncertainty: list[str]
    alternatives: list[str] = Field(default_factory=list)


class VisionResult(Record):
    schema_version: Literal["1"] = "1"
    status: Literal["complete", "refused", "truncated"]
    proposals: list[Proposal]
    protected: list[Box]
    protection_complete: StrictBool = False
    model: str
    prompt_version: str
    usage: dict = Field(default_factory=dict)
