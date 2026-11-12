"""Messages sent to the LLM and the result of a call.

A result never holds the prompt, and a FAILED result never holds an answer: nothing that
comes after can take a failed call for a normal one.
"""

from __future__ import annotations

from typing import Generic, Literal, Optional, TypeVar, Union

from pydantic import BaseModel, Field, model_validator

from app.models.document import FrozenModel

Role = Literal["system", "user", "assistant"]
LLMStatus = Literal["OK", "FAILED"]
LLMFailureReason = Literal[
    "CONFIG_MISSING",
    "CONFIG_INVALID",
    "TIMEOUT",
    "CONNECTION_ERROR",
    "RATE_LIMITED",
    "SERVER_ERROR",
    "AUTH_ERROR",
    "BAD_REQUEST",
    "UNEXPECTED_RESPONSE",
    "EMPTY_RESPONSE",
    "TRUNCATED",
    "CONTENT_FILTERED",
    "INVALID_JSON",
    "SCHEMA_MISMATCH",
    "INTERNAL_ERROR",
]

# Sent again, each time with new message IDs.
RETRYABLE: frozenset[str] = frozenset(
    {"TIMEOUT", "CONNECTION_ERROR", "RATE_LIMITED", "SERVER_ERROR"}
)
# A structured answer in the wrong form: the request is made once more.
FORMAT_FAILURES: frozenset[str] = frozenset({"INVALID_JSON", "SCHEMA_MISMATCH"})

T = TypeVar("T", bound=BaseModel)


class Message(FrozenModel):
    role: Role
    content: str


class Attempt(FrozenModel):
    """One request on the wire. Both IDs are new for every attempt."""

    prompt_msg_id: str
    completion_msg_id: str
    outcome: Union[Literal["OK"], LLMFailureReason]
    http_status: Optional[int] = None
    duration_ms: int = Field(ge=0)


class CallRecord(FrozenModel):
    """What produced a result: kept with every verdict that is built on it."""

    model: Optional[str]  # None when the settings could not be read
    prompt_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    gateway_version: str
    attempts: tuple[Attempt, ...]
    duration_ms: int = Field(ge=0)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class TextResult(FrozenModel):
    status: LLMStatus
    text: Optional[str] = None
    failure: Optional[LLMFailureReason] = None
    record: CallRecord

    @model_validator(mode="after")
    def _status_agrees_with_the_content(self) -> TextResult:
        if self.status == "OK":
            if self.text is None or self.failure is not None:
                raise ValueError("an OK result has a text and no failure")
        elif self.failure is None or self.text is not None:
            raise ValueError("a FAILED result has a failure and no text")
        return self


class StructuredResult(FrozenModel, Generic[T]):
    """`text` is the answer as it came; `value` is that answer read against the schema."""

    status: LLMStatus
    value: Optional[T] = None
    text: Optional[str] = None
    failure: Optional[LLMFailureReason] = None
    record: CallRecord

    @model_validator(mode="after")
    def _status_agrees_with_the_content(self) -> StructuredResult[T]:
        if self.status == "OK":
            if self.value is None or self.text is None or self.failure is not None:
                raise ValueError("an OK result has a value, a text and no failure")
        elif self.failure is None or self.value is not None or self.text is not None:
            raise ValueError("a FAILED result has a failure and no value or text")
        return self
