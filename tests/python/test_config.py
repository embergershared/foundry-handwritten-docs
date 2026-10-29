import logging

import pytest

from handwritten_docs.config import (
    BYTES_PER_MB,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MAX_PDF_MB,
    ENV_LOG_LEVEL,
    ENV_MAX_PDF_MB,
    ConfigError,
    load_settings,
)


def test_defaults_when_nothing_is_set() -> None:
    settings = load_settings({})

    assert settings.log_level == DEFAULT_LOG_LEVEL
    assert settings.max_pdf_bytes == DEFAULT_MAX_PDF_MB * BYTES_PER_MB


def test_values_are_read_and_normalized() -> None:
    settings = load_settings({ENV_LOG_LEVEL: " debug ", ENV_MAX_PDF_MB: "5"})

    assert settings.log_level == "DEBUG"
    assert settings.log_level_number == logging.DEBUG
    assert settings.max_pdf_bytes == 5 * BYTES_PER_MB


@pytest.mark.parametrize("level", ["VERBOSE", "TRACE", "CRITICAL", ""])
def test_only_standard_log_levels_are_accepted(level: str) -> None:
    with pytest.raises(ConfigError, match=ENV_LOG_LEVEL):
        load_settings({ENV_LOG_LEVEL: level})


@pytest.mark.parametrize("value", ["ten", "1.5", "", "0", "-3"])
def test_max_pdf_size_must_be_a_positive_whole_number(value: str) -> None:
    with pytest.raises(ConfigError, match=ENV_MAX_PDF_MB):
        load_settings({ENV_MAX_PDF_MB: value})
