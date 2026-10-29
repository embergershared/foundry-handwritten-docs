"""Fixtures: the synthetic PDFs, written to each test's temporary folder."""

from pathlib import Path

import pytest
import synthetic_pdfs

from handwritten_docs.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def printed_pdf(tmp_path: Path) -> Path:
    return synthetic_pdfs.write_printed(tmp_path / "printed.pdf")


@pytest.fixture
def scanned_pdf(tmp_path: Path) -> Path:
    return synthetic_pdfs.write_scanned(tmp_path / "scanned.pdf")


@pytest.fixture
def mixed_pdf(tmp_path: Path) -> Path:
    return synthetic_pdfs.write_mixed(tmp_path / "mixed.pdf")


@pytest.fixture
def form_image_pdf(tmp_path: Path) -> Path:
    return synthetic_pdfs.write_image_in_form(tmp_path / "form-image.pdf")


@pytest.fixture
def encrypted_pdf(tmp_path: Path) -> Path:
    return synthetic_pdfs.write_encrypted(tmp_path / "encrypted.pdf")


@pytest.fixture
def not_a_pdf(tmp_path: Path) -> Path:
    return synthetic_pdfs.write_not_a_pdf(tmp_path / "not-a.pdf")


@pytest.fixture
def truncated_pdf(tmp_path: Path) -> Path:
    return synthetic_pdfs.write_truncated(tmp_path / "truncated.pdf")
