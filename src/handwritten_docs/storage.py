"""Content-addressed, atomic local checkpoints. No document text in diagnostics."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def canonical(value: Any) -> bytes:
    def encode(item: Any) -> Any:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        if isinstance(item, Path):
            return str(item)
        raise TypeError("unsupported canonical value type")

    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        default=encode,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(canonical(value))
    os.replace(temp, path)


def read_json(path: Path, limit: int) -> Any:
    if path.stat().st_size > limit:
        raise ValueError("JSON exceeds configured size limit")
    return json.loads(path.read_bytes())


def select_pages(spec: str, count: int, maximum: int) -> list[int]:
    """Physical one-based PDF pages; never process all pages implicitly."""
    selected: set[int] = set()
    for token in spec.split(","):
        bounds = token.split("-")
        if len(bounds) == 1:
            selected.add(int(token))
        elif len(bounds) == 2:
            first, last = map(int, bounds)
            if first > last or last - first >= maximum:
                raise ValueError("invalid or excessive page range")
            selected.update(range(first, last + 1))
        else:
            raise ValueError("invalid page selection")
    if not selected or len(selected) > maximum or min(selected) < 1 or max(selected) > count:
        raise ValueError("page selection outside document or configured limit")
    return sorted(selected)
