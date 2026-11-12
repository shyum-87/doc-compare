"""The call flow that the gateway and the fake share. Fails closed.

A call returns a result and never raises for anything that happens while it runs: a
failure comes back as FAILED with a reason. Only a mistake of the caller (no messages, no
prompt ID) is raised, before anything is sent.

Logs carry the prompt ID, the status, the reason, counts and times only: no prompt, no
answer, no address, no header value.
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, TypeVar

from pydantic import BaseModel

from app.llm.structured import instruction_for, parse_structured
from app.models.llm import (
    FORMAT_FAILURES,
    Attempt,
    CallRecord,
    LLMFailureReason,
    Message,
    StructuredResult,
    TextResult,
)

# Raise this whenever the instruction message, the retry rule or the classification changes.
GATEWAY_VERSION = "0.1.0"
# A structured answer in the wrong form is asked for this many times in all.
FORMAT_TRIES = 2

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_APP_ROOT = Path(__file__).resolve().parent.parent


def where(error: BaseException) -> str:
    """`file:line` of the innermost frame of this repository, or 'outside'."""
    for frame in reversed(traceback.extract_tb(error.__traceback__)):
        path = Path(frame.filename).resolve()
        if _APP_ROOT in path.parents:
            return f"{path.name}:{frame.lineno}"
    return "outside"


@dataclass(frozen=True)
class Outcome:
    """One request with its transport retries: a text or a failure, never both."""

    text: Optional[str]
    failure: Optional[LLMFailureReason]
    attempts: tuple[Attempt, ...] = ()
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


def _sum(values: Sequence[Optional[int]]) -> Optional[int]:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


class BaseLLM:
    """`complete` and `complete_structured`; a subclass sends the request."""

    model: Optional[str] = None
    _clock: Callable[[], float] = staticmethod(time.monotonic)

    def _request(self, messages: tuple[Message, ...], max_tokens: Optional[int]) -> Outcome:
        raise NotImplementedError

    def complete(
        self,
        messages: Sequence[Message],
        *,
        prompt_id: str,
        prompt_version: str,
        max_tokens: Optional[int] = None,
    ) -> TextResult:
        sent = _checked(messages, prompt_id, prompt_version)
        started = self._clock()
        outcome = self._safe_request(sent, max_tokens)
        record = self._record(prompt_id, prompt_version, [outcome], started)
        _log(record, outcome.failure)
        if outcome.failure is not None:
            return TextResult(status="FAILED", failure=outcome.failure, record=record)
        return TextResult(status="OK", text=outcome.text, record=record)

    def complete_structured(
        self,
        messages: Sequence[Message],
        schema: type[T],
        *,
        prompt_id: str,
        prompt_version: str,
        max_tokens: Optional[int] = None,
    ) -> StructuredResult[T]:
        sent = _checked(messages, prompt_id, prompt_version)
        if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
            raise TypeError("the schema is not a Pydantic model class")
        started = self._clock()
        outcomes: list[Outcome] = []
        value: Optional[T] = None
        text: Optional[str] = None
        failure: Optional[LLMFailureReason] = "INTERNAL_ERROR"
        try:
            sent = (*sent, instruction_for(schema))
            for _ in range(FORMAT_TRIES):
                outcome = self._safe_request(sent, max_tokens)
                failure = outcome.failure
                if outcome.text is not None:
                    read = parse_structured(outcome.text, schema)
                    if isinstance(read, str):
                        failure = read
                        outcome = _with_last_outcome(outcome, read)
                    else:
                        value, text = read, outcome.text
                outcomes.append(outcome)
                if failure not in FORMAT_FAILURES:
                    break
        except Exception as error:  # fail closed: nothing may escape as a result
            logger.error("internal error: %s at %s", type(error).__name__, where(error))
            value, text, failure = None, None, "INTERNAL_ERROR"
        record = self._record(prompt_id, prompt_version, outcomes, started)
        _log(record, failure)
        if failure is not None:
            return StructuredResult[schema](status="FAILED", failure=failure, record=record)
        return StructuredResult[schema](status="OK", value=value, text=text, record=record)

    def _safe_request(self, messages: tuple[Message, ...], max_tokens: Optional[int]) -> Outcome:
        try:
            outcome = self._request(messages, max_tokens)
            if (outcome.text is None) == (outcome.failure is None):
                raise ValueError("an outcome is a text or a failure")
            return outcome
        except Exception as error:  # fail closed
            # The message of the exception may quote the prompt, so only its type is logged.
            logger.error("internal error: %s at %s", type(error).__name__, where(error))
            return Outcome(text=None, failure="INTERNAL_ERROR")

    def _record(
        self, prompt_id: str, prompt_version: str, outcomes: Sequence[Outcome], started: float
    ) -> CallRecord:
        return CallRecord(
            model=self.model,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            gateway_version=GATEWAY_VERSION,
            attempts=tuple(attempt for outcome in outcomes for attempt in outcome.attempts),
            duration_ms=max(0, round((self._clock() - started) * 1000)),
            prompt_tokens=_sum([outcome.prompt_tokens for outcome in outcomes]),
            completion_tokens=_sum([outcome.completion_tokens for outcome in outcomes]),
        )


def _checked(
    messages: Sequence[Message], prompt_id: str, prompt_version: str
) -> tuple[Message, ...]:
    """Mistakes of the caller are refused before anything is sent."""
    sent = tuple(messages)
    if not sent or not all(isinstance(message, Message) for message in sent):
        raise ValueError("a call needs at least one Message")
    for name, value in (("prompt_id", prompt_id), ("prompt_version", prompt_version)):
        if not isinstance(value, str) or not value:
            raise ValueError(f"a call needs a {name}")
    return sent


def _with_last_outcome(outcome: Outcome, reason: LLMFailureReason) -> Outcome:
    """The request went through, but its answer has the wrong form."""
    attempts = outcome.attempts
    if attempts:
        attempts = (*attempts[:-1], attempts[-1].model_copy(update={"outcome": reason}))
    return Outcome(
        text=None,
        failure=reason,
        attempts=attempts,
        prompt_tokens=outcome.prompt_tokens,
        completion_tokens=outcome.completion_tokens,
    )


def _log(record: CallRecord, failure: Optional[LLMFailureReason]) -> None:
    counts = (len(record.attempts), record.duration_ms)
    if failure is None:
        logger.info("call %s: OK, attempts=%d, %d ms", record.prompt_id, *counts)
    else:
        logger.error("call %s: FAILED %s, attempts=%d, %d ms", record.prompt_id, failure, *counts)
