"""The gateway on the real SDK path, with a mock transport in place of the network."""

from __future__ import annotations

import json
import logging
import uuid

import httpx2
import pytest
from conftest import completion
from pydantic import BaseModel

from app.llm.gateway import BACKOFF_SECONDS, MAX_ATTEMPTS
from app.llm.structured import instruction_for
from app.models.llm import RETRYABLE, Message

PROMPT = (Message(role="system", content="You check documents."), Message(role="user", content="Q"))
IDS = {"prompt_id": "test.prompt", "prompt_version": "1"}
SECRET_BODY = "body-of-the-error-answer"


class Answer(BaseModel):
    verdict: str


def _error(status: int) -> httpx2.Response:
    return httpx2.Response(status, json={"error": {"message": SECRET_BODY}})


def _raise(error: Exception):
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise error

    return handler


def _in_turn(*responses):
    """Each request gets the next response; an exception in the list is raised."""
    left = list(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        response = left.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    return handler


def _outcomes(result) -> list[str]:
    return [attempt.outcome for attempt in result.record.attempts]


# --- the request ---------------------------------------------------------------------


def test_the_request_goes_to_the_address_of_the_settings(make_gateway):
    wire = make_gateway(lambda request: completion())
    result = wire.gateway.complete(PROMPT, **IDS)
    assert (result.status, result.text) == ("OK", "hello")
    (request,) = wire.requests
    assert request.method == "POST"
    assert str(request.url) == "http://gateway.test/v1/chat/completions"
    assert json.loads(request.content) == {
        "model": "model-value",
        "messages": [
            {"role": "system", "content": "You check documents."},
            {"role": "user", "content": "Q"},
        ],
        "temperature": 0,
    }


def test_max_tokens_is_sent_only_when_given(make_gateway):
    wire = make_gateway(lambda request: completion())
    wire.gateway.complete(PROMPT, max_tokens=50, **IDS)
    assert json.loads(wire.requests[0].content)["max_tokens"] == 50


def test_the_fixed_headers(make_gateway):
    wire = make_gateway(lambda request: completion())
    wire.gateway.complete(PROMPT, **IDS)
    headers = wire.requests[0].headers
    assert headers["x-dep-ticket"] == "ticket-value"
    assert headers["Send-System-Name"] == "system-value"
    assert headers["User-Id"] == "user-value"
    assert headers["User-Type"] == "AD_ID"
    assert headers["Authorization"] == "Bearer placeholder"


def test_the_api_key_of_the_settings_is_used(make_gateway, full_env):
    wire = make_gateway(lambda request: completion(), {**full_env, "DS_OPENAI_API_KEY": "key"})
    wire.gateway.complete(PROMPT, **IDS)
    assert wire.requests[0].headers["Authorization"] == "Bearer key"


def test_every_call_has_new_message_ids(make_gateway):
    wire = make_gateway(lambda request: completion())
    first = wire.gateway.complete(PROMPT, **IDS)
    second = wire.gateway.complete(PROMPT, **IDS)
    seen = []
    for request, result in zip(wire.requests, (first, second), strict=True):
        (attempt,) = result.record.attempts
        assert request.headers["Prompt-Msg-Id"] == attempt.prompt_msg_id
        assert request.headers["Completion-Msg-Id"] == attempt.completion_msg_id
        seen += [attempt.prompt_msg_id, attempt.completion_msg_id]
    assert len(set(seen)) == 4
    for value in seen:
        assert str(uuid.UUID(value)) == value


# --- the answer ----------------------------------------------------------------------


def test_the_record_of_a_call(make_gateway):
    wire = make_gateway(lambda request: completion())
    record = wire.gateway.complete(PROMPT, **IDS).record
    assert record.model == "model-value"
    assert (record.prompt_id, record.prompt_version) == ("test.prompt", "1")
    assert (record.prompt_tokens, record.completion_tokens) == (7, 2)
    assert _outcomes(wire.gateway.complete(PROMPT, **IDS)) == ["OK"]


def test_an_answer_without_usage(make_gateway):
    wire = make_gateway(lambda request: completion(usage=False))
    record = wire.gateway.complete(PROMPT, **IDS).record
    assert (record.prompt_tokens, record.completion_tokens) == (None, None)


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (completion(content=None), "EMPTY_RESPONSE"),
        (completion(content=""), "EMPTY_RESPONSE"),
        (completion(content="  \n"), "EMPTY_RESPONSE"),
        (completion(content="half an ans", finish_reason="length"), "TRUNCATED"),
        (completion(content=None, finish_reason="content_filter"), "CONTENT_FILTERED"),
        (httpx2.Response(200, json={"choices": []}), "UNEXPECTED_RESPONSE"),
        (httpx2.Response(200, json={"error": "x"}), "UNEXPECTED_RESPONSE"),
        (httpx2.Response(200, json=[1, 2]), "UNEXPECTED_RESPONSE"),
        (
            httpx2.Response(
                200, text="<html>sign in</html>", headers={"content-type": "text/html"}
            ),
            "UNEXPECTED_RESPONSE",
        ),
        (
            httpx2.Response(200, text="not json", headers={"content-type": "application/json"}),
            "UNEXPECTED_RESPONSE",
        ),
    ],
)
def test_an_answer_that_cannot_be_used_fails_and_is_not_sent_again(make_gateway, response, reason):
    wire = make_gateway(lambda request: response)
    result = wire.gateway.complete(PROMPT, **IDS)
    assert (result.status, result.failure, result.text) == ("FAILED", reason, None)
    assert _outcomes(result) == [reason]
    assert len(wire.requests) == 1 and wire.sleeps == []


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (400, "BAD_REQUEST"),
        (404, "BAD_REQUEST"),
        (409, "BAD_REQUEST"),
        (422, "BAD_REQUEST"),
        (401, "AUTH_ERROR"),
        (403, "AUTH_ERROR"),
    ],
)
def test_a_status_that_is_not_sent_again(make_gateway, status, reason):
    wire = make_gateway(lambda request: _error(status))
    result = wire.gateway.complete(PROMPT, **IDS)
    assert (result.status, result.failure) == ("FAILED", reason)
    assert [a.http_status for a in result.record.attempts] == [status]
    assert len(wire.requests) == 1 and wire.sleeps == []


@pytest.mark.parametrize(
    ("handler", "reason", "status"),
    [
        (lambda request: _error(408), "TIMEOUT", 408),
        (lambda request: _error(429), "RATE_LIMITED", 429),
        (lambda request: _error(500), "SERVER_ERROR", 500),
        (lambda request: _error(503), "SERVER_ERROR", 503),
        (_raise(httpx2.ReadTimeout("slow")), "TIMEOUT", None),
        (_raise(httpx2.ConnectTimeout("slow")), "TIMEOUT", None),
        (_raise(httpx2.ConnectError("no route")), "CONNECTION_ERROR", None),
    ],
)
def test_a_failure_that_may_pass_is_sent_three_times(make_gateway, handler, reason, status):
    assert reason in RETRYABLE
    wire = make_gateway(handler)
    result = wire.gateway.complete(PROMPT, **IDS)
    assert (result.status, result.failure) == ("FAILED", reason)
    assert _outcomes(result) == [reason] * MAX_ATTEMPTS == [reason] * 3
    assert [a.http_status for a in result.record.attempts] == [status] * 3
    assert wire.sleeps == list(BACKOFF_SECONDS) == [1.0, 2.0]
    assert len(wire.requests) == 3


def test_every_attempt_has_new_message_ids(make_gateway):
    wire = make_gateway(lambda request: _error(503))
    result = wire.gateway.complete(PROMPT, **IDS)
    sent = [
        (request.headers["Prompt-Msg-Id"], request.headers["Completion-Msg-Id"])
        for request in wire.requests
    ]
    recorded = [(a.prompt_msg_id, a.completion_msg_id) for a in result.record.attempts]
    assert sent == recorded
    assert len({value for pair in sent for value in pair}) == 6


def test_a_second_attempt_that_passes(make_gateway):
    wire = make_gateway(_in_turn(_error(503), completion()))
    result = wire.gateway.complete(PROMPT, **IDS)
    assert (result.status, result.text) == ("OK", "hello")
    assert _outcomes(result) == ["SERVER_ERROR", "OK"]
    assert wire.sleeps == [1.0]
    assert result.record.prompt_tokens == 7


def test_a_failure_that_cannot_pass_ends_the_attempts(make_gateway):
    wire = make_gateway(_in_turn(httpx2.ConnectError("no route"), _error(401), completion()))
    result = wire.gateway.complete(PROMPT, **IDS)
    assert (result.status, result.failure) == ("FAILED", "AUTH_ERROR")
    assert _outcomes(result) == ["CONNECTION_ERROR", "AUTH_ERROR"]


def test_an_unknown_exception_is_an_internal_error(make_gateway, caplog):
    wire = make_gateway(_raise(ValueError("http://gateway.test " + SECRET_BODY)))
    with caplog.at_level(logging.DEBUG):
        result = wire.gateway.complete(PROMPT, **IDS)
    assert (result.status, result.failure) == ("FAILED", "INTERNAL_ERROR")
    assert _outcomes(result) == ["INTERNAL_ERROR"]
    assert "internal error: ValueError at gateway.py:" in caplog.text
    assert SECRET_BODY not in caplog.text and "gateway.test" not in caplog.text


# --- settings ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "reason", "variables"),
    [
        ({"DS_API_BASE_URL": ""}, "CONFIG_MISSING", ("DS_API_BASE_URL",)),
        ({"DS_CREDENTIAL": " "}, "CONFIG_MISSING", ("DS_CREDENTIAL",)),
        ({"DS_LLM_TIMEOUT_SECONDS": "soon"}, "CONFIG_INVALID", ("DS_LLM_TIMEOUT_SECONDS",)),
    ],
)
def test_without_settings_nothing_is_sent(
    make_gateway, full_env, monkeypatch, change, reason, variables
):
    # the SDK reads these on its own when it is given no address
    monkeypatch.setenv("OPENAI_BASE_URL", "http://elsewhere.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    wire = make_gateway(lambda request: completion(), {**full_env, **change})
    assert wire.gateway.config_failure == reason
    assert wire.gateway.config_variables == variables
    text = wire.gateway.complete(PROMPT, **IDS)
    structured = wire.gateway.complete_structured(PROMPT, Answer, **IDS)
    for result in (text, structured):
        assert (result.status, result.failure) == ("FAILED", reason)
        assert result.record.model is None and result.record.attempts == ()
    assert wire.requests == []


def test_the_timeout_of_the_settings_reaches_the_request(make_gateway, full_env):
    wire = make_gateway(lambda request: completion(), {**full_env, "DS_LLM_TIMEOUT_SECONDS": "7"})
    wire.gateway.complete(PROMPT, **IDS)
    timeout = wire.requests[0].extensions["timeout"]
    assert set(timeout.values()) == {7.0}


def test_the_sdk_does_not_retry_on_its_own(make_gateway):
    wire = make_gateway(lambda request: _error(503))
    wire.gateway.complete(PROMPT, **IDS)
    assert [request.headers["x-stainless-retry-count"] for request in wire.requests] == ["0"] * 3


# --- what is shown -------------------------------------------------------------------


@pytest.mark.parametrize("status", [200, 401, 500])
def test_no_secret_shows_in_the_log_or_in_the_result(make_gateway, caplog, status):
    handler = (lambda request: completion()) if status == 200 else (lambda request: _error(status))
    wire = make_gateway(handler)
    with caplog.at_level(logging.DEBUG):
        result = wire.gateway.complete(PROMPT, **IDS)
    shown = caplog.text + repr(result) + result.model_dump_json() + repr(wire.gateway.__dict__)
    for secret in ("ticket-value", "system-value", "user-value", "gateway.test", SECRET_BODY):
        assert secret not in shown
    assert "You check documents." not in caplog.text + repr(result)
    assert "hello" not in caplog.text


def test_the_log_of_a_call(make_gateway, caplog):
    wire = make_gateway(_in_turn(completion(), _error(403)))
    with caplog.at_level(logging.DEBUG):
        wire.gateway.complete(PROMPT, **IDS)
        wire.gateway.complete(PROMPT, **IDS)
    # the whole log: the SDK and its transport, which log the address, are silent
    assert {record.name for record in caplog.records} == {"app.llm.base"}
    lines = [record.getMessage() for record in caplog.records]
    assert len(lines) == 2
    assert lines[0].startswith("call test.prompt: OK, attempts=1, ")
    assert lines[1].startswith("call test.prompt: FAILED AUTH_ERROR, attempts=1, ")


# --- structured ----------------------------------------------------------------------


def test_a_structured_call_on_the_sdk_path(make_gateway):
    wire = make_gateway(_in_turn(completion("no json here"), completion('{"verdict": "yes"}')))
    result = wire.gateway.complete_structured(PROMPT, Answer, **IDS)
    assert result.status == "OK"
    assert result.value == Answer(verdict="yes")
    assert result.text == '{"verdict": "yes"}'
    assert _outcomes(result) == ["INVALID_JSON", "OK"]
    assert (result.record.prompt_tokens, result.record.completion_tokens) == (14, 4)
    assert wire.sleeps == []  # a wrong form is asked for again at once
    for request in wire.requests:
        last = json.loads(request.content)["messages"][-1]
        assert last == {"role": "system", "content": instruction_for(Answer).content}
    first, second = wire.requests
    assert first.headers["Prompt-Msg-Id"] != second.headers["Prompt-Msg-Id"]
