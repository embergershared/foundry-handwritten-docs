"""PDF inventory and bounded, one-page-at-a-time rendering."""

import math
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader

from .config import Settings
from .models import Geometry


def open_pdf(path: Path, settings: Settings) -> PdfReader:
    if path.stat().st_size > settings.max_input_bytes:
        raise ValueError("PDF exceeds configured byte limit")
    reader = PdfReader(path, strict=True)
    if reader.is_encrypted:
        raise ValueError("encrypted inputs are not supported")
    root = reader.trailer["/Root"]
    if "/AcroForm" in root or "/Perms" in root:
        raise ValueError(
            "form/signed inputs are not supported; signature validity cannot be retained"
        )
    for page in reader.pages:
        if page.get("/Annots"):
            raise ValueError("interactive annotations must be flattened in a separate source copy")
        if float(page.get("/UserUnit", 1)) != 1:
            raise ValueError("nonstandard PDF UserUnit is not supported")
    return reader


def geometry(reader: PdfReader, number: int) -> Geometry:
    page = reader.pages[number - 1]
    crop = tuple(float(v) for v in page.cropbox)
    media = tuple(float(v) for v in page.mediabox)
    rotation = int(page.rotation) % 360
    if rotation not in (0, 90, 180, 270):
        raise ValueError("unsupported page rotation")
    if not all(math.isfinite(v) for v in (*crop, *media)):
        raise ValueError("nonfinite PDF geometry")
    left, bottom, right, top = crop
    if not (media[0] <= left < right <= media[2] and media[1] <= bottom < top <= media[3]):
        raise ValueError("CropBox must be positive and contained within MediaBox")
    w, h = right - left, top - bottom
    width, height = (h, w) if rotation in (90, 270) else (w, h)
    return Geometry(
        page=number, media=media, crop=crop, rotation=rotation, width=width, height=height
    )


def render(path: Path, geom: Geometry, settings: Settings) -> Image.Image:
    scale = settings.dpi / 72
    if math.ceil(geom.width * scale) * math.ceil(geom.height * scale) > settings.max_pixels:
        raise ValueError("render exceeds configured pixel limit")
    with pdfium.PdfDocument(path) as document:
        page = document[geom.page - 1]
        try:
            if (
                abs(page.get_width() - geom.width) > 0.1
                or abs(page.get_height() - geom.height) > 0.1
            ):
                raise ValueError("renderer and canonical CropBox/rotation disagree")
            bitmap = page.render(scale=scale)
            try:
                return bitmap.to_pil().convert("RGB")
            finally:
                bitmap.close()
        finally:
            page.close()
