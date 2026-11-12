"""Reading a structured answer against a schema."""

from __future__ import annotations

import json
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

from app.llm.structured import instruction_for, parse_structured


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["PASS", "FAIL"]
    reason: str
    pages: tuple[int, ...] = ()


GOOD = '{"state": "PASS", "reason": "it is there"}'


def test_the_instruction_carries_the_json_schema():
    message = instruction_for(Verdict)
    assert message.role == "system"
    assert json.dumps(Verdict.model_json_schema(), ensure_ascii=False) in message.content
    assert "JSON" in message.content


def test_the_instruction_is_the_same_every_time():
    assert instruction_for(Verdict) == instruction_for(Verdict)


@pytest.mark.parametrize(
    "text",
    [
        GOOD,
        f"  \n{GOOD}\n ",
        f"```json\n{GOOD}\n```",
        f"```\n{GOOD}\n```",
        f"```JSON\r\n{GOOD}\r\n```\n",
    ],
)
def test_an_object_is_read_as_the_schema(text):
    assert parse_structured(text, Verdict) == Verdict(state="PASS", reason="it is there")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "PASS",
        f"Here is the answer: {GOOD}",  # nothing is cut out of running text
        f"{GOOD} I hope this helps.",
        f"```json\n{GOOD}\n```\nNote: checked twice.",
        f"```json\n{GOOD}\n```\n```json\n{GOOD}\n```",
        f"```json {GOOD}```",  # the fence lines are lines of their own
        f"[{GOOD}]",
        '"PASS"',
        "12",
        "null",
        '{"state": "PASS", "reason": "cut off',
    ],
)
def test_anything_but_one_json_object_is_invalid_json(text):
    assert parse_structured(text, Verdict) == "INVALID_JSON"


@pytest.mark.parametrize(
    "text",
    [
        "{}",
        '{"state": "PASS"}',
        '{"state": "MAYBE", "reason": "x"}',
        '{"state": "PASS", "reason": 3}',
        '{"state": "PASS", "reason": "x", "more": 1}',
    ],
)
def test_an_object_of_another_shape_is_a_schema_mismatch(text):
    assert parse_structured(text, Verdict) == "SCHEMA_MISMATCH"


def test_a_json_array_fills_a_tuple_and_a_string_does_not_fill_a_number():
    read = parse_structured('{"state": "FAIL", "reason": "x", "pages": [1, 2]}', Verdict)
    assert read.pages == (1, 2)
    text = '{"state": "FAIL", "reason": "x", "pages": ["1"]}'
    assert parse_structured(text, Verdict) == "SCHEMA_MISMATCH"
