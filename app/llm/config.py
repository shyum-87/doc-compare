"""Settings of the LLM gateway. Every value comes from an environment variable.

There is no default address: without one nothing is sent anywhere. No value is ever shown,
only the names of the variables that are missing or wrong.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from app.models.llm import LLMFailureReason

REQUIRED_VARIABLES = (
    "DS_API_BASE_URL",
    "DS_CREDENTIAL",
    "DS_SYSTEM_NAME",
    "DS_USER_ID",
    "DS_LLM_MODEL",
)
API_KEY_VARIABLE = "DS_OPENAI_API_KEY"
TIMEOUT_VARIABLE = "DS_LLM_TIMEOUT_SECONDS"
DEFAULT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, repr=False)
class LLMSettings:
    base_url: str
    credential: str
    system_name: str
    user_id: str
    model: str
    api_key: str = "placeholder"
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def __repr__(self) -> str:
        return "LLMSettings(<hidden>)"


@dataclass(frozen=True)
class SettingsResult:
    settings: Optional[LLMSettings]
    failure: Optional[LLMFailureReason] = None  # CONFIG_MISSING or CONFIG_INVALID
    variables: tuple[str, ...] = ()  # names of the variables the failure is about


def load_settings(env: Mapping[str, str]) -> SettingsResult:
    """Read the settings. A problem is returned, not raised."""
    values = {name: (env.get(name) or "").strip() for name in REQUIRED_VARIABLES}
    missing = tuple(name for name, value in values.items() if not value)
    if missing:
        return SettingsResult(settings=None, failure="CONFIG_MISSING", variables=missing)
    if not values["DS_API_BASE_URL"].lower().startswith(("http://", "https://")):
        return SettingsResult(
            settings=None, failure="CONFIG_INVALID", variables=("DS_API_BASE_URL",)
        )

    timeout = DEFAULT_TIMEOUT_SECONDS
    written = (env.get(TIMEOUT_VARIABLE) or "").strip()
    if written:
        try:
            timeout = float(written)
        except ValueError:
            timeout = math.nan
        if not math.isfinite(timeout) or timeout <= 0:
            return SettingsResult(
                settings=None, failure="CONFIG_INVALID", variables=(TIMEOUT_VARIABLE,)
            )

    return SettingsResult(
        settings=LLMSettings(
            base_url=values["DS_API_BASE_URL"],
            credential=values["DS_CREDENTIAL"],
            system_name=values["DS_SYSTEM_NAME"],
            user_id=values["DS_USER_ID"],
            model=values["DS_LLM_MODEL"],
            api_key=(env.get(API_KEY_VARIABLE) or "").strip() or "placeholder",
            timeout_seconds=timeout,
        )
    )


def read_env_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines. Blank lines, # comments and lines without a name are skipped."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not name:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values
