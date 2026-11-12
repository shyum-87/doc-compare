"""A fake LLM for tests: scripted answers, no network (D-002).

It shares the call flow of the gateway, so reading a structured answer and asking once
more work the same way.
"""

from __future__ import annotations

from typing import Optional, Sequence, get_args

from app.llm.base import BaseLLM, Outcome
from app.models.llm import Attempt, LLMFailureReason, Message

_REASONS = frozenset(get_args(LLMFailureReason))


class FakeLLM(BaseLLM):
    """Gives `answers` in order, one per request.

    An answer that spells a failure reason ("TIMEOUT") makes that request fail with it.
    Running out of answers is an INTERNAL_ERROR.
    """

    def __init__(self, answers: Sequence[str], model: str = "fake-model") -> None:
        self.model = model
        self.calls: list[tuple[Message, ...]] = []
        self.max_tokens: list[Optional[int]] = []
        self._answers = list(answers)

    def _request(self, messages: tuple[Message, ...], max_tokens: Optional[int]) -> Outcome:
        self.calls.append(messages)
        self.max_tokens.append(max_tokens)
        number = len(self.calls)
        if number > len(self._answers):
            raise IndexError("the fake has no answer left")
        answer = self._answers[number - 1]
        failed = answer in _REASONS
        attempt = Attempt(
            prompt_msg_id=f"fake-prompt-{number}",
            completion_msg_id=f"fake-completion-{number}",
            outcome=answer if failed else "OK",
            duration_ms=0,
        )
        if failed:
            return Outcome(text=None, failure=answer, attempts=(attempt,))
        return Outcome(text=answer, failure=None, attempts=(attempt,))
