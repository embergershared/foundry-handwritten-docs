"""Local-only command line stages. Network adapters are intentionally not CLI switches."""

import argparse
import json
import logging
from pathlib import Path

from pydantic import ValidationError
from pypdf.errors import PdfReadError

from .config import load_settings
from .export import export_pdf
from .models import Analysis, Review
from .pdf import geometry, open_pdf
from .pipeline import analyze, create_review, protect_output
from .report import write_report
from .storage import file_hash, read_json, select_pages, write_json

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    stages = parser.add_subparsers(dest="stage", required=True)
    for name in ("inspect", "analyze", "review-report", "export"):
        command = stages.add_parser(name)
        command.add_argument("source", type=Path)
        command.add_argument("--output", type=Path, required=True)
        if name in ("inspect", "analyze"):
            command.add_argument("--pages", required=True)
        if name == "analyze":
            command.add_argument("--evidence", type=Path, required=True)
        if name in ("review-report", "export"):
            command.add_argument("--analysis", type=Path, required=True)
            command.add_argument("--review", type=Path)
        if name == "review-report":
            command.add_argument("--refresh-bindings", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings(args.config)
        protect_output(args.source, args.output)
        if args.stage == "inspect":
            reader = open_pdf(args.source, settings)
            pages = select_pages(args.pages, len(reader.pages), settings.max_pages)
            write_json(
                args.output / "inventory.json",
                {
                    "source_sha256": file_hash(args.source),
                    "page_count": len(reader.pages),
                    "selected": [geometry(reader, p).model_dump() for p in pages],
                    "cloud_processing": False,
                },
            )
        elif args.stage == "analyze":
            result = analyze(args.source, args.evidence, args.output, args.pages, settings)
            write_json(args.output / "analysis.json", result)
        else:
            result = Analysis.model_validate(read_json(args.analysis, settings.max_json_bytes))
            review_path = args.review or args.output / "review.json"
            previous = (
                Review.model_validate(read_json(review_path, settings.max_json_bytes))
                if review_path.exists()
                else None
            )
            if args.stage == "export":
                if previous is None:
                    raise ValueError(
                        "export requires review.json, even when all decisions are pending"
                    )
                export_pdf(args.source, result, previous, args.output, settings)
                write_report(
                    args.source,
                    result,
                    previous,
                    args.output,
                    settings,
                    exported=args.output / "replacement.pdf",
                )
            else:
                review = (
                    create_review(args.source, result, args.output, settings, previous)
                    if previous is None or args.refresh_bindings
                    else previous
                )
                write_report(args.source, result, review, args.output, settings)
        LOGGER.info("Local %s stage completed", args.stage)
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        ValidationError,
        PdfReadError,
        json.JSONDecodeError,
    ) as error:
        # Do not log service/document strings, local filenames, or identifiers.
        LOGGER.error(
            "Stage failed (%s); inspect inputs and configured limits", type(error).__name__
        )
        return 1
