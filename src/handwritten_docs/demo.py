"""Generate entirely synthetic local fixtures; no customer sample is opened."""

import argparse
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from .config import Settings
from .models import Box
from .safety import font
from .storage import file_hash, write_json


def generate(output: Path, rotation: int = 0) -> tuple[Path, Path]:
    """Deliberately fake handwriting, stale hidden OCR, protected ink, and unchanged page."""
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    name, _ = font(settings)
    path = pdfmetrics.getFont(name).face.filename
    image = Image.new("RGB", (600, 800), "white")
    draw = ImageDraw.Draw(image)
    local_font = ImageFont.truetype(path, 24)
    draw.text((100, 145), "Check clearance", fill="black", font=local_font)
    draw.text((100, 265), "42 mm", fill="black", font=local_font)
    draw.text((100, 385), "Crossing text", fill="black", font=local_font)
    draw.line((70, 400, 490, 400), fill="black", width=2)
    draw.line([(100, 560), (160, 530), (145, 580), (215, 535), (260, 565)], fill="black", width=3)
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(300, 400))
    canvas.drawImage(ImageReader(image), 0, 0, 300, 400)
    canvas.setFont("Helvetica", 10)
    canvas.drawString(35, 360, "Printed heading")
    hidden = canvas.beginText(50, 315)
    hidden.setFont("Helvetica", 12)
    hidden.setTextRenderMode(3)
    hidden.textOut("STALE_CLEARANCE")
    canvas.drawText(hidden)
    canvas.showPage()
    canvas.drawString(35, 350, "Unchanged reference page")
    canvas.save()
    stream.seek(0)
    reader = PdfReader(stream)
    reader.pages[0][NameObject("/Rotate")] = NumberObject(rotation)
    writer = PdfWriter()
    writer.append(reader)
    writer.add_outline_item("Synthetic first page", 0)
    writer.set_page_label(0, 1, style="/D", prefix="S-")
    source = output / "synthetic.pdf"
    with source.open("wb") as target:
        writer.write(target)
    from .pdf import geometry

    geom = geometry(PdfReader(source), 1)

    def transformed(box: Box) -> Box:
        points = [
            geom.pdf_to_display(x, 400 - y)
            for x, y in ((box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1))
        ]
        return Box(
            x0=min(p[0] for p in points),
            y0=min(p[1] for p in points),
            x1=max(p[0] for p in points),
            y1=max(p[1] for p in points),
        )

    def polygon(box: Box) -> list[float]:
        return [box.x0, box.y0, box.x1, box.y0, box.x1, box.y1, box.x0, box.y1]

    candidates = [
        ("Check clearance", "text", Box(x0=45, y0=65, x1=225, y1=95)),
        ("42 mm", "unit", Box(x0=45, y0=125, x1=150, y1=155)),
        ("Crossing text", "text", Box(x0=45, y0=185, x1=225, y1=215)),
    ]
    words = []
    proposals = []
    content = "Printed heading "
    heading_box = transformed(Box(x0=35, y0=30, x1=125, y1=42))
    words.append(
        {
            "content": "Printed heading",
            "polygon": polygon(heading_box),
            "confidence": 1.0,
            "span": {"offset": 0, "length": 15},
        }
    )
    styles = []
    for index, (text, kind, box) in enumerate(candidates):
        bounds = transformed(box)
        offset = len(content)
        content += text + " "
        span = {"offset": offset, "length": len(text)}
        words.append(
            {
                "content": text,
                "polygon": polygon(bounds),
                "confidence": 0.999,
                "span": span,
            }
        )
        styles.append({"isHandwritten": True, "confidence": 0.999, "spans": [span]})
        proposals.append(
            {
                "id": f"synthetic-{index}",
                "box": bounds.model_dump(),
                "text": text,
                "kind": kind,
                "uncertainty": [],
                "alternatives": [],
            }
        )
    evidence = {
        "schema_version": "1",
        "source_sha256": file_hash(source),
        "provenance": {
            "mode": "synthetic-offline-double",
            "model": "not-a-live-model",
            "usage": {"paid_calls": 0},
            "limitations": "Not real handwriting or accuracy evidence",
        },
        "pages": [
            {
                "source_page": 1,
                "di": {
                    "apiVersion": "2024-11-30",
                    "modelId": "prebuilt-layout",
                    "stringIndexType": "unicodeCodePoint",
                    "content": content,
                    "styles": styles,
                    "pages": [
                        {
                            "pageNumber": 1,
                            "width": geom.width,
                            "height": geom.height,
                            "unit": "pixel",
                            "words": words,
                        }
                    ],
                    "tables": [],
                },
                "vision": {
                    "schema_version": "1",
                    "status": "complete",
                    "proposals": proposals,
                    "protected": [],
                    "protection_complete": False,
                    "model": "synthetic-offline-double",
                    "prompt_version": "literal-v1",
                    "usage": {},
                },
                "local_review": {
                    "reviewer": "Synthetic fixture author",
                    "protection_complete": True,
                    "ocr_complete": True,
                    "protected": [
                        transformed(Box(x0=30, y0=198, x1=250, y1=203)).model_dump(),
                        transformed(Box(x0=40, y0=255, x1=145, y1=300)).model_dump(),
                    ],
                },
            }
        ],
    }
    evidence_path = output / "evidence.json"
    write_json(evidence_path, evidence)
    return source, evidence_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.output)


if __name__ == "__main__":
    main()
