"""Escaped local HTML review, with no external assets or document-authored markup."""

from html import escape
from pathlib import Path

from PIL import ImageDraw, ImageFont

from .config import Settings
from .export import eligibility
from .models import Analysis, Review
from .pdf import render
from .pipeline import binding, protect_output, verify_analysis
from .safety import clean, fit, font, mask_region
from .storage import digest

THEME_SCRIPT = """(() => {
const param = new URLSearchParams(window.location.search).get("scoutTheme");
const theme =
  param || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
document.documentElement.setAttribute("data-theme", theme);
})();"""
CSS = """
:root {
  color-scheme: light;
  --cp-bg: #f7f4ef;
  --cp-bg-elevated: #fcfbf8;
  --cp-surface: #ffffff;
  --cp-surface-soft: #f5f5f5;
  --cp-border: #dedede;
  --cp-border-strong: #919191;
  --cp-text: #242424;
  --cp-text-muted: #5c5c5c;
  --cp-text-soft: #6f6f6f;
  --cp-accent: #b11f4b;
  --cp-accent-hover: #9a1a41;
  --cp-accent-soft: rgba(177, 31, 75, 0.08);
  --cp-accent-fg: #ffffff;
  --cp-success: #16a34a;
  --cp-danger: #dc2626;
  --cp-warning: #f59e0b;
  --cp-link: #0078d4;
  --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.12);
  --cp-overlay: rgba(255, 255, 255, 0.8);
  --cp-panel: rgba(255, 255, 255, 0.86);
  --cp-panel-strong: rgba(255, 255, 255, 0.96);
  --cp-sheen: rgba(255, 255, 255, 0.55);
  --cp-highlight: rgba(177, 31, 75, 0.12);
}
html[data-theme="dark"] {
  color-scheme: dark;
  --cp-bg: #3d3b3a;
  --cp-bg-elevated: #343231;
  --cp-surface: #292929;
  --cp-surface-soft: #2e2e2e;
  --cp-border: #474747;
  --cp-border-strong: #5f5f5f;
  --cp-text: #dedede;
  --cp-text-muted: #919191;
  --cp-text-soft: #b0b0b0;
  --cp-accent: #fd8ea1;
  --cp-accent-hover: #fb7b91;
  --cp-accent-soft: rgba(253, 142, 161, 0.14);
  --cp-accent-fg: #1a1a1a;
  --cp-success: #4ade80;
  --cp-danger: #f87171;
  --cp-warning: #fbbf24;
  --cp-link: #4da6ff;
  --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.32);
  --cp-overlay: rgba(41, 41, 41, 0.88);
  --cp-panel: rgba(41, 41, 41, 0.72);
  --cp-panel-strong: rgba(41, 41, 41, 0.96);
  --cp-sheen: rgba(255, 255, 255, 0.04);
  --cp-highlight: rgba(253, 142, 161, 0.12);
}
body { background:var(--cp-bg); color:var(--cp-text);
font-family:"Segoe UI",Aptos,Calibri,-apple-system,BlinkMacSystemFont,sans-serif;
max-width:1100px; margin:32px auto; padding:16px; }
h1 { color:var(--cp-accent); }
article { background:var(--cp-surface); border:1px solid var(--cp-border);
border-radius:16px; margin:24px 0; padding:24px; }
.pair { display:flex; flex-wrap:wrap; gap:24px; }
figure { margin:0; flex:1; min-width:240px; }
img { max-width:100%; border:1px solid var(--cp-border); }
code { font-family:Consolas,"Courier New",Courier,monospace; overflow-wrap:anywhere; }
small,figcaption { color:var(--cp-text-muted); }
a { color:var(--cp-link); }
"""


def write_report(
    source: Path,
    analysis: Analysis,
    review: Review,
    output: Path,
    settings: Settings,
    exported: Path | None = None,
) -> Path:
    protect_output(source, output)
    verify_analysis(source, analysis, settings)
    if review.analysis_sha256 != digest(analysis):
        raise ValueError("review belongs to another analysis")
    output.mkdir(parents=True, exist_ok=True)
    assets = output / "assets"
    assets.mkdir(exist_ok=True)
    decisions = {d.annotation_id: d for d in review.decisions}
    if set(decisions) != {a.id for p in analysis.pages for a in p.annotations}:
        raise ValueError("report decisions do not exactly match analysis")
    cards = []
    for page in analysis.pages:
        image = render(source, page.geometry, settings)
        actual = render(exported, page.geometry, settings) if exported else None
        overview = image.copy()
        overlay = ImageDraw.Draw(overview)
        for annotation in page.annotations:
            overlay.rectangle(
                page.geometry.pixels(annotation.box, image.size),
                outline=(177, 31, 75),
                width=2,
            )
        overview.thumbnail((900, 900))
        overview_name = f"page-{page.geometry.page}.png"
        overview.save(assets / overview_name)
        overview.close()
        cards.append(
            f"<article><h2>Page {page.geometry.page} context</h2>"
            f'<img src="assets/{overview_name}" alt="Page overview with candidate bounds">'
            "<p>Outlined bounds are proposals, not erasure rectangles.</p></article>"
        )
        for annotation in page.annotations:
            decision = decisions[annotation.id]
            mask = mask_region(image, page, annotation, settings)
            if decision.binding != binding(
                analysis,
                annotation.model_dump(),
                mask.sha256,
                decision.text,
            ):
                raise ValueError("stale review binding; refresh edits before rendering report")
            status, reasons = eligibility(annotation, decision, mask, settings)
            if status == "replaced" and not page.ocr_complete:
                status, reasons = "blocked", ["complete retained OCR not locally attested"]
            after = actual.copy() if actual else image.copy()
            if not actual and status == "replaced":
                after = clean(after, mask)
                _, size = fit(decision.text, annotation, settings)
                name, _ = font(settings)
                from reportlab.pdfbase import pdfmetrics

                font_path = pdfmetrics.getFont(name).face.filename
                scale = image.width / page.geometry.width
                draw = ImageDraw.Draw(after)
                draw.text(
                    (annotation.box.x0 * scale, annotation.box.y0 * scale),
                    decision.text,
                    font=ImageFont.truetype(font_path, round(size * scale)),
                    fill=(0, 0, 0),
                )
            crop = page.geometry.pixels(annotation.box, image.size)
            before_name, after_name = f"{annotation.id}-before.png", f"{annotation.id}-after.png"
            image.crop(crop).save(assets / before_name)
            after.crop(crop).save(assets / after_name)
            cards.append(
                f"<article><h2>Page {page.geometry.page}: {escape(status)}</h2>"
                f"<p><code>{escape(annotation.id)}</code></p>"
                f"<p>Literal proposal: <strong>{escape(decision.text)}</strong></p>"
                f"<p>DI: {escape(annotation.ocr_text)}</p>"
                f"<p>Nearby context: {escape(annotation.context)}</p>"
                f"<p>{escape('; '.join(reasons + annotation.reasons))}</p>"
                f'<div class="pair"><figure><img src="assets/{before_name}" alt="Original crop">'
                f"<figcaption>Before</figcaption></figure>"
                f'<figure><img src="assets/{after_name}" alt="Replacement or preserved crop">'
                f"<figcaption>{'Exported PDF' if actual else 'Preview'} / after</figcaption>"
                f"</figure></div></article>"
            )
            after.close()
        image.close()
        if actual:
            actual.close()
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'\">"
        f"<script>{THEME_SCRIPT}</script><style>{CSS}</style>"
        "<title>Local handwriting review</title></head><body>"
        "<h1>Local handwriting review</h1>"
        "<p>Derived transcription, not calculation validation or an authenticated original. "
        "Unsafe and unsupported regions remain unchanged. "
        "No cloud requests were made by this CLI.</p>"
        "<p>Edit review.json locally. Changed text requires refreshed bindings "
        "and fresh approval. "
        "Approval never overrides failed cleanup or typography gates.</p>"
        f"<small>Source SHA256: <code>{escape(analysis.source_sha256)}</code></small>"
        + "".join(cards)
        + "</body></html>"
    )
    path = output / "report.html"
    path.write_text(html, encoding="utf-8")
    return path
