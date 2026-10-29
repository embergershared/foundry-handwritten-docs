# Handwriting CLI

`handwritten_docs` is a local, offline command-line tool that finds the handwritten content of
mixed printed and handwritten PDFs, lets a person review it, and replaces it with typed text
where that is safe. It is built in phases ([#4](https://github.com/embergershared/foundry-handwritten-docs/issues/4)):

| Command | What it does | Status |
|---|---|---|
| `inspect` | Reports each page's size, rotation, text layer and images | Available |
| `extract` | Places recorded recognition results on the pages and classifies each handwritten region | Phase 2 |
| `review`, `approve` | A review file and HTML preview; approvals bound to the exact input | Phase 3 |
| `export` | A new PDF with the approved regions replaced by their typed text | Phase 4 |

It makes no cloud call: recognition results are read from files, and the source PDF is never
modified.

## Set up (PowerShell, workstation)

Python 3.13 (`.python-version`) in the project's `.venv`, with the hash-locked packages:

```powershell
Set-Location <repository folder>
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r requirements-dev.lock
```

`requirements.lock` holds the runtime packages only; `requirements-dev.lock` adds the test and
lint tools. To add or change a package, see [supply-chain.md](supply-chain.md).

## Run (PowerShell, workstation)

The package lives in `src/`, so put it on the path for the session, then run it from the
repository root:

```powershell
$env:PYTHONPATH = 'src'
.venv\Scripts\python -m handwritten_docs inspect samples\contoso-form.pdf
.venv\Scripts\python -m handwritten_docs inspect samples\contoso-form.pdf --json
```

Keep real documents in `samples/` and outputs in `out/`: both are gitignored, so nothing from a
real document reaches the public repository.

### `inspect`

On the tests' synthetic three-page PDF (printed text with a note image, a scan, a rotated page):

```text
mixed.pdf: 3 page(s), PDF 1.3, 54.0 KB
page  size (pt)          rotation  text layer    images
   1  612 x 792                 0  yes (92)      1 (400x120)
   2  612 x 792                 0  no            1 (850x1100)
   3  792 x 612                90  yes (92)      0
```

- **size (pt):** the page's visible box (crop box), in points (1/72 inch), before rotation.
- **rotation:** the page's `/Rotate` value, 0, 90, 180 or 270.
- **text layer:** whether the page has extractable text, with its count of non-space
  characters. A scanned page has none unless it was OCR'd.
- **images:** the image objects drawn on the page (including those inside form objects), with
  their size in pixels. Inline images are not counted.

`--json` writes the same report as JSON. The report holds counts and sizes only, never the
document's text, so it can be shared.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Done |
| 1 | The input can't be used: missing, over the size limit, encrypted, or not a readable PDF. The reason is logged on standard error. |
| 2 | Bad arguments or settings |

Encrypted PDFs are refused, not opened, even when they have no user password.

## Settings

Read from environment variables, in `src/handwritten_docs/config.py` only:

| Variable | Default | Meaning |
|---|---|---|
| `HANDWRITTEN_DOCS_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. Logs go to standard error. |
| `HANDWRITTEN_DOCS_MAX_PDF_MB` | `100` | Larger files are refused before they are read. |

## Develop and test (PowerShell, workstation)

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
```

The tests are offline and use synthetic PDFs that `tests/python/synthetic_pdfs.py` generates
at run time (printed, scanned, rotated, image inside a form, encrypted, damaged). Never add a
real document, or anything derived from one, to the tests. CI runs the same three commands in
its **Python lint and test** job.

## Code

| Path | What it holds |
|---|---|
| `src/handwritten_docs/cli.py` | The commands, output formats and exit codes |
| `src/handwritten_docs/config.py` | Settings from environment variables |
| `src/handwritten_docs/inspection.py` | PDF inspection with `pypdf` |
| `src/handwritten_docs/logging_setup.py` | Logging to standard error |
| `tests/python/` | pytest tests and the synthetic PDF generator |
