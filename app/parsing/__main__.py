"""Command line: python -m app.parsing <main file> --doc-id ... --out result.json

Exit codes: 0 = OK, 1 = REVIEW_REQUIRED, 2 = FAILED or a usage error.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

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
    parser.add_argument("--original-language", required=True, choices=["ko", "vi", "en", "zh"])
    parser.add_argument("--source", type=Path, default=None, help="rag.md before translation")
    parser.add_argument("--out", type=Path, required=True, help="result JSON (keep under out/)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.original_language == "ko" and args.source is not None:
        parser.error("--source cannot be used with --original-language ko")  # exits with 2

    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s"
    )
    result = ingest(
        args.main_file,
        doc_id=args.doc_id,
        version=args.version,
        original_language=args.original_language,
        source_path=args.source,
    )
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        # written as bytes so the file is UTF-8 with LF line ends on every platform
        args.out.write_bytes(result.model_dump_json(indent=2).encode("utf-8"))
    except OSError as error:
        logger.error("cannot write the result file: %s", type(error).__name__)
        return 2
    return EXIT_CODES[result.status]


if __name__ == "__main__":
    sys.exit(main())
