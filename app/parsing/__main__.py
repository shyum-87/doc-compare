"""Command line: python -m app.parsing <main file> --doc-id ... --out result.json

Exit codes: 0 = OK, 1 = REVIEW_REQUIRED, 2 = FAILED, a usage error, or no result file.
Codes 0 and 1 come out only after the result file is written.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Sequence, get_args

from app.models.document import Language
from app.parsing.ingest import ingest

EXIT_CODES = {"OK": 0, "REVIEW_REQUIRED": 1, "FAILED": 2}

logger = logging.getLogger("app.parsing")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.parsing",
        description="Read rag_ko.md (and rag.md) into elements and check the result.",
    )
    parser.add_argument("main_file", type=Path, help="rag_ko.md, or a Korean baseline document")
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--original-language", required=True, choices=list(get_args(Language)))
    parser.add_argument("--source", type=Path, default=None, help="rag.md before translation")
    parser.add_argument("--out", type=Path, required=True, help="result JSON (keep under out/)")
    return parser


def _same_file(first: Path, second: Path) -> bool:
    """Whether two paths name one file. A path that does not exist is compared as written."""
    try:
        return first.samefile(second)
    except (OSError, ValueError):
        return _spelling(first) == _spelling(second)


def _spelling(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.original_language == "ko" and args.source is not None:
        parser.error("--source cannot be used with --original-language ko")  # exits with 2
    inputs = [args.main_file] if args.source is None else [args.main_file, args.source]
    if any(_same_file(args.out, path) for path in inputs):
        # the result would replace the document that is being read
        parser.error("--out cannot be the main file or the source file")  # exits with 2

    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s"
    )
    # Nothing but 0, 1 or 2 leaves this function, and a log line names the type of an error
    # only: its message can hold a path, a document ID or text of the document.
    try:
        result = ingest(
            args.main_file,
            doc_id=args.doc_id,
            version=args.version,
            original_language=args.original_language,
            source_path=args.source,
        )
        # as bytes, so the file is UTF-8 with LF line ends on every platform
        data = result.model_dump_json(indent=2).encode("utf-8")
        exit_code = EXIT_CODES[result.status]
    except Exception as error:
        logger.error("internal error: %s", type(error).__name__)
        return 2
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(data)
    except Exception as error:
        logger.error("cannot write the result file: %s", type(error).__name__)
        return 2
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
