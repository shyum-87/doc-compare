"""The shared call flow, driven through the fake LLM."""

from __future__ import annotations

import logging

import pytest
from pydantic import BaseModel, ConfigDict

from app.llm.base import GATEWAY_VERSION, BaseLLM, Outcome
from app.llm.fake import FakeLLM
from app.llm.structured import instruction_for
from app.models.llm import Message, StructuredResult, TextResult

PROMPT = (Message(role="system", content="You check documents."), Message(role="user", content="Q"))
IDS = {"prompt_id": "test.prompt", "prompt_version": "3"}


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: str


GOOD = '{"verdict": "yes"}'


def _outcomes(result) -> list[str]:
    return [attempt.outcome for attempt in result.record.attempts]


def test_a_text_call():
    llm = FakeLLM(["hello"])
    result = llm.complete(PROMPT, **IDS)
    assert isinstance(result, TextResult)
    assert (result.status, result.text, result.failure) == ("OK", "hello", None)
    assert llm.calls == [PROMPT]
    record = result.record
    assert record.model == "fake-model"
    assert (record.prompt_id, record.prompt_version) == ("test.prompt", "3")
    assert record.gateway_version == GATEWAY_VERSION
    assert _outcomes(result) == ["OK"]


def test_max_tokens_reaches_the_request_only_when_given():
    llm = FakeLLM(["a", "b"])
    llm.complete(PROMPT, **IDS)
    llm.complete(PROMPT, max_tokens=50, **IDS)
    assert llm.max_tokens == [None, 50]


def test_a_scripted_failure():
    result = FakeLLM(["AUTH_ERROR"]).complete(PROMPT, **IDS)
    assert (result.status, result.text, result.failure) == ("FAILED", None, "AUTH_ERROR")
    assert _outcomes(result) == ["AUTH_ERROR"]


def test_a_structured_call_adds_the_instruction_last():
    llm = FakeLLM([GOOD])
    result = llm.complete_structured(PROMPT, Answer, **IDS)
    assert isinstance(result, StructuredResult)
    assert result.status == "OK"
    assert result.value == Answer(verdict="yes")
    assert result.text == GOOD
    assert llm.calls == [(*PROMPT, instruction_for(Answer))]


@pytest.mark.parametrize(
    ("bad", "reason"), [("not json", "INVALID_JSON"), ('{"other": 1}', "SCHEMA_MISMATCH")]
)
def test_a_wrong_form_is_asked_for_once_more(bad, reason):
    llm = FakeLLM([bad, GOOD])
    result = llm.complete_structured(PROMPT, Answer, **IDS)
    assert result.status == "OK"
    assert result.value == Answer(verdict="yes")
    assert _outcomes(result) == [reason, "OK"]
    assert llm.calls[0] == llm.calls[1]  # the same request, nothing about the first answer


def test_a_wrong_form_twice_fails_and_is_not_asked_for_a_third_time():
    llm = FakeLLM(["not json", '{"other": 1}', GOOD])
    result = llm.complete_structured(PROMPT, Answer, **IDS)
    assert (result.status, result.failure) == ("FAILED", "SCHEMA_MISMATCH")
    assert result.value is None and result.text is None
    assert _outcomes(result) == ["INVALID_JSON", "SCHEMA_MISMATCH"]
    assert len(llm.calls) == 2


def test_another_failure_is_not_asked_for_again():
    llm = FakeLLM(["AUTH_ERROR", GOOD])
    result = llm.complete_structured(PROMPT, Answer, **IDS)
    assert (result.status, result.failure) == ("FAILED", "AUTH_ERROR")
    assert len(llm.calls) == 1


def test_a_failure_after_a_wrong_form_is_the_failure_of_the_call():
    result = FakeLLM(["not json", "TIMEOUT"]).complete_structured(PROMPT, Answer, **IDS)
    assert (result.status, result.failure) == ("FAILED", "TIMEOUT")
    assert _outcomes(result) == ["INVALID_JSON", "TIMEOUT"]


def test_running_out_of_answers_is_an_internal_error():
    llm = FakeLLM([])
    assert llm.complete(PROMPT, **IDS).failure == "INTERNAL_ERROR"
    assert llm.complete_structured(PROMPT, Answer, **IDS).failure == "INTERNAL_ERROR"


class _Broken(BaseLLM):
    def __init__(self, outcome=None):
        self._outcome = outcome

    def _request(self, messages, max_tokens):
        if self._outcome is None:
            raise RuntimeError("the prompt was: " + messages[-1].content)
        return self._outcome


@pytest.mark.parametrize(
    "outcome",
    [
        None,  # raises
        Outcome(text=None, failure=None),
        Outcome(text="both", failure="TIMEOUT"),
    ],
)
def test_nothing_escapes_a_call(outcome, caplog):
    with caplog.at_level(logging.DEBUG):
        text = _Broken(outcome).complete(PROMPT, **IDS)
        structured = _Broken(outcome).complete_structured(PROMPT, Answer, **IDS)
    assert (text.status, text.failure, text.text) == ("FAILED", "INTERNAL_ERROR", None)
    assert (structured.status, structured.failure) == ("FAILED", "INTERNAL_ERROR")
    assert "the prompt was" not in caplog.text  # the type of the exception only
    if outcome is None:
        # the innermost frame of app/: the test file that raised is not part of it
        assert "internal error: RuntimeError at base.py:" in caplog.text


@pytest.mark.parametrize(
    "arguments",
    [
        {"messages": [], **IDS},
        {"messages": [{"role": "user", "content": "Q"}], **IDS},
        {"messages": PROMPT, "prompt_id": "", "prompt_version": "1"},
        {"messages": PROMPT, "prompt_id": "p", "prompt_version": ""},
        {"messages": PROMPT, "prompt_id": "p", "prompt_version": 1},
    ],
)
def test_a_mistake_of_the_caller_is_raised_before_anything_is_sent(arguments):
    llm = FakeLLM(["hello"])
    with pytest.raises(ValueError):
        llm.complete(**arguments)
    with pytest.raises(ValueError):
        llm.complete_structured(schema=Answer, **arguments)
    assert llm.calls == []


def test_a_schema_that_is_not_a_model_class_is_raised():
    llm = FakeLLM(["hello"])
    with pytest.raises(TypeError):
        llm.complete_structured(PROMPT, dict, **IDS)
    assert llm.calls == []


def test_the_log_holds_ids_codes_and_counts_only(caplog):
    llm = FakeLLM(["the answer text", "not json", "RATE_LIMITED"])
    with caplog.at_level(logging.DEBUG):
        llm.complete(PROMPT, **IDS)
        llm.complete_structured(PROMPT, Answer, **IDS)
    lines = [(record.levelname, record.getMessage()) for record in caplog.records]
    assert lines == [
        ("INFO", "call test.prompt: OK, attempts=1, 0 ms"),
        ("ERROR", "call test.prompt: FAILED RATE_LIMITED, attempts=2, 0 ms"),
    ]


def test_token_counts_add_up_over_the_requests_of_one_call():
    class _Counting(BaseLLM):
        def __init__(self):
            self.answers = [("not json", 10, 2), (GOOD, 11, None)]

        def _request(self, messages, max_tokens):
            text, prompt_tokens, completion_tokens = self.answers.pop(0)
            return Outcome(
                text=text,
                failure=None,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

    record = _Counting().complete_structured(PROMPT, Answer, **IDS).record
    assert (record.prompt_tokens, record.completion_tokens) == (21, 2)
    assert FakeLLM(["x"]).complete(PROMPT, **IDS).record.prompt_tokens is None
