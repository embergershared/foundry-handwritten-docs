"""Settings, read from environment variables in this module only.

Every other module receives a :class:`Settings` instead of reading the environment.
"""

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass

ENV_LOG_LEVEL = "HANDWRITTEN_DOCS_LOG_LEVEL"
ENV_MAX_PDF_MB = "HANDWRITTEN_DOCS_MAX_PDF_MB"

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_PDF_MB = 100
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
BYTES_PER_MB = 1024 * 1024


class ConfigError(ValueError):
    """An environment variable holds a value the tool cannot use."""


@dataclass(frozen=True)
class Settings:
    """What the tool needs from its environment."""

    log_level: str = DEFAULT_LOG_LEVEL
    max_pdf_bytes: int = DEFAULT_MAX_PDF_MB * BYTES_PER_MB

    @property
    def log_level_number(self) -> int:
        """The ``logging`` module's number for :attr:`log_level`."""
        return logging.getLevelNamesMapping()[self.log_level]


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Read the settings from ``environ`` (the process environment by default).

    Raises:
        ConfigError: a variable is set to a value outside its allowed range.
    """
    env = os.environ if environ is None else environ

    log_level = env.get(ENV_LOG_LEVEL, DEFAULT_LOG_LEVEL).strip().upper()
    if log_level not in LOG_LEVELS:
        raise ConfigError(f"{ENV_LOG_LEVEL} must be one of {', '.join(LOG_LEVELS)}.")

    raw_max_mb = env.get(ENV_MAX_PDF_MB, str(DEFAULT_MAX_PDF_MB)).strip()
    try:
        max_mb = int(raw_max_mb)
    except ValueError:
        raise ConfigError(f"{ENV_MAX_PDF_MB} must be a whole number of megabytes.") from None
    if max_mb < 1:
        raise ConfigError(f"{ENV_MAX_PDF_MB} must be at least 1.")

    return Settings(log_level=log_level, max_pdf_bytes=max_mb * BYTES_PER_MB)
