"""Command line: python -m app.llm check [--env-file .env]

Makes one text call and one structured call with fixed sentences that have nothing to do
with any document, and shows the status, the reason, counts and times only.

Exit codes: 0 = both calls are OK, 2 = anything else.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from pydantic import BaseModel

from app.llm.config import read_env_file
from app.llm.gateway import LLMGateway
from app.models.llm import Message, StructuredResult, TextResult

logger = logging.getLogger("app.llm")

TEXT_PROMPT = (Message(role="user", content="Reply with the single word OK."),)
STRUCTURED_PROMPT = (Message(role="user", content='Set the field "answer" to the word OK.'),)
PROMPT_VERSION = "1"


class CheckAnswer(BaseModel):
    answer: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.llm", description="Check the connection to the in-house LLM."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="one text call and one structured call")
    check.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="KEY=VALUE lines; a variable that is set in the environment wins",
    )
    return parser


def _report(name: str, result: Union[TextResult, StructuredResult]) -> bool:
    record = result.record
    counts = f"attempts={len(record.attempts)}, {record.duration_ms} ms"
    if result.status == "OK":
        usage = "yes" if record.prompt_tokens is not None else "no"
        logger.info("%s: OK, %s, usage=%s", name, counts, usage)
        return True
    status = record.attempts[-1].http_status if record.attempts else None
    http = f" (http {status})" if status is not None else ""
    logger.error("%s: FAILED %s%s, %s", name, result.failure, http, counts)
    return False


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
    gateway_factory: Callable[[Mapping[str, str]], Any] = LLMGateway.from_env,
) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s"
    )
    # Nothing but 0 or 2 leaves this function, and a log line names the type of an error
    # only: its message can hold a path, the address or a value of the settings.
    try:
        values = dict(os.environ if env is None else env)
        if args.env_file is not None:
            try:
                values = {**read_env_file(args.env_file), **values}
            except (OSError, ValueError) as error:
                logger.error("cannot read the env file: %s", type(error).__name__)
                return 2
        gateway = gateway_factory(values)
        failure = getattr(gateway, "config_failure", None)
        if failure is not None:
            names = ", ".join(getattr(gateway, "config_variables", ()))
            logger.error("configuration: %s: %s", failure, names)
            return 2
        text = gateway.complete(
            TEXT_PROMPT, prompt_id="llm.check.text", prompt_version=PROMPT_VERSION
        )
        text_ok = _report("text call", text)
        structured = gateway.complete_structured(
            STRUCTURED_PROMPT,
            CheckAnswer,
            prompt_id="llm.check.structured",
            prompt_version=PROMPT_VERSION,
        )
        structured_ok = _report("structured call", structured)
    except Exception as error:
        logger.error("internal error: %s", type(error).__name__)
        return 2
    return 0 if text_ok and structured_ok else 2


if __name__ == "__main__":
    sys.exit(main())
