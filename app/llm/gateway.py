"""The in-house OpenAI-compatible LLM, called through the openai SDK.

The address comes from the settings and from nowhere else: without settings nothing is
sent. Every attempt carries new Prompt-Msg-Id and Completion-Msg-Id values, so the retry
of the SDK is off and the retry is done here.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Callable, Mapping, Optional

import openai

from app.llm.base import BaseLLM, Outcome, where
from app.llm.config import LLMSettings, SettingsResult, load_settings
from app.models.llm import RETRYABLE, Attempt, LLMFailureReason, Message

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)  # before the second and the third attempt
USER_TYPE = "AD_ID"

logger = logging.getLogger(__name__)

# httpx2 logs the full address of every request at INFO, and the SDK logs requests and
# answers at DEBUG. Neither may reach a log, whatever level the program sets.
SILENCED_LOGGERS = ("httpx2", "httpcore2", "openai")
for _name in SILENCED_LOGGERS:
    logging.getLogger(_name).setLevel(logging.CRITICAL + 1)


def _new_id() -> str:
    return str(uuid.uuid4())


def _reason_of_status(status: int) -> LLMFailureReason:
    if status == 408:
        return "TIMEOUT"
    if status == 429:
        return "RATE_LIMITED"
    if status >= 500:
        return "SERVER_ERROR"
    if status in (401, 403):
        return "AUTH_ERROR"
    return "BAD_REQUEST"


def _tokens(usage: Any, name: str) -> Optional[int]:
    value = getattr(usage, name, None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class LLMGateway(BaseLLM):
    def __init__(
        self,
        loaded: SettingsResult,
        *,
        http_client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        new_id: Callable[[], str] = _new_id,
    ) -> None:
        self.config_failure: Optional[LLMFailureReason] = loaded.failure
        self.config_variables: tuple[str, ...] = loaded.variables
        self._settings: Optional[LLMSettings] = loaded.settings
        if self._settings is None and self.config_failure is None:
            self.config_failure = "CONFIG_MISSING"
        self.model = self._settings.model if self._settings else None
        self._http_client = http_client
        self._sleep = sleep
        self._clock = clock
        self._new_id = new_id
        self._client: Optional[openai.OpenAI] = None

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None, **kwargs: Any) -> LLMGateway:
        """Never raises: with bad settings every call of the gateway comes back FAILED."""
        return cls(load_settings(os.environ if env is None else env), **kwargs)

    def _sdk(self, settings: LLMSettings) -> openai.OpenAI:
        if self._client is None:
            self._client = openai.OpenAI(
                api_key=settings.api_key,
                base_url=settings.base_url,  # always given: the SDK never picks an address
                timeout=settings.timeout_seconds,
                max_retries=0,  # the SDK would send the same message IDs again
                default_headers={
                    "x-dep-ticket": settings.credential,
                    "Send-System-Name": settings.system_name,
                    "User-Id": settings.user_id,
                    "User-Type": USER_TYPE,
                },
                http_client=self._http_client,
            )
        return self._client

    def _request(self, messages: tuple[Message, ...], max_tokens: Optional[int]) -> Outcome:
        settings = self._settings
        if settings is None:
            return Outcome(text=None, failure=self.config_failure)
        client = self._sdk(settings)
        request: dict[str, Any] = {
            "model": settings.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": 0,
        }
        if max_tokens is not None:
            request["max_tokens"] = max_tokens

        attempts: list[Attempt] = []
        for number in range(MAX_ATTEMPTS):
            if number:
                self._sleep(BACKOFF_SECONDS[number - 1])
            attempt, text, usage = self._send(client, request)
            attempts.append(attempt)
            if attempt.outcome == "OK":
                return Outcome(
                    text=text,
                    failure=None,
                    attempts=tuple(attempts),
                    prompt_tokens=_tokens(usage, "prompt_tokens"),
                    completion_tokens=_tokens(usage, "completion_tokens"),
                )
            if attempt.outcome not in RETRYABLE:
                break
        return Outcome(text=None, failure=attempts[-1].outcome, attempts=tuple(attempts))

    def _send(
        self, client: openai.OpenAI, request: dict[str, Any]
    ) -> tuple[Attempt, Optional[str], Any]:
        """One request on the wire, classified. The answer comes back only with 'OK'."""
        prompt_msg_id, completion_msg_id = self._new_id(), self._new_id()
        started = self._clock()
        status: Optional[int] = None
        text: Optional[str] = None
        usage: Any = None
        outcome: str
        try:
            response = client.chat.completions.create(
                **request,
                extra_headers={
                    "Prompt-Msg-Id": prompt_msg_id,
                    "Completion-Msg-Id": completion_msg_id,
                },
            )
            outcome, text = _read(response)
            usage = getattr(response, "usage", None)
        except openai.APITimeoutError:  # before APIConnectionError: it is a subclass
            outcome = "TIMEOUT"
        except openai.APIConnectionError:
            outcome = "CONNECTION_ERROR"
        except openai.APIStatusError as error:
            status = error.status_code
            outcome = _reason_of_status(status)
        except (openai.OpenAIError, json.JSONDecodeError):
            outcome = "UNEXPECTED_RESPONSE"  # a 200 whose body is not what the SDK reads
        except Exception as error:  # fail closed
            # The message may hold the address or the body of the answer: the type only.
            logger.error("internal error: %s at %s", type(error).__name__, where(error))
            outcome = "INTERNAL_ERROR"
        attempt = Attempt(
            prompt_msg_id=prompt_msg_id,
            completion_msg_id=completion_msg_id,
            outcome=outcome,
            http_status=status,
            duration_ms=max(0, round((self._clock() - started) * 1000)),
        )
        return attempt, (text if outcome == "OK" else None), usage


def _read(response: Any) -> tuple[str, Optional[str]]:
    """The outcome and the text of a response that came back without an exception."""
    choices = getattr(response, "choices", None)  # an HTML page comes back as a plain str
    if not isinstance(choices, list) or not choices:
        return "UNEXPECTED_RESPONSE", None
    choice = choices[0]
    finish_reason = getattr(choice, "finish_reason", None)
    if finish_reason == "length":
        return "TRUNCATED", None  # a part of an answer is not judged
    if finish_reason == "content_filter":
        return "CONTENT_FILTERED", None
    content = getattr(getattr(choice, "message", None), "content", None)
    if not isinstance(content, str) or not content.strip():
        return "EMPTY_RESPONSE", None
    return "OK", content
