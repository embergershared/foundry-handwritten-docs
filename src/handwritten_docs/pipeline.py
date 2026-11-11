"""Offline evidence ingestion, deterministic checkpoints, and source-bound review."""

from importlib.metadata import version
from pathlib import Path

from .config import Settings
from .extraction import attach_structure, parse_di, reconcile
from .models import Analysis, Box, Decision, PageAnalysis, Review, VisionResult
from .pdf import geometry, open_pdf, render
from .safety import font, mask_region
from .storage import digest, file_hash, read_json, select_pages, write_json


def runtime_identity() -> dict[str, str]:
    return {
        name: version(name)
        for name in ("pypdfium2", "pypdf", "reportlab", "Pillow", "numpy", "pydantic")
    } | {"pipeline": "0.1.0"}


def protect_output(source: Path, output: Path) -> None:
    if source.resolve().is_relative_to(output.resolve()):
        raise ValueError("source must be outside the output directory")


def analyze(
    source: Path,
    evidence_path: Path,
    output: Path,
    pages: str,
    settings: Settings,
) -> Analysis:
    """Import local service evidence or synthetic doubles; never send network requests."""
    protect_output(source, output)
    reader = open_pdf(source, settings)
    selected = select_pages(pages, len(reader.pages), settings.max_pages)
    source_hash = file_hash(source)
    evidence = read_json(evidence_path, settings.max_json_bytes)
    if set(evidence) != {"schema_version", "source_sha256", "pages", "provenance"}:
        raise ValueError("unknown or missing evidence fields")
    if evidence["schema_version"] != "1" or evidence["source_sha256"] != source_hash:
        raise ValueError("evidence belongs to another source or schema")
    if len(evidence["pages"]) != len(selected):
        raise ValueError("evidence must contain exactly the selected pages")
    mapped = {entry["source_page"]: entry for entry in evidence["pages"]}
    if set(mapped) != set(selected) or len(mapped) != len(evidence["pages"]):
        raise ValueError("duplicate or mismatched evidence source pages")
    config_hash = digest([settings, font(settings)[1], runtime_identity()])
    key = digest([source_hash, digest(evidence), config_hash, selected, "pipeline-v1"])
    cache = output / "cache" / f"{key}.json"
    if cache.exists():
        stored = read_json(cache, settings.max_json_bytes)
        cached = Analysis.model_validate(stored["analysis"])
        if digest(cached) != stored["sha256"]:
            raise ValueError("analysis cache checksum mismatch")
        if cached.run_id != key:
            raise ValueError("corrupt analysis cache")
        return cached
    result_pages = []
    for number in selected:
        checkpoint = output / "checkpoints" / f"{key}-{number}.json"
        raster_path = output / "pages" / f"{number}.png"
        if checkpoint.exists():
            saved = read_json(checkpoint, settings.max_json_bytes)
            saved_page = PageAnalysis.model_validate(saved["page"])
            if digest(saved_page) != saved["sha256"]:
                raise ValueError("page checkpoint checksum mismatch")
            if not raster_path.exists() or file_hash(raster_path) != saved_page.raster_sha256:
                raise ValueError(
                    "checkpoint raster missing or changed; use a new output directory"
                )
            result_pages.append(saved_page)
            continue
        entry = mapped[number]
        allowed = {"source_page", "di", "vision", "local_review"}
        if set(entry) != allowed:
            raise ValueError("unknown or missing page evidence fields")
        geom = geometry(reader, number)
        words = parse_di(entry["di"], geom)
        vision = VisionResult.model_validate(entry["vision"])
        if len(words) > settings.max_words_per_page:
            raise ValueError("page word limit exceeded")
        if len(vision.proposals) > settings.max_regions_per_page:
            raise ValueError("page proposal limit exceeded")
        if vision.protection_complete:
            raise ValueError("vision cannot attest local protection inspection")
        annotations = reconcile(words, vision, geom, settings)
        attach_structure(annotations, entry["di"], geom)
        review = entry["local_review"]
        if set(review) != {"reviewer", "protection_complete", "ocr_complete", "protected"}:
            raise ValueError("invalid local inspection attestation")
        if (
            type(review["protection_complete"]) is not bool
            or type(review["ocr_complete"]) is not bool
        ):
            raise ValueError("inspection attestations require JSON booleans")
        if (review["protection_complete"] or review["ocr_complete"]) and not review["reviewer"]:
            raise ValueError("local inspection requires an identified reviewer")
        protected = [Box.model_validate(b) for b in review["protected"]] + vision.protected
        for b in protected:
            if not Box(x0=0, y0=0, x1=geom.width, y1=geom.height).contains(b):
                raise ValueError("protected region outside page")
        image = render(source, geom, settings)
        raster_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(raster_path)
        result_pages.append(
            PageAnalysis(
                geometry=geom,
                raster_sha256=file_hash(raster_path),
                words=words,
                annotations=annotations,
                protected=protected,
                protection_complete=review["protection_complete"],
                ocr_complete=review["ocr_complete"],
                tables=entry["di"].get("tables", []),
                formulas=entry["di"]["pages"][0].get("formulas", []),
            )
        )
        image.close()
        write_json(checkpoint, {"sha256": digest(result_pages[-1]), "page": result_pages[-1]})
    analysis = Analysis(
        source_sha256=source_hash,
        config_sha256=config_hash,
        evidence_sha256=digest(evidence),
        run_id=key,
        provenance={"evidence": evidence["provenance"], "runtime": runtime_identity()},
        pages=result_pages,
    )
    write_json(cache, {"sha256": digest(analysis), "analysis": analysis})
    write_json(output / "analysis.json", analysis)
    return analysis


def verify_analysis(source: Path, analysis: Analysis, settings: Settings) -> None:
    if file_hash(source) != analysis.source_sha256:
        raise ValueError("source changed since analysis")
    if digest([settings, font(settings)[1], runtime_identity()]) != analysis.config_sha256:
        raise ValueError("configuration or font changed since analysis")
    reader = open_pdf(source, settings)
    for page in analysis.pages:
        if geometry(reader, page.geometry.page) != page.geometry:
            raise ValueError("source page geometry changed")


def binding(analysis: Analysis, annotation: dict, mask_hash: str, text: str) -> str:
    return digest([digest(analysis), annotation, mask_hash, text])


def create_review(
    source: Path,
    analysis: Analysis,
    output: Path,
    settings: Settings,
    previous: Review | None = None,
) -> Review:
    """Refresh bindings for edited text; every refresh resets decisions to pending."""
    protect_output(source, output)
    verify_analysis(source, analysis, settings)
    previous_by_id = {d.annotation_id: d for d in previous.decisions} if previous else {}
    decisions = []
    for page in analysis.pages:
        image = render(source, page.geometry, settings)
        for annotation in page.annotations:
            mask = mask_region(image, page, annotation, settings)
            old = previous_by_id.get(annotation.id)
            text = old.text if old else annotation.text
            decisions.append(
                Decision(
                    annotation_id=annotation.id,
                    text=text,
                    binding=binding(analysis, annotation.model_dump(), mask.sha256, text),
                )
            )
        image.close()
    review = Review(analysis_sha256=digest(analysis), decisions=decisions)
    write_json(output / "review.json", review)
    return review
