"""Logging to standard error, so standard output carries only the command's result."""

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: int) -> None:
    """Send log records at ``level`` and above to standard error."""
    logging.basicConfig(level=level, format=LOG_FORMAT, stream=sys.stderr, force=True)
