"""Ask for a JSON object and read the answer against a Pydantic schema.

An answer that passes has the right form and nothing more: whether what it says agrees
with the documents is checked by the caller.
"""

from __future__ import annotations

import json
import re
from typing import TypeVar, Union

from pydantic import BaseModel, ValidationError

from app.models.llm import LLMFailureReason, Message

T = TypeVar("T", bound=BaseModel)

# The whole answer inside one code fence, the fence lines on lines of their own.
_FENCED_RE = re.compile(r"```[A-Za-z]*[ \t]*\r?\n(.*?)\r?\n```", re.DOTALL)

_INSTRUCTION = (
    "Answer with one JSON object and nothing else: no explanation and no text before or "
    "after it. The object must be valid against this JSON Schema:\n"
)


def instruction_for(schema: type[BaseModel]) -> Message:
    """The message that is put after the messages of the caller."""
    return Message(
        role="system",
        content=_INSTRUCTION + json.dumps(schema.model_json_schema(), ensure_ascii=False),
    )


def parse_structured(text: str, schema: type[T]) -> Union[T, LLMFailureReason]:
    """Read an answer. Nothing is cut out of running text: only a whole-answer fence comes off."""
    body = text.strip()
    fenced = _FENCED_RE.fullmatch(body)
    if fenced:
        body = fenced.group(1)
    try:
        data = json.loads(body)
    except ValueError:
        return "INVALID_JSON"
    if not isinstance(data, dict):
        return "INVALID_JSON"
    try:
        # strict, as JSON: "3" is not 3, while an array still fills a tuple. A model that
        # writes another type has not followed the schema.
        return schema.model_validate_json(body, strict=True)
    except ValidationError:
        return "SCHEMA_MISMATCH"
