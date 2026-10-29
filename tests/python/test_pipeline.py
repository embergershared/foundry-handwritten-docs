"""Entirely synthetic real-PDF regression tests; never read the attached sample."""

import asyncio
from pathlib import Path

import numpy as np
import pytest
from azure.core.exceptions import HttpResponseError, ServiceRequestError
from PIL import Image, ImageDraw
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, RectangleObject

from handwritten_docs.cli import main
from handwritten_docs.config import Settings
from handwritten_docs.demo import generate
from handwritten_docs.export import automatic, export_pdf
from handwritten_docs.extraction import attach_structure, parse_di, plain_prose, reconcile
from handwritten_docs.models import Box, Decision, Geometry, Review, VisionResult
from handwritten_docs.pdf import geometry, open_pdf, render
from handwritten_docs.pipeline import analyze, create_review
from handwritten_docs.report import write_report
from handwritten_docs.safety import clean, fit, mask_region
from handwritten_docs.services import Authorization, retry
from handwritten_docs.storage import file_hash, read_json, select_pages, write_json


@pytest.fixture
def case(tmp_path: Path) -> tuple:
    source, evidence = generate(tmp_path / "input")
    settings = Settings()
    output = tmp_path / "run"
    analysis = analyze(source, evidence, output, "1", settings)
    review = create_review(source, analysis, output, settings)
    return source, evidence, output, settings, analysis, review


def approve(review: Review, index: int) -> None:
    decision = review.decisions[index]
    decision.state = "approved"
    decision.cleanup_reviewed = True
    decision.reviewer = "Synthetic reviewer"
    decision.reviewed_at = "2026-10-29T00:00:00Z"


def test_full_export_removes_stale_ocr_and_preserves_original(case: tuple) -> None:
    source, _, output, settings, analysis, review = case
    original_hash = file_hash(source)
    assert "STALE_CLEARANCE" in PdfReader(source).pages[0].extract_text()
    approve(review, 0)
    approve(review, 2)  # Approval must never override a protected crossing rule.
    manifest = export_pdf(source, analysis, review, output, settings)
    assert manifest["counts"] == {"replaced": 1, "preserved": 0, "pending": 1, "blocked": 1}
    result = PdfReader(output / "replacement.pdf")
    text = result.pages[0].extract_text()
    assert text.count("Check clearance") == 1
    assert "STALE_CLEARANCE" not in text
    assert "Printed heading" in text
    assert "42 mm" in text
    assert result.pages[1].get_contents().get_data() == (
        PdfReader(source).pages[1].get_contents().get_data()
    )
    assert result.page_labels == PdfReader(source).page_labels
    assert result.outline[0].title == "Synthetic first page"
    assert file_hash(source) == original_hash
    assert b"/FontFile2" in (output / "replacement.pdf").read_bytes()


def test_zero_raster_changes_outside_mask_and_final_region(case: tuple) -> None:
    source, _, output, settings, analysis, review = case
    page = analysis.pages[0]
    image = render(source, page.geometry, settings)
    mask = mask_region(image, page, page.annotations[0], settings)
    assert not mask.reasons
    cleaned = clean(image, mask)
    assert np.array_equal(np.asarray(image)[~mask.mask], np.asarray(cleaned)[~mask.mask])
    assert np.count_nonzero(np.any(np.asarray(image) != np.asarray(cleaned), axis=2)) > 0
    approve(review, 0)
    export_pdf(source, analysis, review, output, settings)
    final = render(output / "replacement.pdf", page.geometry, settings)
    outside = np.ones(mask.mask.shape, dtype=bool)
    x0, y0, x1, y1 = page.geometry.pixels(page.annotations[0].box, image.size)
    outside[y0:y1, x0:x1] = False
    difference = np.abs(np.asarray(image).astype(int) - np.asarray(final).astype(int))
    # PDFium image recomposition can differ by one intensity level at raster edges.
    assert np.max(difference[outside]) <= 1
    assert np.count_nonzero(np.max(difference[outside], axis=1) > 1) == 0


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rotation_export_preserves_display_and_boxes(tmp_path: Path, rotation: int) -> None:
    source, evidence = generate(tmp_path / "input", rotation)
    settings = Settings(min_font_points=6)
    analysis = analyze(source, evidence, tmp_path / "run", "1", settings)
    review = create_review(source, analysis, tmp_path / "run", settings)
    if rotation in (90, 270):
        # Sideways multiword text cannot fit horizontally; explicit short literal correction
        # exercises the transform without implying support for vertical text layout.
        review.decisions[0].text = "OK"
        review = create_review(source, analysis, tmp_path / "run", settings, review)
    approve(review, 0)
    manifest = export_pdf(source, analysis, review, tmp_path / "run", settings)
    assert manifest["counts"]["replaced"] == 1
    result = PdfReader(tmp_path / "run" / "replacement.pdf")
    assert result.pages[0].rotation == rotation
    assert result.pages[0].cropbox == PdfReader(source).pages[0].cropbox
    expected = "OK" if rotation in (90, 270) else "Check clearance"
    assert expected in result.pages[0].extract_text()
    geom = analysis.pages[0].geometry
    assert (
        render(source, geom, settings).size
        == render(tmp_path / "run" / "replacement.pdf", geom, settings).size
    )
    before = np.asarray(render(source, geom, settings))
    after = np.asarray(render(tmp_path / "run" / "replacement.pdf", geom, settings))
    outside = np.ones(before.shape[:2], dtype=bool)
    x0, y0, x1, y1 = geom.pixels(
        analysis.pages[0].annotations[0].box, (before.shape[1], before.shape[0])
    )
    outside[y0:y1, x0:x1] = False
    assert np.max(np.abs(before.astype(int) - after.astype(int))[outside]) <= 1


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_crop_rotation_coordinate_roundtrips(rotation: int) -> None:
    width, height = (200, 300) if rotation in (0, 180) else (300, 200)
    geom = Geometry(
        page=2,
        media=(-10, -20, 400, 500),
        crop=(30, 40, 230, 340),
        rotation=rotation,
        width=width,
        height=height,
    )
    for point in [(30, 40), (230, 340), (65.5, 98.25)]:
        assert geom.display_to_pdf(*geom.pdf_to_display(*point)) == pytest.approx(point)
    b = Box(x0=10, y0=20, x1=30, y1=40)
    assert geom.pixels(b, (width * 2, height * 2)) == (20, 40, 60, 80)


def test_real_cropbox_render(tmp_path: Path) -> None:
    source, _ = generate(tmp_path)
    reader = PdfReader(source)
    reader.pages[0].cropbox = RectangleObject((20, 20, 280, 380))
    writer = PdfWriter()
    writer.append(reader)
    cropped = tmp_path / "cropped.pdf"
    with cropped.open("wb") as stream:
        writer.write(stream)
    geom = geometry(open_pdf(cropped, Settings()), 1)
    assert render(cropped, geom, Settings()).size == (520, 720)


def test_real_cropbox_export_preserves_original_offsets(tmp_path: Path) -> None:
    source, evidence_path = generate(tmp_path / "input")
    reader = PdfReader(source)
    reader.pages[0].cropbox = RectangleObject((20, 20, 280, 380))
    writer = PdfWriter()
    writer.append(reader)
    cropped = tmp_path / "input" / "cropped.pdf"
    with cropped.open("wb") as stream:
        writer.write(stream)
    evidence = read_json(evidence_path, 1_000_000)
    evidence["source_sha256"] = file_hash(cropped)
    entry = evidence["pages"][0]
    entry["di"]["pages"][0]["width"] = 260
    entry["di"]["pages"][0]["height"] = 360
    for word in entry["di"]["pages"][0]["words"]:
        word["polygon"] = [v - 20 for v in word["polygon"]]
    for proposal in entry["vision"]["proposals"]:
        proposal["box"] = {key: value - 20 for key, value in proposal["box"].items()}
    entry["local_review"]["protected"] = [
        {key: value - 20 for key, value in box.items()}
        for box in entry["local_review"]["protected"]
    ]
    write_json(evidence_path, evidence)
    settings = Settings()
    output = tmp_path / "run"
    analysis = analyze(cropped, evidence_path, output, "1", settings)
    review = create_review(cropped, analysis, output, settings)
    approve(review, 0)
    manifest = export_pdf(cropped, analysis, review, output, settings)
    assert manifest["counts"]["replaced"] == 1
    result = PdfReader(output / "replacement.pdf")
    assert result.pages[0].cropbox == RectangleObject((20, 20, 280, 380))
    before = np.asarray(render(cropped, analysis.pages[0].geometry, settings))
    after = np.asarray(render(output / "replacement.pdf", analysis.pages[0].geometry, settings))
    outside = np.ones(before.shape[:2], dtype=bool)
    x0, y0, x1, y1 = analysis.pages[0].geometry.pixels(
        analysis.pages[0].annotations[0].box, (before.shape[1], before.shape[0])
    )
    outside[y0:y1, x0:x1] = False
    assert np.max(np.abs(before.astype(int) - after.astype(int))[outside]) <= 1


def test_numeric_requires_approval_even_with_calibration(case: tuple) -> None:
    _, _, _, _, analysis, review = case
    settings = Settings(calibration_id="synthetic-policy-test-not-pilot-calibration")
    assert automatic(analysis.pages[0].annotations[0], settings)
    assert not automatic(analysis.pages[0].annotations[1], settings)
    assert review.decisions[1].state == "pending"


@pytest.mark.parametrize(
    "text",
    [
        "42",
        "ID-42",
        "12/04/2026",
        "5 mm",
        "x = y",
        "kg",
        "ten kg",
        "forty years",
        "ninety days",
        "eleven metres",
        "twelfth month",
    ],
)
def test_nonprose_never_auto(text: str) -> None:
    assert not plain_prose(text)


def test_uncalibrated_default_no_automatic_replacement(case: tuple) -> None:
    source, _, output, settings, analysis, review = case
    manifest = export_pdf(source, analysis, review, output, settings)
    assert manifest["counts"]["replaced"] == 0
    assert PdfReader(source).pages[0].get_contents().get_data() == (
        PdfReader(output / "replacement.pdf").pages[0].get_contents().get_data()
    )


def test_missing_ocr_attestation_preserves_original_rejection_reasons(case: tuple) -> None:
    source, _, output, settings, analysis, review = case
    analysis.pages[0].ocr_complete = False
    review = create_review(source, analysis, output, settings)
    review.decisions[0].state = "rejected"
    approve(review, 2)
    manifest = export_pdf(source, analysis, review, output, settings)
    assert manifest["regions"][0]["status"] == "preserved"
    assert "protected region overlap" in manifest["regions"][2]["reasons"]


def test_numeric_approval_replaces_without_calculating(case: tuple) -> None:
    source, _, output, settings, analysis, review = case
    approve(review, 1)
    manifest = export_pdf(source, analysis, review, output, settings)
    assert manifest["counts"]["replaced"] == 1
    assert PdfReader(output / "replacement.pdf").pages[0].extract_text().count("42 mm") == 1


def test_stale_content_approval_rejected_and_refresh_resets(case: tuple) -> None:
    source, _, output, settings, analysis, review = case
    approve(review, 0)
    review.decisions[0].text = "Changed literal words"
    with pytest.raises(ValueError, match="stale approval"):
        export_pdf(source, analysis, review, output, settings)
    fresh = create_review(source, analysis, output, settings, review)
    assert fresh.decisions[0].state == "pending"
    assert fresh.decisions[0].text == "Changed literal words"
    assert fresh.decisions[0].binding != review.decisions[0].binding


@pytest.mark.parametrize("field", ["box", "text", "config", "protection"])
def test_approval_invalidated_by_proposal_changes(case: tuple, field: str) -> None:
    source, _, output, settings, analysis, review = case
    approve(review, 0)
    modified = analysis.model_copy(deep=True)
    if field == "box":
        modified.pages[0].annotations[0].box.x0 += 1
    elif field == "text":
        modified.pages[0].annotations[0].text += "!"
    elif field == "config":
        settings = Settings(dpi=150)
    else:
        modified.pages[0].protection_complete = False
    with pytest.raises(ValueError):
        export_pdf(source, modified, review, output, settings)


def test_changed_source_rejected(case: tuple) -> None:
    source, _, output, settings, analysis, review = case
    with source.open("ab") as stream:
        stream.write(b"\n% source changed\n")
    with pytest.raises(ValueError, match="source changed"):
        export_pdf(source, analysis, review, output, settings)


def test_grid_and_protected_ink_cannot_be_approved(case: tuple) -> None:
    source, _, _, settings, analysis, _ = case
    page = analysis.pages[0]
    image = render(source, page.geometry, settings)
    result = mask_region(image, page, page.annotations[2], settings)
    assert result.reasons
    assert not np.any(result.mask)
    with pytest.raises(ValueError, match="cannot be overridden"):
        clean(image, result)


def test_background_and_boundary_abstention(case: tuple) -> None:
    _, _, _, settings, analysis, _ = case
    page, annotation = analysis.pages[0], analysis.pages[0].annotations[0]
    image = Image.new("RGB", (600, 800), (230, 230, 230))
    ImageDraw.Draw(image).text((100, 145), "ink", fill="black")
    assert mask_region(image, page, annotation, settings).reasons
    white = Image.new("RGB", (600, 800), "white")
    ImageDraw.Draw(white).line((20, 150, 500, 150), fill="black")
    assert mask_region(white, page, annotation, settings).reasons


def test_formula_and_unsupported_glyphs_remain_unchanged(case: tuple) -> None:
    source, _, _, settings, analysis, _ = case
    page = analysis.pages[0]
    formula = page.annotations[0].model_copy(update={"kind": "formula"})
    assert mask_region(render(source, page.geometry, settings), page, formula, settings).reasons
    with pytest.raises(ValueError, match="glyph"):
        fit("漢字", page.annotations[0], settings)
    with pytest.raises(ValueError):
        fit("a\nb", page.annotations[0], settings)
    with pytest.raises(ValueError, match="fit"):
        fit("A" * 1000, page.annotations[0], settings)


def test_unicode_codepoint_spans_and_partial_styles(case: tuple) -> None:
    _, evidence_path, _, _, analysis, _ = case
    raw = read_json(evidence_path, 1_000_000)["pages"][0]["di"]
    raw["content"] = "😀 café"
    raw["pages"][0]["words"] = [
        {
            "content": "café",
            "confidence": 1,
            "polygon": [45, 65, 225, 65, 225, 95, 45, 95],
            "span": {"offset": 2, "length": 4},
        }
    ]
    raw["styles"] = [
        {"isHandwritten": True, "confidence": 1, "spans": [{"offset": 2, "length": 4}]}
    ]
    words = parse_di(raw, analysis.pages[0].geometry)
    assert words[0].text == "café" and words[0].handwritten
    raw["styles"][0]["spans"][0]["length"] = 1
    assert parse_di(raw, analysis.pages[0].geometry)[0].style_confidence == 0
    raw["stringIndexType"] = "utf16CodeUnit"
    with pytest.raises(ValueError, match="unicodeCodePoint"):
        parse_di(raw, analysis.pages[0].geometry)


def test_table_and_formula_context_never_becomes_calculated_text(case: tuple) -> None:
    _, evidence_path, _, _, analysis, _ = case
    raw = read_json(evidence_path, 1_000_000)["pages"][0]["di"]
    polygon = raw["pages"][0]["words"][1]["polygon"]
    raw["tables"] = [
        {
            "cells": [
                {
                    "rowIndex": 2,
                    "columnIndex": 3,
                    "content": "literal cell",
                    "boundingRegions": [{"pageNumber": 1, "polygon": polygon}],
                }
            ]
        }
    ]
    raw["pages"][0]["formulas"] = [{"polygon": polygon, "value": "a+b", "kind": "inline"}]
    annotations = analysis.pages[0].annotations
    original = annotations[0].text
    attach_structure(annotations, raw, analysis.pages[0].geometry)
    assert annotations[0].table_context[0]["row"] == 2
    assert annotations[0].table_context[0]["column"] == 3
    assert annotations[0].formula_context[0]["value"] == "a+b"
    assert annotations[0].text == original
    assert annotations[0].kind == "formula"


@pytest.mark.parametrize("status", ["refused", "truncated"])
def test_refused_truncated_no_successful_cache(case: tuple, status: str) -> None:
    _, evidence_path, _, settings, analysis, _ = case
    vision = VisionResult.model_validate(read_json(evidence_path, 1_000_000)["pages"][0]["vision"])
    vision.status = status
    with pytest.raises(ValueError, match=status):
        reconcile(analysis.pages[0].words, vision, analysis.pages[0].geometry, settings)


def test_unknown_schema_and_malformed_geometry_rejected() -> None:
    with pytest.raises(ValidationError):
        Box(x0=1, y0=0, x1=0, y1=2)
    with pytest.raises(ValidationError):
        Box(x0=float("nan"), y0=0, x1=3, y1=2)
    with pytest.raises(ValidationError):
        Decision(annotation_id="a", binding="b", text="c", state="maybe")
    with pytest.raises(ValidationError):
        Decision(annotation_id="a", binding="b", text="c", cleanup_reviewed="false")


def test_cache_no_repeat_render_and_evidence_invalidation(case: tuple, monkeypatch) -> None:
    source, evidence_path, output, settings, analysis, _ = case
    import handwritten_docs.pipeline as pipeline

    monkeypatch.setattr(
        pipeline, "render", lambda *args: pytest.fail("cached page rendered again")
    )
    cached = analyze(source, evidence_path, output, "1", settings)
    assert cached == analysis
    evidence = read_json(evidence_path, 1_000_000)
    evidence["provenance"]["changed"] = True
    write_json(evidence_path, evidence)
    with pytest.raises(pytest.fail.Exception, match="rendered again"):
        analyze(source, evidence_path, output, "1", settings)


def test_interrupted_analysis_resumes_page_checkpoint(case: tuple, monkeypatch) -> None:
    source, evidence, output, settings, analysis, _ = case
    import handwritten_docs.pipeline as pipeline

    cache = output / "cache" / f"{analysis.run_id}.json"
    cache.unlink()
    monkeypatch.setattr(pipeline, "render", lambda *args: pytest.fail("checkpoint rendered again"))
    assert analyze(source, evidence, output, "1", settings) == analysis


def test_corrupt_checkpoint_fails_explicitly(case: tuple) -> None:
    source, evidence, output, settings, analysis, _ = case
    cache = output / "cache" / f"{analysis.run_id}.json"
    stored = read_json(cache, settings.max_json_bytes)
    stored["analysis"]["pages"][0]["protection_complete"] = False
    write_json(cache, stored)
    with pytest.raises(ValueError, match="checksum"):
        analyze(source, evidence, output, "1", settings)


def test_html_escapes_document_content_and_uses_local_assets(case: tuple) -> None:
    source, _, output, settings, analysis, review = case
    review.decisions[0].text = '<script>alert("document")</script>'
    review = create_review(source, analysis, output, settings, review)
    path = write_report(source, analysis, review, output, settings)
    html = path.read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(&quot;document&quot;)&lt;/script&gt;" in html
    assert '<script>alert("document")</script>' not in html
    assert "https://" not in html
    assert "--cp-bg" in html
    assert list((output / "assets").glob("*.png"))


@pytest.mark.parametrize("spec", ["0", "3", "2-1", "1-100", "", "1-2-3"])
def test_invalid_page_selection(spec: str) -> None:
    with pytest.raises(ValueError):
        select_pages(spec, 2, 20)


def test_limits_corrupt_and_encrypted_input(tmp_path: Path) -> None:
    source, _ = generate(tmp_path)
    with pytest.raises(ValueError, match="byte"):
        open_pdf(source, Settings(max_input_bytes=1))
    geom = geometry(PdfReader(source), 1)
    with pytest.raises(ValueError, match="pixel"):
        render(source, geom, Settings(max_pixels=1))
    encrypted = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.append(PdfReader(source))
    writer.encrypt("synthetic-test")
    with encrypted.open("wb") as stream:
        writer.write(stream)
    with pytest.raises(ValueError, match="encrypted"):
        open_pdf(encrypted, Settings())
    assert main(["inspect", str(source), "--pages", "99", "--output", str(tmp_path / "out")]) == 1


def test_network_authorization_exact_source_page_endpoint() -> None:
    grant = Authorization(
        source_sha256="a" * 64,
        endpoint="https://example.invalid",
        approved_pages=[1],
        target_reference="synthetic",
        data_permission_reference="synthetic",
    )
    grant.check("https://example.invalid", "a" * 64, 1)
    for endpoint, source, page in [
        ("https://another.invalid", "a" * 64, 1),
        ("https://example.invalid", "b" * 64, 1),
        ("https://example.invalid", "a" * 64, 2),
    ]:
        with pytest.raises(PermissionError):
            grant.check(endpoint, source, page)


def test_bounded_visible_retry_and_permanent_failure(caplog) -> None:
    attempts = []

    async def action() -> str:
        attempts.append(1)
        if len(attempts) < 3:
            raise ServiceRequestError("synthetic")
        return "done"

    async def sleep(_: float) -> None:
        return None

    assert asyncio.run(retry(action, sleep=sleep)) == "done"
    assert len(attempts) == 3
    assert "retry" in caplog.text

    async def permanent() -> None:
        error = HttpResponseError("synthetic")
        error.status_code = 403
        raise error

    with pytest.raises(HttpResponseError):
        asyncio.run(retry(permanent, sleep=sleep))


def test_cli_end_to_end_and_rejected_review(case: tuple) -> None:
    source, evidence, output, _, _, review = case
    assert main(["inspect", str(source), "--pages", "1", "--output", str(output)]) == 0
    assert (
        main(
            [
                "analyze",
                str(source),
                "--pages",
                "1",
                "--evidence",
                str(evidence),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    review.decisions[0].state = "rejected"
    write_json(output / "review.json", review)
    assert (
        main(
            [
                "review-report",
                str(source),
                "--analysis",
                str(output / "analysis.json"),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "export",
                str(source),
                "--analysis",
                str(output / "analysis.json"),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    manifest = read_json(output / "manifest.json", 1_000_000)
    assert manifest["counts"]["preserved"] == 1
    assert (output / "report.html").exists()


def test_signature_form_inputs_and_source_output_collision_rejected(tmp_path: Path) -> None:
    source, _ = generate(tmp_path / "input")
    reader = PdfReader(source)
    writer = PdfWriter()
    writer.append(reader)
    writer.root_object[NameObject("/Perms")] = DictionaryObject()
    signed = tmp_path / "signed.pdf"
    with signed.open("wb") as stream:
        writer.write(stream)
    with pytest.raises(ValueError, match="signed"):
        open_pdf(signed, Settings())
    assert (
        main(
            [
                "inspect",
                str(source),
                "--pages",
                "1",
                "--output",
                str(source.parent),
            ]
        )
        == 1
    )
