"""One configuration boundary; cloud execution is deliberately not exposed by the CLI."""

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    """Limits and algorithm versions are part of every provenance/approval digest."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    dpi: int = Field(default=144, ge=72, le=300)
    max_input_bytes: int = Field(default=50_000_000, ge=1)
    max_pages: int = Field(default=20, ge=1, le=100)
    max_pixels: int = Field(default=30_000_000, ge=1)
    max_json_bytes: int = Field(default=20_000_000, ge=1)
    max_regions_per_page: int = Field(default=200, ge=1, le=2000)
    max_words_per_page: int = Field(default=20000, ge=1)
    ink_threshold: int = Field(default=220, ge=1, le=254)
    background_tolerance: int = Field(default=8, ge=0, le=20)
    margin_pixels: int = Field(default=3, ge=2, le=20)
    min_font_points: float = Field(default=7, ge=6, le=24)
    max_font_points: float = Field(default=16, ge=7, le=72)
    ocr_threshold: float = Field(default=0.99, ge=0, le=1)
    style_threshold: float = Field(default=0.99, ge=0, le=1)
    calibration_id: str | None = None
    algorithm: str = "uniform-mask-v1"
    prompt_version: str = "literal-v1"
    di_api_version: str = "2024-11-30"
    font_path: Path | None = None
    font_license_path: Path | None = None


def load_settings(path: Path | None = None) -> Settings:
    """Read configuration once; no secret files are loaded."""
    settings = Settings.model_validate_json(path.read_bytes()) if path else Settings()
    font = os.environ.get("HANDWRITTEN_DOCS_FONT")
    return settings.model_copy(update={"font_path": Path(font)}) if font else settings
