"""Rebuild changed pages without retaining old content streams or stale OCR."""

import io
import os
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject, RectangleObject
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from .config import Settings
from .extraction import normalized, plain_prose
from .models import Analysis, Annotation, Decision, PageAnalysis, Review
from .pdf import open_pdf, render
from .pipeline import binding, protect_output, verify_analysis
from .safety import MaskResult, clean, fit, font, font_notice, mask_region
from .storage import digest, write_json


def automatic(annotation: Annotation, settings: Settings) -> bool:
    return (
        settings.calibration_id is not None
        and annotation.kind == "text"
        and plain_prose(annotation.text)
        and annotation.grounded
        and not annotation.reasons
        and not annotation.alternatives
        and normalized(annotation.text) == normalized(annotation.ocr_text)
    )


def eligibility(
    annotation: Annotation,
    decision: Decision,
    mask: MaskResult,
    settings: Settings,
) -> tuple[str, list[str]]:
    if decision.state == "rejected":
        return "preserved", ["reviewer rejected replacement"]
    if mask.reasons:
        return "blocked", mask.reasons
    try:
        fit(decision.text, annotation, settings)
    except ValueError as error:
        return "blocked", [str(error)]
    if decision.state == "approved":
        if not decision.cleanup_reviewed:
            return "pending", ["independent local cleanup inspection required"]
        return "replaced", ["explicit source-bound approval"]
    if (
        automatic(annotation, settings)
        and decision.text == annotation.text
        and decision.cleanup_reviewed
    ):
        return "replaced", ["calibrated automatic plain-text policy"]
    return "pending", ["explicit review required; no calibrated automatic evidence"]


def _display_transform(canvas: Canvas, page: PageAnalysis) -> None:
    geom = page.geometry
    origin = geom.display_to_pdf(0, geom.height)
    xaxis = geom.display_to_pdf(1, geom.height)
    yaxis = geom.display_to_pdf(0, geom.height - 1)
    canvas.transform(
        xaxis[0] - origin[0],
        xaxis[1] - origin[1],
        yaxis[0] - origin[0],
        yaxis[1] - origin[1],
        *origin,
    )


def _draw_text(
    canvas: Canvas,
    page: PageAnalysis,
    annotation: Annotation,
    text: str,
    settings: Settings,
) -> None:
    name, size = fit(text, annotation, settings)
    canvas.setFont(name, size)
    canvas.drawString(
        annotation.box.x0,
        page.geometry.height - annotation.box.y1 + size * 0.25,
        text,
    )


def rebuild_page(
    image: Image.Image,
    page: PageAnalysis,
    replacements: list[tuple[Annotation, str]],
    settings: Settings,
) -> PdfReader:
    stream = io.BytesIO()
    geom = page.geometry
    canvas = Canvas(
        stream, pagesize=(geom.media[2] - geom.media[0], geom.media[3] - geom.media[1])
    )
    _display_transform(canvas, page)
    canvas.drawImage(ImageReader(image), 0, 0, geom.width, geom.height)
    for annotation, text in replacements:
        _draw_text(canvas, page, annotation, text, settings)
    name, _ = font(settings)
    face = pdfmetrics.getFont(name).face
    for word in page.words:
        if any(word.box.overlaps(a.box) for a, _ in replacements):
            continue
        if any(ord(c) not in face.charToGlyph for c in word.text):
            raise ValueError("retained OCR has unsupported glyph; changed page cannot be rebuilt")
        # A rebuilt hidden OCR layer is not another copy of visible replacement text.
        text_object = canvas.beginText()
        text_object.setTextRenderMode(3)
        size = min(12, word.box.y1 - word.box.y0)
        text_object.setFont(name, size)
        text_object.setTextOrigin(word.box.x0, geom.height - word.box.y1)
        width = pdfmetrics.stringWidth(word.text, name, size)
        if width:
            text_object.setHorizScale((word.box.x1 - word.box.x0) / width * 100)
        text_object.textOut(word.text)
        canvas.drawText(text_object)
    canvas.showPage()
    canvas.save()
    stream.seek(0)
    rebuilt = PdfReader(stream)
    target = rebuilt.pages[0]
    target.mediabox = RectangleObject(geom.media)
    target.cropbox = RectangleObject(geom.crop)
    target[NameObject("/Rotate")] = NumberObject(geom.rotation)
    return rebuilt


def _outlines(reader: PdfReader, writer: PdfWriter) -> None:
    def copy(items: list, parent: object = None) -> None:
        previous = parent
        for item in items:
            if isinstance(item, list):
                copy(item, previous)
            else:
                number = reader.get_destination_page_number(item)
                if number is None:
                    raise ValueError("unsupported unresolved PDF bookmark")
                previous = writer.add_outline_item(item.title, number, parent=parent)

    copy(reader.outline)
    labels = reader.trailer["/Root"].get("/PageLabels")
    if labels is not None:
        writer.root_object[NameObject("/PageLabels")] = labels.get_object().clone(writer)


def export_pdf(
    source: Path,
    analysis: Analysis,
    review: Review,
    output: Path,
    settings: Settings,
) -> dict:
    protect_output(source, output)
    verify_analysis(source, analysis, settings)
    if review.analysis_sha256 != digest(analysis):
        raise ValueError("review belongs to another analysis")
    decisions = {d.annotation_id: d for d in review.decisions}
    expected = {a.id for p in analysis.pages for a in p.annotations}
    if set(decisions) != expected:
        raise ValueError("review decisions must exactly match all annotation IDs")
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "replacement.pdf"
    if source.resolve() == destination.resolve():
        raise ValueError("output must not overwrite original PDF")
    reader = open_pdf(source, settings)
    by_page = {p.geometry.page: p for p in analysis.pages}
    writer = PdfWriter()
    entries = []
    changed = []
    for number, original in enumerate(reader.pages, 1):
        page = by_page.get(number)
        if page is None:
            writer.add_page(original)
            continue
        image = render(source, page.geometry, settings)
        cleaned = image.copy()
        combined = np.zeros((image.height, image.width), dtype=bool)
        replacements = []
        page_entries = []
        for annotation in page.annotations:
            decision = decisions[annotation.id]
            mask = mask_region(image, page, annotation, settings)
            expected_binding = binding(
                analysis,
                annotation.model_dump(),
                mask.sha256,
                decision.text,
            )
            if decision.binding != expected_binding:
                raise ValueError(
                    "stale approval binding: source/content/geometry/mask/config changed"
                )
            status, reasons = eligibility(annotation, decision, mask, settings)
            if status == "replaced" and not page.ocr_complete:
                status, reasons = "blocked", ["complete retained OCR not locally attested"]
            if status == "replaced":
                cleaned = clean(cleaned, mask)
                combined |= mask.mask
                replacements.append((annotation, decision.text))
            page_entries.append(
                {
                    "id": annotation.id,
                    "page": number,
                    "status": status,
                    "reasons": reasons,
                    "binding": decision.binding,
                    "mask_sha256": mask.sha256,
                    "reviewer": decision.reviewer,
                    "reviewed_at": decision.reviewed_at,
                }
            )
        if replacements:
            if not np.array_equal(np.asarray(image)[~combined], np.asarray(cleaned)[~combined]):
                raise ValueError("cleanup changed pixels outside approved ink masks")
            rebuilt = rebuild_page(cleaned, page, replacements, settings)
            writer.add_page(rebuilt.pages[0])
            changed.append(number)
            cleaned.save(output / f"cleaned-{number}.png")
        else:
            writer.add_page(original)
        entries.extend(page_entries)
        image.close()
        cleaned.close()
    _outlines(reader, writer)
    notice = font_notice(settings)
    writer.add_attachment("font-license.txt", notice)
    writer.add_metadata({"/Title": "Derived transcription - not an authenticated original"})
    temp = destination.with_suffix(".pdf.tmp")
    try:
        with temp.open("wb") as stream:
            writer.write(stream)
        # Verify structural preservation before publishing the PDF.
        result = PdfReader(temp, strict=True)
        if len(result.pages) != len(reader.pages):
            raise ValueError("export page count differs")
        for index, page in enumerate(result.pages):
            original = reader.pages[index]
            if (
                page.mediabox != original.mediabox
                or page.cropbox != original.cropbox
                or page.rotation != original.rotation
            ):
                raise ValueError("export page geometry differs")
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()
    manifest = {
        "schema_version": "1",
        "source_sha256": analysis.source_sha256,
        "analysis_sha256": digest(analysis),
        "changed_pages": changed,
        "regions": entries,
        "counts": {
            s: sum(e["status"] == s for e in entries)
            for s in ("replaced", "preserved", "pending", "blocked")
        },
        "warnings": [
            "Derived transcription, not calculation validation or an authenticated original",
            "Bookmark titles/targets retained; detailed view positions normalized to Fit",
            "Automatic policy uncalibrated"
            if settings.calibration_id is None
            else "Calibration evidence supplied by local operator",
        ],
    }
    write_json(output / "manifest.json", manifest)
    write_json(output / "analysis.json", analysis)
    write_json(output / "review.json", review)
    (output / "font-license.txt").write_bytes(notice)
    return manifest
