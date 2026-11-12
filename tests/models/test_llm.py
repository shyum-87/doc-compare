"""Result models of an LLM call."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError

from app.models.llm import (
    FORMAT_FAILURES,
    RETRYABLE,
    Attempt,
    CallRecord,
    LLMFailureReason,
    Message,
    StructuredResult,
    TextResult,
)

ALL_REASONS = get_args(LLMFailureReason)


class Answer(BaseModel):
    verdict: str


def _record(*outcomes: str) -> CallRecord:
    attempts = tuple(
        Attempt(prompt_msg_id=f"p{i}", completion_msg_id=f"c{i}", outcome=outcome, duration_ms=1)
        for i, outcome in enumerate(outcomes)
    )
    return CallRecord(
        model="m",
        prompt_id="test.prompt",
        prompt_version="1",
        gateway_version="0.0.0",
        attempts=attempts,
        duration_ms=5,
    )


def test_the_reason_sets_name_known_reasons():
    assert RETRYABLE == {"TIMEOUT", "CONNECTION_ERROR", "RATE_LIMITED", "SERVER_ERROR"}
    assert FORMAT_FAILURES == {"INVALID_JSON", "SCHEMA_MISMATCH"}
    assert RETRYABLE | FORMAT_FAILURES <= set(ALL_REASONS)
    assert len(ALL_REASONS) == 15


def test_a_message_has_one_of_three_roles():
    assert Message(role="user", content="x").role == "user"
    with pytest.raises(ValidationError):
        Message(role="tool", content="x")


def test_an_ok_text_result():
    result = TextResult(status="OK", text="hello", record=_record("OK"))
    assert result.failure is None


def test_a_failed_text_result():
    result = TextResult(status="FAILED", failure="TIMEOUT", record=_record("TIMEOUT"))
    assert result.text is None


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "OK"},  # no text
        {"status": "OK", "text": "x", "failure": "TIMEOUT"},
        {"status": "FAILED"},  # no failure
        {"status": "FAILED", "failure": "TIMEOUT", "text": "x"},  # a failure carries no answer
        {"status": "FAILED", "failure": "SOMETHING_ELSE"},
        {"status": "DONE", "text": "x"},
    ],
)
def test_a_text_result_that_disagrees_with_itself_is_refused(fields):
    with pytest.raises(ValidationError):
        TextResult(record=_record("OK"), **fields)


def test_an_ok_structured_result_keeps_the_answer_and_its_reading_apart():
    result = StructuredResult[Answer](
        status="OK", value=Answer(verdict="yes"), text='{"verdict": "yes"}', record=_record("OK")
    )
    assert result.value.verdict == "yes"
    assert result.text == '{"verdict": "yes"}'


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "OK", "text": "{}"},  # no value
        {"status": "OK", "value": Answer(verdict="yes")},  # no text
        {"status": "FAILED", "failure": "SCHEMA_MISMATCH", "text": "{}"},
        {"status": "FAILED", "failure": "SCHEMA_MISMATCH", "value": Answer(verdict="yes")},
        {"status": "FAILED"},
    ],
)
def test_a_structured_result_that_disagrees_with_itself_is_refused(fields):
    with pytest.raises(ValidationError):
        StructuredResult[Answer](record=_record("OK"), **fields)


def test_an_attempt_outcome_is_ok_or_a_reason():
    with pytest.raises(ValidationError):
        Attempt(prompt_msg_id="p", completion_msg_id="c", outcome="MAYBE", duration_ms=1)


def test_results_are_frozen_and_take_no_unknown_fields():
    result = TextResult(status="OK", text="hello", record=_record("OK"))
    with pytest.raises(ValidationError):
        result.text = "other"
    with pytest.raises(ValidationError):
        TextResult(status="OK", text="hello", record=_record("OK"), prompt="x")


def test_a_result_reads_back_from_json():
    text = TextResult(status="FAILED", failure="RATE_LIMITED", record=_record("RATE_LIMITED"))
    assert TextResult.model_validate_json(text.model_dump_json()) == text
    structured = StructuredResult[Answer](
        status="OK", value=Answer(verdict="yes"), text="{}", record=_record("INVALID_JSON", "OK")
    )
    assert StructuredResult[Answer].model_validate_json(structured.model_dump_json()) == structured
