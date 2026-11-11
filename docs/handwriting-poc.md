# Local handwriting replacement proof of concept

The local CLI reads a scanned PDF, reconciles Document Intelligence (DI) handwriting
evidence with literal vision proposals, produces an editable review and a local HTML
report, and exports a separate derived PDF. It does not interpret engineering content,
repair arithmetic, execute document instructions, or authenticate the result.

**Current status:** the complete local/offline path is implemented and tested with
synthetic PDFs. The DI and Foundry adapters have network-free contract tests, not live
service validation. No real handwriting accuracy, protected-content detection accuracy,
model selection, or automatic threshold calibration has been established.

## Install and run offline

Python 3.13 is required. Install only hash-locked dependencies from the approved feed.
If the feed is unavailable, stop; do not silently substitute PyPI. The wheel build uses
the locked setuptools/wheel packages rather than an unrestricted build environment.

**PowerShell (workstation), repository root:**

```powershell
Set-Location <repository-root>
py -3.13 -m venv .venv
$env:PIP_INDEX_URL = 'https://packagefeedproxy.microsoft.io/pypi/simple/'
.venv\Scripts\python -m pip install --require-hashes -r requirements-dev.lock
.venv\Scripts\python -m pip install --no-deps --no-build-isolation -e .
.venv\Scripts\python -m handwritten_docs.demo --output artifacts\synthetic-input
.venv\Scripts\python -m handwritten_docs inspect artifacts\synthetic-input\synthetic.pdf --pages 1 --output artifacts\synthetic-run
.venv\Scripts\python -m handwritten_docs analyze artifacts\synthetic-input\synthetic.pdf --pages 1 --evidence artifacts\synthetic-input\evidence.json --output artifacts\synthetic-run
.venv\Scripts\python -m handwritten_docs review-report artifacts\synthetic-input\synthetic.pdf --analysis artifacts\synthetic-run\analysis.json --output artifacts\synthetic-run
```

Open `artifacts\synthetic-run\report.html` locally. The demonstration uses rendered
font text pretending to be handwriting, a deliberately stale hidden OCR string, numeric
content, a protected crossing rule/signature-like sketch, and an unchanged second page.
It is a safety/plumbing fixture, **not an OCR accuracy benchmark**.

Physical PDF pages are one-based; `--pages 2,10,36-38` is explicit. There is no implicit
whole-document option. Settings bound selected pages, input bytes, JSON bytes, rendered
pixels, words and candidates per page. Pages are rendered and released one at a time.
Defaults permit 20 selected pages, not an unattended full-document run.

## Review and export

`review.json` contains one decision per annotation. Initially every decision is pending.
For a literal transcription inspected against its source crop, set `state` to
`approved`, supply `reviewer` and a UTC `reviewed_at`, and set `cleanup_reviewed` to
`true` only after independently checking that the removable ink is isolated text and
the area contains no unmarked protected content. `rejected` preserves the region.

If you edit `text`, refresh the content-bound digest first:

**PowerShell (workstation), repository root:**

```powershell
Set-Location <repository-root>
.venv\Scripts\python -m handwritten_docs review-report artifacts\synthetic-input\synthetic.pdf --analysis artifacts\synthetic-run\analysis.json --output artifacts\synthetic-run --refresh-bindings
```

This keeps literal text edits but resets **all decisions** to pending and clears
cleanup attestations. Inspect the new review, then supply fresh approvals. It never
silently reapproves changed text. Do not edit `analysis.json` to bypass a safety finding.
Analysis changes require fresh review and invalidate existing approval hashes.

**PowerShell (workstation), repository root:**

```powershell
Set-Location <repository-root>
.venv\Scripts\python -m handwritten_docs export artifacts\synthetic-input\synthetic.pdf --analysis artifacts\synthetic-run\analysis.json --output artifacts\synthetic-run
```

| Output | Meaning |
|---|---|
| `replacement.pdf` | Separate derived document; original source is never overwritten |
| `analysis.json` | Versioned source, geometry, runtime, service provenance and annotation evidence |
| `review.json` | Literal text, approval state, reviewer and source-bound digest |
| `manifest.json` | Replaced, preserved, pending and blocked regions with explicit reasons |
| `report.html`, `assets/` | Escaped local overview/before/after evidence; export reports show actual rendered PDF crops |
| `cleaned-<page>.png` | Working raster for changed pages, before typed vector placement |
| `font-license.txt` | Font notice, also embedded as an attachment in the derived PDF |
| `pages/`, `checkpoints/`, `cache/` | Ignored local rendered inputs and content-addressed checkpoints |

Keep the source **outside** the output directory. Review data and caches are private
local data, not a tamper-proof signature/audit system. Hash binding prevents accidental
stale approval; it does not defend against an operator deliberately rewriting all records.
Use a private working directory with appropriate local access controls and retention.

## Conservative replacement policy

| Gate | Effect |
|---|---|
| Source/config/font/runtime/geometry/content/mask changed | Existing review is rejected as stale |
| Numbers, identifiers, dates, units, equations or uncertain text | Require explicit literal text approval; never infer or calculate |
| Signatures, drawings, unknown content, formulas | Blocked in this version, including when approved |
| Missing local protection or complete-OCR attestation | Blocked; a model cannot supply human attestation |
| Printed words, protected boxes or other candidates overlap | Blocked |
| Grid/rule contact, uncertain boundary, colored ink, nonuniform/non-white background | Blocked |
| Missing glyph, multiline/vertical layout, or unreadable font size | Blocked |
| Uniform, locally inspected isolated ink and successful text fit | Remove only the pixel mask, never an entire rectangle |

The local operator must inventory signatures, drawings, stamps, printed matter and
other protected regions in the evidence. The uniform-background/boundary tests are
**not** a general signature/print classifier. An incomplete or dishonest local inspection
can defeat that assumption; do not mark complex scan regions safe merely because a
service finds text. Black handwriting touching black printed material cannot be safely
separated here. Formula evidence is retained literally, but all formula replacement is
explicitly blocked rather than executing arbitrary LaTeX or pretending layout is solved.

Automatic replacement is off by default (`calibration_id: null`). Supplying a local
calibration reference only enables the conservative plain-prose policy: DI/vision
whitespace-only agreement, strong individual OCR/style evidence, no uncertainty or
alternatives, grounded geometry, locally attested protection and cleanup, successful
masking and typography. Reviewable numbers, dates and unit-like text are excluded.
The lexical filters are conservative heuristics, not semantic proof; no class should
be enabled until labeled pilot evidence supports it without wrong automatic replacements.

Changed pages consist only of the cleaned raster, visible embedded-font replacements,
and rebuilt invisible OCR for retained DI words. Original changed-page streams are not
merged underneath; replaced words are omitted from hidden OCR. The complete-OCR
attestation matters: missing retained words would otherwise disappear from search.
Unchanged pages keep original streams without rasterization. Page count, MediaBox,
CropBox and rotation are checked before the derived PDF is published. Labels and basic
bookmark titles/page targets are preserved; bookmark view positions normalize to Fit.
Encrypted, form/signed, interactive-annotation and nonstandard UserUnit inputs are
rejected rather than implying those features or signature validity survive.

## Local evidence contract

`analyze` currently **imports** local service responses; it does not itself call Azure.
The synthetic generator is the executable example of the import contract.
Top-level evidence has exactly `schema_version: "1"`, `source_sha256`, `provenance`,
and `pages`. Each page entry has:

| Field | Contract |
|---|---|
| `source_page` | Original physical PDF page, not printed label |
| `di` | Raw GA `2024-11-30` `prebuilt-layout` result for one rendered page, pageNumber 1, explicit `stringIndexType: unicodeCodePoint` |
| `vision` | `VisionResult` schema: complete/refused/truncated status, literal proposals, alternatives, uncertainty, proposed boxes and protected regions |
| `local_review` | Identified local reviewer, JSON boolean `protection_complete` and `ocr_complete`, plus protected display-point boxes |

Vision boxes and all review geometry use displayed CropBox points, top-left origin.
DI pixels/inches are scaled against that exact rendered page, with aspect/orientation
validation. Code-point spans are checked against word content, including non-BMP text;
partial handwriting spans do not provide full-word strong style evidence.
Table row/column/cell context and literal formula records are retained separately.
Unmatched vision discoveries and DI-only handwriting are review-only. Refusals,
truncation, invalid enums/spans/geometry and unknown schema fields fail explicitly.

The import envelope preserves raw responses through the evidence digest; retain the
original private evidence file alongside outputs. Model/API/prompt versions and usage
must come from the original service response, not a fabricated unified confidence.
The DI/vision input and output are untrusted recognition evidence, not authoritative text.
Checksummed page checkpoints resume interrupted local analysis. Cache keys cover source,
evidence, selected pages, configuration, font bytes, package/runtime versions and algorithm.
Corrupt checkpoints fail rather than being silently reused.

## Azure gate and adapters

No Azure provisioning or sample uploads are needed to run the synthetic pipeline.
`services.py` supplies injectable async adapters for one-page DI layout and Foundry
vision overview plus contextual high-detail crops. DI requests use code-point offsets
and optionally `formulas`/`ocrHighResolution`. Vision uses strict structured output,
literal-only prompts and explicit refusal/truncation rejection.

There is deliberately no `--live` switch. Before integrating these adapters into a
real authorized run, record the exact target, selected source hash/pages, data permission,
region/residency/retention, pinned compatible vision model version, networking and cost
approval. `Authorization` binds a caller to the exact endpoint, source and pages; merely
having a sample is not consent. Configure the DI SDK for API `2024-11-30`, Entra credentials,
and no automatic POST retries (`retry_total=0`); configure OpenAI SDK retries explicitly
(`max_retries=0`) and the target's pinned API version. Clients remain caller-owned and
must be closed by the caller. The offline CLI never constructs these clients or credentials.

Use existing authorized resources first, least-privilege DI/OpenAI data-plane roles,
and approved private connectivity/DNS. The existing Foundry catalog module is not
wired into main and is not proof of private access; do not enable public access as a
workaround. New IaC, provisioning and any network exception need separate approval.

DI stores private operation continuation checkpoints. A lost submission response is
marked ambiguous and is **not** silently submitted/billed twice. Reconcile such an
operation manually before retrying. Polling retries are bounded and logged without
document content. Successful local analysis is reused without paid calls.
Live endpoint compatibility, actual service usage/latency and retention remain unverified.

## Validation and empirical limitations

**PowerShell (workstation), repository root:**

```powershell
Set-Location <repository-root>
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m compileall -q src
.venv\Scripts\python -m pip wheel --no-build-isolation --no-deps . --wheel-dir artifacts\dist
```

Tests generate synthetic PDFs/images locally: masked raster equality outside approved
ink is exact; PDFium final renders outside candidate placement bounds allow at most
one intensity level of recomposition rounding. Tests cover rotation/crop roundtrips,
stale/duplicate OCR removal, protected rules, numeric approval, glyph/fit rejection,
malformed/refused/truncated evidence, cache/approval invalidation, retry/resume and CLI stages.
No new static type checker is configured; public contracts have type annotations and
runtime schema validation, and compile/import checks are not claimed as static type checking.

No attached document, real crop, real output or confidential identifier belongs in git,
GitHub issues, logs, or CI artifacts. `local-data/` and `artifacts/` are ignored, but an
ignore rule is not an access-control boundary. Public CI runs synthetic tests only.

After separate Azure/data authorization, build a labeled pilot before enabling any
automatic class: report region precision/recall, character/word error, exact numeric/sign/unit
accuracy, formula correctness, protected-content changes, wrong automatic replacements,
coverage/abstentions, latency and actual billed usage. Zero errors on a small pilot is
not production proof. The current implementation intentionally makes no empirical
accuracy claim.

## Dependencies and fonts

Runtime packages are age-gated and hash-locked from the approved index. Azure SDKs and
Pydantic use MIT licenses, OpenAI and PDFium bindings use permissive Apache/BSD licensing,
pypdf/ReportLab/NumPy use BSD-style licenses and Pillow uses HPND. Review each shipped
dependency's license notices when distributing an application bundle.

The default is ReportLab's bundled Bitstream Vera TTF, embedded in derived PDFs.
Its `fonts/bitstream-vera-license.txt` ships with ReportLab; no font binary is copied into
this repository. It supports the synthetic Latin fixtures, not arbitrary mathematical
or multilingual content. A locally licensed Unicode font can be supplied in configuration
(`font_path`) or `HANDWRITTEN_DOCS_FONT`; the bytes are hashed into provenance and approval
bindings. A custom font also requires `font_license_path` pointing to its embedding and
redistribution notice; that notice accompanies the PDF. Check rights and glyph coverage before using another
font. Unsupported glyphs or formula layouts remain unchanged, not substituted with boxes.

## References

- [DI response and code-point spans](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/analyze-document-response?view=doc-intel-4.0.0)
- [Layout](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0)
- [Formula/high-resolution add-ons](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/add-on-capabilities?view=doc-intel-4.0.0)
- [Structured output](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs)
