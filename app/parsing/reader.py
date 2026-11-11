"""Read an input file into lines. Expected input problems are returned, not raised."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.models.findings import FailureReason

_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class ReadResult:
    file_name: str
    sha256: Optional[str]
    lines: tuple[str, ...]
    error: Optional[FailureReason]


def read_lines(path: Path) -> ReadResult:
    """Decode as UTF-8 (BOM ignored) and hash the raw bytes.

    CRLF, LF and a lone CR each end a line; no other character does.
    """
    file_name = path.name
    try:
        data = path.read_bytes()
    except (OSError, ValueError):  # ValueError: the path holds a NUL character
        return ReadResult(file_name=file_name, sha256=None, lines=(), error="FILE_UNREADABLE")
    digest = hashlib.sha256(data).hexdigest()
    body = data[len(_BOM) :] if data.startswith(_BOM) else data
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return ReadResult(file_name=file_name, sha256=digest, lines=(), error="NOT_UTF8")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    if not any(line.strip() for line in lines):
        return ReadResult(file_name=file_name, sha256=digest, lines=(), error="EMPTY_DOCUMENT")
    return ReadResult(file_name=file_name, sha256=digest, lines=tuple(lines), error=None)
