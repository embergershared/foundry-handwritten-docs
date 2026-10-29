import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import synthetic_pdfs

from handwritten_docs.cli import EXIT_INPUT_ERROR, EXIT_OK, EXIT_USAGE_ERROR, main
from handwritten_docs.config import ENV_LOG_LEVEL

SRC = Path(__file__).resolve().parents[2] / "src"


def test_inspect_prints_one_row_per_page(mixed_pdf: Path) -> None:
    out = io.StringIO()

    assert main(["inspect", str(mixed_pdf)], out=out) == EXIT_OK

    lines = out.getvalue().splitlines()
    assert lines[0].startswith("mixed.pdf: 3 page(s), PDF 1.")
    assert len(lines) == 2 + 3
    assert lines[2].split()[:5] == ["1", "612", "x", "792", "0"]
    assert lines[3].rstrip().endswith("1 (850x1100)")
    assert lines[4].split()[4] == str(synthetic_pdfs.ROTATED_DEGREES)


def test_inspect_json_matches_the_report(mixed_pdf: Path) -> None:
    out = io.StringIO()

    assert main(["inspect", "--json", str(mixed_pdf)], out=out) == EXIT_OK

    report = json.loads(out.getvalue())
    assert report["file_name"] == "mixed.pdf"
    assert report["page_count"] == 3
    assert [page["has_text_layer"] for page in report["pages"]] == [True, False, True]
    assert report["pages"][1]["images"][0]["width_px"] == synthetic_pdfs.SCAN_SIZE_PX[0]


def test_json_never_contains_document_text(printed_pdf: Path) -> None:
    out = io.StringIO()

    main(["inspect", "--json", str(printed_pdf)], out=out)

    assert synthetic_pdfs.SECRET_PHRASE not in out.getvalue()


def test_unusable_input_exits_1_with_the_reason_on_stderr(
    encrypted_pdf: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = io.StringIO()

    assert main(["inspect", str(encrypted_pdf)], out=out) == EXIT_INPUT_ERROR

    assert out.getvalue() == ""
    assert "encrypted.pdf is encrypted" in capsys.readouterr().err


def test_bad_settings_exit_2(
    printed_pdf: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(ENV_LOG_LEVEL, "VERBOSE")

    assert main(["inspect", str(printed_pdf)], out=io.StringIO()) == EXIT_USAGE_ERROR

    assert ENV_LOG_LEVEL in capsys.readouterr().err


def test_missing_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exited:
        main([], out=io.StringIO())

    assert exited.value.code == EXIT_USAGE_ERROR


def test_runs_as_a_module(printed_pdf: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    env.pop(ENV_LOG_LEVEL, None)

    result = subprocess.run(
        [sys.executable, "-m", "handwritten_docs", "inspect", str(printed_pdf)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == EXIT_OK, result.stderr
    assert result.stdout.startswith("printed.pdf: 1 page(s)")
