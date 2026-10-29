"""The command line: ``python -m handwritten_docs <command> ...``.

Results go to standard output; diagnostics go to the log on standard error. Exit codes:
0 done, 1 the input file cannot be used, 2 bad arguments or settings.
"""

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import TextIO

from handwritten_docs.config import ConfigError, load_settings
from handwritten_docs.inspection import PdfInfo, PdfInspectionError, inspect_pdf
from handwritten_docs.logging_setup import configure_logging

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_INPUT_ERROR = 1
EXIT_USAGE_ERROR = 2
BYTES_PER_KB = 1024
JSON_INDENT = 2


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    """Run one command and return its exit code."""
    out = sys.stdout if out is None else out
    args = _parser().parse_args(argv)

    try:
        settings = load_settings()
    except ConfigError as exc:
        configure_logging(logging.ERROR)
        logger.error("invalid settings: %s", exc)
        return EXIT_USAGE_ERROR
    configure_logging(settings.log_level_number)

    try:
        info = inspect_pdf(args.pdf, settings)
    except PdfInspectionError as exc:
        logger.error("cannot inspect: %s", exc)
        return EXIT_INPUT_ERROR

    out.write(_as_json(info) if args.json else _as_table(info))
    return EXIT_OK


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m handwritten_docs",
        description="Find, review and safely replace handwritten content in PDFs.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    inspect = commands.add_parser(
        "inspect",
        help="report the pages, text layer and images of a PDF",
        description="Report each page's size, rotation, text layer and images. "
        "The report never includes the document's text.",
    )
    inspect.add_argument("pdf", type=Path, help="the PDF to inspect")
    inspect.add_argument("--json", action="store_true", help="write the report as JSON")
    return parser


def _as_json(info: PdfInfo) -> str:
    report = asdict(info)
    report["page_count"] = info.page_count
    for page, page_report in zip(info.pages, report["pages"], strict=True):
        page_report["has_text_layer"] = page.has_text_layer
    return json.dumps(report, indent=JSON_INDENT) + "\n"


def _as_table(info: PdfInfo) -> str:
    size_kb = info.file_bytes / BYTES_PER_KB
    lines = [
        f"{info.file_name}: {info.page_count} page(s), PDF {info.pdf_version}, {size_kb:.1f} KB",
        f"{'page':>4}  {'size (pt)':<17}  {'rotation':>8}  {'text layer':<12}  images",
    ]
    for page in info.pages:
        size = f"{page.width_pt:g} x {page.height_pt:g}"
        text = f"yes ({page.text_chars})" if page.has_text_layer else "no"
        images = ", ".join(f"{image.width_px}x{image.height_px}" for image in page.images)
        lines.append(
            f"{page.number:>4}  {size:<17}  {page.rotation:>8}  {text:<12}  "
            f"{len(page.images)}{f' ({images})' if images else ''}"
        )
    return "\n".join(lines) + "\n"
