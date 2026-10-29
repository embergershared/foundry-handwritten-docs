"""Report what a PDF contains: its pages, their size and rotation, text layer and images.

The report holds counts and sizes only, never the document's text, so it is safe to log or
share. Images are found through each page's XObject resources, including those nested in form
XObjects; inline images (``BI`` ... ``EI`` in a content stream) are not counted.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from pypdf import PageObject, PdfReader
from pypdf.errors import PyPdfError
from pypdf.generic import DictionaryObject, IndirectObject

from handwritten_docs.config import Settings

logger = logging.getLogger(__name__)

PDF_HEADER_PREFIX = "%PDF-"
FULL_TURN_DEGREES = 360
POINT_DECIMALS = 2
MAX_XOBJECT_DEPTH = 8

# What pypdf raises, besides its own errors, on a file it cannot parse.
_PARSE_ERRORS = (PyPdfError, ValueError, KeyError, TypeError, IndexError, AttributeError)


class PdfInspectionError(Exception):
    """The file cannot be inspected; the message says why, without the document's content."""


class PdfNotFoundError(PdfInspectionError):
    """The path does not name a file."""


class PdfTooLargeError(PdfInspectionError):
    """The file is larger than the configured limit."""


class EncryptedPdfError(PdfInspectionError):
    """The PDF is encrypted; it is not opened."""


class DamagedPdfError(PdfInspectionError):
    """The file is not a PDF, or its structure cannot be read."""


@dataclass(frozen=True)
class ImageInfo:
    """One image XObject drawn on a page."""

    name: str
    width_px: int
    height_px: int


@dataclass(frozen=True)
class PageInfo:
    """One page: its visible box in points, rotation, text layer and images."""

    number: int
    width_pt: float
    height_pt: float
    rotation: int
    text_chars: int
    images: tuple[ImageInfo, ...]

    @property
    def has_text_layer(self) -> bool:
        """Whether the page has extractable text (printed text, or an OCR layer)."""
        return self.text_chars > 0


@dataclass(frozen=True)
class PdfInfo:
    """The whole file."""

    file_name: str
    file_bytes: int
    pdf_version: str
    pages: tuple[PageInfo, ...]

    @property
    def page_count(self) -> int:
        """The number of pages."""
        return len(self.pages)


def inspect_pdf(path: Path, settings: Settings) -> PdfInfo:
    """Read ``path`` and report its pages.

    Raises:
        PdfNotFoundError: ``path`` is not a file.
        PdfTooLargeError: the file is over ``settings.max_pdf_bytes``.
        EncryptedPdfError: the PDF is encrypted.
        DamagedPdfError: the file is not a readable PDF.
    """
    if not path.is_file():
        raise PdfNotFoundError(f"{path} is not a file.")
    file_bytes = path.stat().st_size
    if file_bytes > settings.max_pdf_bytes:
        raise PdfTooLargeError(
            f"{path.name} is {file_bytes} bytes, over the {settings.max_pdf_bytes}-byte limit."
        )

    with path.open("rb") as stream:
        try:
            reader = PdfReader(stream)
            encrypted = reader.is_encrypted
        except _PARSE_ERRORS as exc:
            raise DamagedPdfError(f"{path.name} is not a readable PDF: {exc}") from exc
        if encrypted:
            raise EncryptedPdfError(f"{path.name} is encrypted; it is not opened.")
        try:
            version = reader.pdf_header.removeprefix(PDF_HEADER_PREFIX)
            pages = tuple(
                _page_info(number, page) for number, page in enumerate(reader.pages, start=1)
            )
        except _PARSE_ERRORS as exc:
            raise DamagedPdfError(f"{path.name} has a page that cannot be read: {exc}") from exc

    logger.debug("inspected file=%s pages=%d bytes=%d", path.name, len(pages), file_bytes)
    return PdfInfo(file_name=path.name, file_bytes=file_bytes, pdf_version=version, pages=pages)


def _page_info(number: int, page: PageObject) -> PageInfo:
    box = page.cropbox
    text = page.extract_text() or ""
    return PageInfo(
        number=number,
        width_pt=round(float(box.width), POINT_DECIMALS),
        height_pt=round(float(box.height), POINT_DECIMALS),
        rotation=page.rotation % FULL_TURN_DEGREES,
        text_chars=sum(1 for char in text if not char.isspace()),
        images=tuple(_images_in(page.get("/Resources"), depth=0, seen=set())),
    )


def _images_in(resources: object, depth: int, seen: set[int]) -> list[ImageInfo]:
    """The image XObjects of ``resources``, then those inside its form XObjects."""
    resources = _resolve(resources)
    if not isinstance(resources, DictionaryObject) or depth > MAX_XOBJECT_DEPTH:
        return []
    xobjects = _resolve(resources.get("/XObject"))
    if not isinstance(xobjects, DictionaryObject):
        return []

    images: list[ImageInfo] = []
    for name, reference in xobjects.items():
        if isinstance(reference, IndirectObject):
            # A form can be drawn by several pages or by itself: visit each object once.
            if reference.idnum in seen:
                continue
            seen.add(reference.idnum)
        xobject = _resolve(reference)
        if not isinstance(xobject, DictionaryObject):
            continue
        subtype = xobject.get("/Subtype")
        if subtype == "/Image":
            images.append(
                ImageInfo(
                    name=str(name),
                    width_px=int(xobject.get("/Width", 0)),
                    height_px=int(xobject.get("/Height", 0)),
                )
            )
        elif subtype == "/Form":
            images.extend(_images_in(xobject.get("/Resources"), depth + 1, seen))
    return images


def _resolve(value: object) -> object:
    return value.get_object() if isinstance(value, IndirectObject) else value
