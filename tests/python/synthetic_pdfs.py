"""Synthetic PDFs for the tests, generated at run time: no real document is ever committed.

Pages are drawn with reportlab (``invariant`` output, so a file is the same on every run);
the scanned-style images are drawn with Pillow from a fixed random seed.
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

PRINTED_LINES = (
    "Contoso inspection report",
    "Site: Fabrikam warehouse 7",
    "Inspector notes follow below.",
)
# Drawn on the printed page so tests can check that reports never repeat document text.
SECRET_PHRASE = "Woodgrove account 4417"

SCAN_SIZE_PX = (850, 1100)
NOTE_SIZE_PX = (400, 120)
SEED = 20261029
INK_STROKES = 40
INK_SHADE = 30
PAPER_SHADE = 245
STROKE_WIDTH = 3
MARGIN_PT = 72
LINE_HEIGHT_PT = 18
ROTATED_DEGREES = 90
ENCRYPTION_PASSWORD = "synthetic"


def printed_text_chars() -> int:
    """The non-space characters :func:`write_printed` draws."""
    text = "".join(PRINTED_LINES) + SECRET_PHRASE
    return sum(1 for char in text if not char.isspace())


def ink_image(size: tuple[int, int], seed: int = SEED) -> Image.Image:
    """A grayscale image of random pen strokes on paper, like a scanned handwritten note."""
    rng = random.Random(seed)
    image = Image.new("L", size, PAPER_SHADE)
    draw = ImageDraw.Draw(image)
    width, height = size
    for _ in range(INK_STROKES):
        points = [(rng.randrange(width), rng.randrange(height)) for _ in range(3)]
        draw.line(points, fill=INK_SHADE, width=STROKE_WIDTH)
    return image


def _canvas(path: Path, **options: object) -> canvas.Canvas:
    return canvas.Canvas(str(path), pagesize=letter, invariant=True, **options)


def _draw_printed(pdf: canvas.Canvas) -> None:
    _, height = letter
    y = height - MARGIN_PT
    for line in (*PRINTED_LINES, SECRET_PHRASE):
        pdf.drawString(MARGIN_PT, y, line)
        y -= LINE_HEIGHT_PT


def _draw_scan(pdf: canvas.Canvas) -> None:
    width, height = letter
    pdf.drawImage(ImageReader(ink_image(SCAN_SIZE_PX)), 0, 0, width, height)


def write_printed(path: Path) -> Path:
    """One letter page of printed text, no image."""
    pdf = _canvas(path)
    _draw_printed(pdf)
    pdf.showPage()
    pdf.save()
    return path


def write_scanned(path: Path) -> Path:
    """One letter page that is a single full-page image, with no text layer."""
    pdf = _canvas(path)
    _draw_scan(pdf)
    pdf.showPage()
    pdf.save()
    return path


def write_mixed(path: Path) -> Path:
    """Three pages: printed text with a handwritten-note image, a scan, a rotated printed page."""
    pdf = _canvas(path)
    _draw_printed(pdf)
    note_width, note_height = NOTE_SIZE_PX
    pdf.drawImage(
        ImageReader(ink_image(NOTE_SIZE_PX, seed=SEED + 1)),
        MARGIN_PT,
        MARGIN_PT,
        note_width / 2,
        note_height / 2,
    )
    pdf.showPage()
    _draw_scan(pdf)
    pdf.showPage()
    pdf.setPageRotation(ROTATED_DEGREES)
    _draw_printed(pdf)
    pdf.showPage()
    pdf.save()
    return path


def write_image_in_form(path: Path) -> Path:
    """One page whose only image is inside a form XObject."""
    pdf = _canvas(path)
    pdf.beginForm("note")
    pdf.drawImage(ImageReader(ink_image(NOTE_SIZE_PX)), MARGIN_PT, MARGIN_PT)
    pdf.endForm()
    pdf.doForm("note")
    pdf.showPage()
    pdf.save()
    return path


def write_encrypted(path: Path) -> Path:
    """A printed page, encrypted with a user password."""
    pdf = _canvas(path, encrypt=ENCRYPTION_PASSWORD)
    _draw_printed(pdf)
    pdf.showPage()
    pdf.save()
    return path


def write_not_a_pdf(path: Path) -> Path:
    """A text file with a .pdf name."""
    path.write_text("This is not a PDF.\n", encoding="utf-8")
    return path


def write_truncated(path: Path) -> Path:
    """The first half of a valid PDF."""
    whole = write_printed(path).read_bytes()
    path.write_bytes(whole[: len(whole) // 2])
    return path
