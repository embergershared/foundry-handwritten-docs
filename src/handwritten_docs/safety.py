"""Conservative uniform-background masks; approval cannot override a failed gate."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from reportlab import rl_config
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .config import Settings
from .models import Annotation, PageAnalysis
from .storage import digest, file_hash


@dataclass
class MaskResult:
    mask: np.ndarray
    background: tuple[int, int, int]
    reasons: list[str]

    @property
    def sha256(self) -> str:
        return digest(
            [
                self.mask.shape,
                hashlib.sha256(self.mask.tobytes()).hexdigest(),
                self.background,
                self.reasons,
            ]
        )


def mask_region(
    image: Image.Image,
    page: PageAnalysis,
    annotation: Annotation,
    settings: Settings,
) -> MaskResult:
    """Reject grid lines, nonuniform backgrounds, contact and unknown protection."""
    pixels = np.asarray(image.convert("RGB"))
    mask = np.zeros(pixels.shape[:2], dtype=bool)
    reasons = []
    if not page.protection_complete:
        reasons.append("protected content inventory not locally attested")
    if not annotation.grounded:
        reasons.append("ungrounded removal geometry")
    if annotation.kind in ("signature", "drawing", "unknown", "formula"):
        reasons.append("protected or unsupported content/layout")
    if any(annotation.box.overlaps(b) for b in page.protected):
        reasons.append("protected region overlap")
    if any(
        annotation.box.overlaps(w.box) and i not in annotation.word_indexes
        for i, w in enumerate(page.words)
    ):
        reasons.append("other OCR content overlaps placement")
    if any(a.id != annotation.id and annotation.box.overlaps(a.box) for a in page.annotations):
        reasons.append("overlapping annotation bounds")
    x0, y0, x1, y1 = page.geometry.pixels(annotation.box, image.size)
    m = settings.margin_pixels
    if x0 < m or y0 < m or x1 + m > image.width or y1 + m > image.height:
        return MaskResult(mask, (255, 255, 255), reasons + ["insufficient boundary margin"])
    crop = pixels[y0 - m : y1 + m, x0 - m : x1 + m]
    ring = np.ones(crop.shape[:2], dtype=bool)
    ring[m:-m, m:-m] = False
    background = np.median(crop[ring], axis=0).astype(np.int16)
    deviation = np.max(np.abs(crop.astype(np.int16) - background), axis=2)
    if np.max(deviation[ring]) > settings.background_tolerance:
        reasons.append("ink/line contact or nonuniform background at boundary")
    local = pixels[y0:y1, x0:x1]
    dark = np.min(local, axis=2) < settings.ink_threshold
    if not np.any(dark):
        reasons.append("no removable ink")
    # Include antialiased edge pixels, but never outside the grounded region.
    ink = np.max(np.abs(local.astype(np.int16) - background), axis=2) > 1
    if np.any(np.max(local, axis=2) - np.min(local, axis=2) > settings.background_tolerance):
        reasons.append("colored ink or background unsupported")
    if np.min(background) < 245:
        reasons.append("only near-white uniform backgrounds supported")
    if np.any(np.mean(dark, axis=0) > 0.85) or np.any(np.mean(dark, axis=1) > 0.85):
        reasons.append("possible rule/grid/protected stroke")
    if not reasons:
        mask[y0:y1, x0:x1] = ink
    return MaskResult(mask, tuple(int(v) for v in background), reasons)


def clean(image: Image.Image, result: MaskResult) -> Image.Image:
    if result.reasons:
        raise ValueError("unsafe cleanup cannot be overridden")
    pixels = np.array(image.convert("RGB"))
    pixels[result.mask] = result.background
    return Image.fromarray(pixels)


def font(settings: Settings) -> tuple[str, str]:
    """Embed a licensed local font; ReportLab ships Bitstream Vera with its license."""
    path = settings.font_path or Path(rl_config.TTFSearchPath[0]) / "Vera.ttf"
    if not path.is_file():
        # ReportLab's resource directory is independent of host system font search order.
        import reportlab

        path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
        if settings.font_path:
            raise ValueError("configured font does not exist")
    name = "Local_" + file_hash(path)[:16]
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(path)))
    font_notice(settings)
    return name, file_hash(path)


def font_notice(settings: Settings) -> bytes:
    """Keep the supplied license with every PDF embedding the font."""
    import reportlab

    if settings.font_path:
        if settings.font_license_path is None:
            raise ValueError("custom font requires an explicit embedding/redistribution license")
        notice = settings.font_license_path
    else:
        notice = Path(reportlab.__file__).parent / "fonts" / "bitstream-vera-license.txt"
    if notice.stat().st_size > 1_000_000:
        raise ValueError("font license exceeds maximum size")
    return notice.read_bytes()


def fit(text: str, annotation: Annotation, settings: Settings) -> tuple[str, float]:
    """Single baseline only. No arbitrary LaTeX execution, multiline reflow or glyph fallback."""
    if not text.strip() or "\n" in text or any(ord(c) < 32 for c in text):
        raise ValueError("empty, multiline or control-character text unsupported")
    name, _ = font(settings)
    face = pdfmetrics.getFont(name).face
    if any(ord(c) not in face.charToGlyph for c in text):
        raise ValueError("font lacks required glyph")
    b = annotation.box
    size = min(settings.max_font_points, (b.y1 - b.y0) / 1.4)
    width = pdfmetrics.stringWidth(text, name, size)
    if width:
        size = min(size, size * (b.x1 - b.x0) / width)
    if size < settings.min_font_points:
        raise ValueError("text cannot fit above readability threshold")
    return name, size
