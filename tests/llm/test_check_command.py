"""The connection check command."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx2
import pytest
from conftest import FULL_ENV, completion

from app.llm.__main__ import main
from app.llm.gateway import LLMGateway

ROOT = Path(__file__).resolve().parents[2]
GOOD = '{"answer": "OK"}'


def _factory(handler, seen=None):
    def factory(env):
        if seen is not None:
            seen.append(dict(env))
        return LLMGateway.from_env(
            env,
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
            sleep=lambda seconds: None,
        )

    return factory


def _in_turn(*responses):
    left = list(responses)
    return lambda request: left.pop(0)


def _lines(caplog) -> list[str]:
    return [
        f"{record.levelname} {record.name}: {record.getMessage()}"
        for record in caplog.records
        if record.name == "app.llm"
    ]


def _run(caplog, handler, env=FULL_ENV, argv=("check",), seen=None) -> int:
    with caplog.at_level(logging.DEBUG):
        return main(list(argv), env=env, gateway_factory=_factory(handler, seen))


def test_both_calls_pass(caplog):
    code = _run(caplog, _in_turn(completion("OK"), completion(GOOD)))
    assert code == 0
    first, second = _lines(caplog)
    assert first.startswith("INFO app.llm: text call: OK, attempts=1, ")
    assert first.endswith(" ms, usage=yes")
    assert second.startswith("INFO app.llm: structured call: OK, attempts=1, ")


def test_an_answer_without_usage_says_so(caplog):
    handler = _in_turn(completion("OK", usage=False), completion(GOOD, usage=False))
    assert _run(caplog, handler) == 0
    assert all(line.endswith("usage=no") for line in _lines(caplog))


def test_a_failed_text_call(caplog):
    error = httpx2.Response(401, json={"error": {"message": "body-of-the-error"}})
    code = _run(caplog, _in_turn(error, completion(GOOD)))
    assert code == 2
    first, second = _lines(caplog)  # the structured call is still made
    assert first.startswith("ERROR app.llm: text call: FAILED AUTH_ERROR (http 401), attempts=1, ")
    assert second.startswith("INFO app.llm: structured call: OK")


def test_a_failed_structured_call(caplog):
    code = _run(caplog, _in_turn(completion("OK"), completion("OK"), completion("OK")))
    assert code == 2
    assert _lines(caplog)[1].startswith(
        "ERROR app.llm: structured call: FAILED INVALID_JSON, attempts=2, "
    )


def test_missing_settings_are_named_and_nothing_is_sent(caplog):
    sent = []
    env = {"DS_SYSTEM_NAME": "system-value", "DS_LLM_MODEL": "model-value"}
    code = _run(caplog, lambda request: sent.append(request), env=env)
    assert code == 2
    assert _lines(caplog) == [
        "ERROR app.llm: configuration: CONFIG_MISSING: DS_API_BASE_URL, DS_CREDENTIAL, DS_USER_ID"
    ]
    assert sent == []
    assert "system-value" not in caplog.text and "model-value" not in caplog.text


def test_an_env_file_fills_in_and_the_environment_wins(caplog, tmp_path):
    path = tmp_path / ".env"
    lines = [f"{name}={value}" for name, value in FULL_ENV.items()]
    path.write_text("\n".join(lines).replace("model-value", "model-of-the-file"), "utf-8")
    seen = []
    handler = _in_turn(completion("OK"), completion(GOOD))
    env = {"DS_USER_ID": "user-of-the-environment"}
    code = _run(caplog, handler, env=env, argv=("check", "--env-file", str(path)), seen=seen)
    assert code == 0
    assert seen[0]["DS_LLM_MODEL"] == "model-of-the-file"
    assert seen[0]["DS_USER_ID"] == "user-of-the-environment"


@pytest.mark.parametrize("content", [None, b"\xff\xfe not utf-8 \xff"])
def test_an_env_file_that_cannot_be_read(caplog, tmp_path, content):
    path = tmp_path / "secret-name.env"
    if content is not None:
        path.write_bytes(content)
    code = _run(caplog, lambda request: completion(), argv=("check", "--env-file", str(path)))
    assert code == 2
    (line,) = _lines(caplog)
    assert line.startswith("ERROR app.llm: cannot read the env file: ")
    assert "secret-name" not in caplog.text


def test_an_error_of_the_factory_is_exit_code_2(caplog):
    def factory(env):
        raise RuntimeError("ticket-value")

    with caplog.at_level(logging.DEBUG):
        assert main(["check"], env=FULL_ENV, gateway_factory=factory) == 2
    assert _lines(caplog) == ["ERROR app.llm: internal error: RuntimeError"]


def test_nothing_of_the_settings_or_the_answers_is_shown(caplog):
    _run(caplog, _in_turn(completion("the answer text"), completion(GOOD)))
    for hidden in (*FULL_ENV.values(), "gateway.test", "the answer text", GOOD, "Reply with"):
        assert hidden not in caplog.text


def test_a_command_is_required():
    with pytest.raises(SystemExit) as raised:
        main([], env=FULL_ENV)
    assert raised.value.code == 2


def test_run_as_a_module_without_settings():
    env = {name: value for name, value in os.environ.items() if not name.startswith("DS_")}
    command = [sys.executable, "-m", "app.llm", "check"]
    done = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, check=False)
    assert done.returncode == 2
    assert done.stdout == b""
    assert done.stderr.decode("ascii").splitlines() == [
        "ERROR app.llm: configuration: CONFIG_MISSING: "
        "DS_API_BASE_URL, DS_CREDENTIAL, DS_SYSTEM_NAME, DS_USER_ID, DS_LLM_MODEL"
    ]
