from pathlib import Path

import pytest
import synthetic_pdfs
from reportlab.lib.pagesizes import letter

from handwritten_docs.config import Settings
from handwritten_docs.inspection import (
    DamagedPdfError,
    EncryptedPdfError,
    PdfNotFoundError,
    PdfTooLargeError,
    inspect_pdf,
)

LETTER_WIDTH, LETTER_HEIGHT = letter


def test_printed_page_has_a_text_layer_and_no_image(printed_pdf: Path, settings: Settings) -> None:
    info = inspect_pdf(printed_pdf, settings)

    assert info.file_name == "printed.pdf"
    assert info.file_bytes == printed_pdf.stat().st_size
    assert info.page_count == 1
    page = info.pages[0]
    assert (page.number, page.width_pt, page.height_pt, page.rotation) == (
        1,
        LETTER_WIDTH,
        LETTER_HEIGHT,
        0,
    )
    assert page.has_text_layer
    assert page.text_chars == synthetic_pdfs.printed_text_chars()
    assert page.images == ()


def test_scanned_page_is_one_image_without_text(scanned_pdf: Path, settings: Settings) -> None:
    page = inspect_pdf(scanned_pdf, settings).pages[0]

    assert not page.has_text_layer
    assert [(image.width_px, image.height_px) for image in page.images] == [
        synthetic_pdfs.SCAN_SIZE_PX
    ]


def test_mixed_document_reports_each_page(mixed_pdf: Path, settings: Settings) -> None:
    info = inspect_pdf(mixed_pdf, settings)

    assert info.page_count == 3
    first, scan, rotated = info.pages
    assert first.has_text_layer
    assert [(i.width_px, i.height_px) for i in first.images] == [synthetic_pdfs.NOTE_SIZE_PX]
    assert not scan.has_text_layer
    assert len(scan.images) == 1
    assert rotated.rotation == synthetic_pdfs.ROTATED_DEGREES
    assert rotated.has_text_layer
    assert [page.number for page in info.pages] == [1, 2, 3]


def test_image_inside_a_form_xobject_is_found(form_image_pdf: Path, settings: Settings) -> None:
    page = inspect_pdf(form_image_pdf, settings).pages[0]

    assert [(i.width_px, i.height_px) for i in page.images] == [synthetic_pdfs.NOTE_SIZE_PX]


def test_report_never_contains_document_text(printed_pdf: Path, settings: Settings) -> None:
    info = inspect_pdf(printed_pdf, settings)

    assert synthetic_pdfs.SECRET_PHRASE not in repr(info)


def test_encrypted_pdf_is_refused(encrypted_pdf: Path, settings: Settings) -> None:
    with pytest.raises(EncryptedPdfError, match="encrypted"):
        inspect_pdf(encrypted_pdf, settings)


@pytest.mark.parametrize("fixture", ["not_a_pdf", "truncated_pdf"])
def test_damaged_file_is_refused(
    fixture: str, settings: Settings, request: pytest.FixtureRequest
) -> None:
    path: Path = request.getfixturevalue(fixture)

    with pytest.raises(DamagedPdfError, match="not a readable PDF"):
        inspect_pdf(path, settings)


def test_missing_file_is_refused(tmp_path: Path, settings: Settings) -> None:
    with pytest.raises(PdfNotFoundError):
        inspect_pdf(tmp_path / "missing.pdf", settings)


def test_folder_is_refused(tmp_path: Path, settings: Settings) -> None:
    with pytest.raises(PdfNotFoundError):
        inspect_pdf(tmp_path, settings)


def test_file_over_the_size_limit_is_not_read(printed_pdf: Path) -> None:
    limit = printed_pdf.stat().st_size - 1

    with pytest.raises(PdfTooLargeError, match=str(limit)):
        inspect_pdf(printed_pdf, Settings(max_pdf_bytes=limit))


def test_file_at_the_size_limit_is_read(printed_pdf: Path) -> None:
    info = inspect_pdf(printed_pdf, Settings(max_pdf_bytes=printed_pdf.stat().st_size))

    assert info.page_count == 1
