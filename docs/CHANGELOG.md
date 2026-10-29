# Changelog

What changed for users of foundry-handwritten-docs, newest first. Each merged PR adds its line under
**Unreleased** (with its issue number); a release moves them under a dated version.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Handwriting CLI: `python -m handwritten_docs inspect <pdf>` reports each page's size,
  rotation, text layer and images, as a table or JSON, without the document's text; encrypted
  and damaged files are refused. Python dependencies are hash-locked, and CI lints and tests
  them (#8).
- README: **Overview** and **Quick start** sections to fill in, before the table of contents;
  the README rules keep them (#5).
- Repository created from
  [embergershared/azd-private-starter-template](https://github.com/embergershared/azd-private-starter-template).
