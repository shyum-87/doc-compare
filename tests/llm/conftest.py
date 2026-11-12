"""A gateway whose requests end in a mock transport: the real SDK path, no network.

Every value here is made up. The host `gateway.test` does not exist (RFC 6761).
"""

from __future__ import annotations

from typing import Callable, Optional

import httpx2
import pytest

from app.llm.gateway import LLMGateway

FULL_ENV = {
    "DS_API_BASE_URL": "http://gateway.test/v1",
    "DS_CREDENTIAL": "ticket-value",
    "DS_SYSTEM_NAME": "system-value",
    "DS_USER_ID": "user-value",
    "DS_LLM_MODEL": "model-value",
}


def completion(
    content: Optional[str] = "hello", finish_reason: str = "stop", usage: bool = True
) -> httpx2.Response:
    body = {
        "id": "x",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content},
            }
        ],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}
    return httpx2.Response(200, json=body)


class Wire:
    """What the gateway did: the requests it sent and how long it waited between them."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.sleeps: list[float] = []
        self.gateway: LLMGateway


@pytest.fixture
def full_env() -> dict[str, str]:
    return dict(FULL_ENV)


@pytest.fixture
def make_gateway() -> Callable[..., Wire]:
    def make(handler: Callable[[httpx2.Request], httpx2.Response], env=None) -> Wire:
        wire = Wire()

        def transport(request: httpx2.Request) -> httpx2.Response:
            wire.requests.append(request)
            return handler(request)

        wire.gateway = LLMGateway.from_env(
            FULL_ENV if env is None else env,
            http_client=httpx2.Client(transport=httpx2.MockTransport(transport)),
            sleep=wire.sleeps.append,
        )
        return wire

    return make
