"""Settings of the LLM gateway, read from environment variables."""

from __future__ import annotations

import pytest

from app.llm.config import REQUIRED_VARIABLES, load_settings, read_env_file

FULL = {
    "DS_API_BASE_URL": "http://gateway.test/v1",
    "DS_CREDENTIAL": "ticket-value",
    "DS_SYSTEM_NAME": "system-value",
    "DS_USER_ID": "user-value",
    "DS_LLM_MODEL": "model-value",
}


def test_all_values_make_settings():
    loaded = load_settings({**FULL, "DS_OPENAI_API_KEY": "key-value"})
    assert loaded.failure is None and loaded.variables == ()
    settings = loaded.settings
    assert settings.base_url == "http://gateway.test/v1"
    assert settings.credential == "ticket-value"
    assert settings.system_name == "system-value"
    assert settings.user_id == "user-value"
    assert settings.model == "model-value"
    assert settings.api_key == "key-value"


def test_defaults():
    settings = load_settings(FULL).settings
    assert settings.api_key == "placeholder"
    assert settings.timeout_seconds == 60.0


def test_values_are_stripped():
    settings = load_settings({**FULL, "DS_LLM_MODEL": "  model-value \n"}).settings
    assert settings.model == "model-value"


def test_the_required_variables():
    assert REQUIRED_VARIABLES == tuple(FULL)


@pytest.mark.parametrize("name", list(FULL))
@pytest.mark.parametrize("value", [None, "", "   "])
def test_a_missing_or_blank_value_is_missing(name, value):
    env = {key: text for key, text in FULL.items() if key != name}
    if value is not None:
        env[name] = value
    loaded = load_settings(env)
    assert loaded.settings is None
    assert loaded.failure == "CONFIG_MISSING"
    assert loaded.variables == (name,)


def test_every_missing_name_is_reported_in_order():
    loaded = load_settings({"DS_SYSTEM_NAME": "system-value"})
    assert loaded.failure == "CONFIG_MISSING"
    assert loaded.variables == (
        "DS_API_BASE_URL",
        "DS_CREDENTIAL",
        "DS_USER_ID",
        "DS_LLM_MODEL",
    )


def test_a_timeout_can_be_set():
    assert (
        load_settings({**FULL, "DS_LLM_TIMEOUT_SECONDS": "12.5"}).settings.timeout_seconds == 12.5
    )


@pytest.mark.parametrize("value", ["abc", "0", "-1", "nan", "inf", "1e999"])
def test_a_bad_timeout_is_invalid(value):
    loaded = load_settings({**FULL, "DS_LLM_TIMEOUT_SECONDS": value})
    assert loaded.settings is None
    assert loaded.failure == "CONFIG_INVALID"
    assert loaded.variables == ("DS_LLM_TIMEOUT_SECONDS",)


@pytest.mark.parametrize("value", ["gateway.test/v1", "ftp://gateway.test", "//gateway.test"])
def test_an_address_that_is_not_http_is_invalid(value):
    loaded = load_settings({**FULL, "DS_API_BASE_URL": value})
    assert loaded.settings is None
    assert loaded.failure == "CONFIG_INVALID"
    assert loaded.variables == ("DS_API_BASE_URL",)


def test_missing_comes_before_invalid():
    loaded = load_settings({"DS_LLM_TIMEOUT_SECONDS": "abc"})
    assert loaded.failure == "CONFIG_MISSING"


def test_no_value_shows_in_repr_or_str():
    loaded = load_settings({**FULL, "DS_OPENAI_API_KEY": "key-value"})
    shown = repr(loaded) + str(loaded) + repr(loaded.settings) + str(loaded.settings)
    for value in (*FULL.values(), "key-value", "gateway.test"):
        assert value not in shown


def test_an_env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes(
        b"\xef\xbb\xbf# a comment\r\n"
        b"\r\n"
        b"DS_LLM_MODEL=model-value\r\n"
        b"  DS_USER_ID = user-value  \n"
        b'DS_CREDENTIAL="quoted=value"\n'
        b"DS_SYSTEM_NAME='single'\n"
        b"a line without the sign\n"
        b"=no name\n"
        b"EMPTY=\n"
    )
    assert read_env_file(path) == {
        "DS_LLM_MODEL": "model-value",
        "DS_USER_ID": "user-value",
        "DS_CREDENTIAL": "quoted=value",
        "DS_SYSTEM_NAME": "single",
        "EMPTY": "",
    }


def test_an_env_file_that_cannot_be_read(tmp_path):
    with pytest.raises(OSError):
        read_env_file(tmp_path / "missing.env")
