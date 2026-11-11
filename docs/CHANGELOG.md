# Changelog

What changed for users of foundry-handwritten-docs, newest first. Each merged PR adds its line under
**Unreleased** (with its issue number); a release moves them under a dated version.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Local handwriting replacement PoC: bounded PDF inspection, offline DI/vision evidence
  ingestion, versioned annotations, source-bound review, escaped local reports, conservative
  ink masks and clean-page PDF/OCR reconstruction. Synthetic-only regression coverage;
  real recognition quality and live Azure processing remain unevaluated and authorization-gated (#4).
- Hash-locked Python dependencies from the approved feed; Python CI now explicitly uses
  that feed and locked-package CI enforces an eight-day age minimum (#4).
- README: **Overview** and **Quick start** sections to fill in, before the table of contents;
  the README rules keep them (#5).
- Repository created from
  [embergershared/azd-private-starter-template](https://github.com/embergershared/azd-private-starter-template).
