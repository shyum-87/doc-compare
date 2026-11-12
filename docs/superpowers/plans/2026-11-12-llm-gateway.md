# 단위 ② 구현 계획: LLM 게이트웨이

**목표:** 사내 OpenAI 호환 LLM을 호출하는 게이트웨이를 `app/llm/`에 만든다. 호출은 예외 대신 결과 객체를 돌려준다.

**구조:** 공통 흐름(`base.py`)이 기록, 로그, 구조화 응답 검증을 맡고, 요청 한 번을 보내는 일만 하위 클래스(`gateway.py`의 SDK 호출, `fake.py`의 가짜)에 맡긴다. 결과 모델은 `app/models/llm.py`에 둔다.

**기술:** Python 3.10, Pydantic 2, `openai` 3.49.0(전송 계층은 `httpx2`), pytest, ruff.

설계는 [2026-11-12-llm-gateway-design.md](../specs/2026-11-12-llm-gateway-design.md)에 있다. 이 계획은 이 세션에서 순서대로 실행한다. 작업마다 테스트를 먼저 쓰고, 실패를 확인하고, 구현하고, 통과를 확인한 뒤 커밋한다.

공통 명령:

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format .
```

## SDK에서 확인한 동작

구현 전에 `httpx2.MockTransport`로 확인했다. 분류 규칙은 이 동작에 맞춘다.

| 응답 | SDK의 동작 |
|---|---|
| 200, 정상 본문 | `ChatCompletion`을 돌려준다. `usage`가 있으면 채워진다 |
| 200, HTML 본문 | 예외 없이 `str`을 돌려준다 |
| 200, `choices`가 없거나 빈 JSON | 예외 없이 `choices`가 `None` 또는 `[]`인 객체를 돌려준다 |
| 200, JSON으로 읽히지 않는 본문 | `json.JSONDecodeError` |
| 4xx, 5xx | `APIStatusError`와 그 하위 클래스. `status_code`가 있다 |
| 연결 실패 | `APIConnectionError` |
| 시간 초과 | `APITimeoutError`(`APIConnectionError`의 하위 클래스) |

## 작업 1. 의존성

**파일:** `pyproject.toml`, `constraints.txt`

- [ ] `pyproject.toml`의 `dependencies`에 `"openai>=3.49,<4"`를 더한다.
- [ ] `constraints.txt`에 `openai==3.49.0`, `httpx2==2.14.0`, `httpcore2==2.14.0`, `jiter==0.18.0`, `anyio==4.16.0`, `h11==0.16.0`, `idna==3.20`, `sniffio==1.3.1`, `truststore==0.10.5`를 더하고, 머리말에 `httpx2`, `httpcore2`, `jiter`를 최신이 아닌 버전으로 고정한 이유를 적는다.
- [ ] `pip install -e ".[dev]" -c constraints.txt`가 끝나고 기존 테스트가 통과하는지 확인한다.
- [ ] 커밋: `build: add the openai SDK and pin its dependencies`

## 작업 2. 결과 모델

**파일:** `app/models/llm.py`, `tests/models/test_llm.py`

```python
Role = Literal["system", "user", "assistant"]
LLMStatus = Literal["OK", "FAILED"]
LLMFailureReason = Literal[...]          # 설계 5.1절의 15개
RETRYABLE: frozenset[str]                # TIMEOUT, CONNECTION_ERROR, RATE_LIMITED, SERVER_ERROR
FORMAT_FAILURES: frozenset[str]          # INVALID_JSON, SCHEMA_MISMATCH

class Message(FrozenModel): role: Role; content: str
class Attempt(FrozenModel):
    prompt_msg_id: str; completion_msg_id: str
    outcome: Union[Literal["OK"], LLMFailureReason]
    http_status: Optional[int] = None; duration_ms: int
class CallRecord(FrozenModel):
    model: Optional[str]; prompt_id: str; prompt_version: str; gateway_version: str
    attempts: tuple[Attempt, ...]; duration_ms: int
    prompt_tokens: Optional[int] = None; completion_tokens: Optional[int] = None
class TextResult(FrozenModel): status; text: Optional[str]; failure: Optional[LLMFailureReason]; record
class StructuredResult(FrozenModel, Generic[T]): status; value: Optional[T]; text; failure; record
```

테스트:

- [ ] `OK`인데 `text`가 없거나 `failure`가 있으면 만들어지지 않는다. `FAILED`인데 `text`나 `value`가 있거나 `failure`가 없어도 만들어지지 않는다.
- [ ] 구조화 결과가 `OK`이면 `value`가 있어야 한다.
- [ ] 모르는 역할과 모르는 실패 사유는 거부된다. 결과를 JSON으로 덤프했다가 다시 읽으면 같다.
- [ ] 커밋: `feat: add the result models of an LLM call`

## 작업 3. 설정

**파일:** `app/llm/__init__.py`, `app/llm/config.py`, `tests/llm/test_config.py`

```python
@dataclass(frozen=True, repr=False)
class LLMSettings:
    base_url: str; credential: str; system_name: str; user_id: str; model: str
    api_key: str = "placeholder"; timeout_seconds: float = 60.0
    def __repr__(self) -> str: return "LLMSettings(<hidden>)"

@dataclass(frozen=True)
class SettingsResult:
    settings: Optional[LLMSettings]
    failure: Optional[LLMFailureReason]   # CONFIG_MISSING 또는 CONFIG_INVALID
    variables: tuple[str, ...]            # 문제가 된 환경변수의 이름

def load_settings(env: Mapping[str, str]) -> SettingsResult
def read_env_file(path: Path) -> dict[str, str]
```

테스트:

- [ ] 값이 모두 있으면 설정이 만들어진다. 앞뒤 공백은 잘린다.
- [ ] 필수 값이 없거나 공백뿐이면 `CONFIG_MISSING`이고 이름이 정해진 순서로 모두 나온다.
- [ ] `DS_OPENAI_API_KEY`가 없으면 `placeholder`, 시간 제한이 없으면 60이다.
- [ ] 시간 제한이 숫자가 아니거나 0 이하이거나 `nan`, `inf`이면 `CONFIG_INVALID`다.
- [ ] `repr`과 `str`에 어떤 값도 나오지 않는다.
- [ ] `read_env_file`: `KEY=VALUE`, 빈 줄, `#` 주석, 값의 양끝 따옴표, `=`가 든 값, BOM을 읽는다. `=`가 없는 줄은 건너뛴다.
- [ ] 커밋: `feat: read the LLM settings from the environment`

## 작업 4. 구조화 응답 읽기

**파일:** `app/llm/structured.py`, `tests/llm/test_structured.py`

```python
def instruction_for(schema: type[BaseModel]) -> Message      # role="system"
def parse_structured(text: str, schema: type[T]) -> Union[T, LLMFailureReason]
```

테스트:

- [ ] 지시 메시지에 스키마의 JSON Schema가 들어 있고, 같은 스키마에는 늘 같은 글이 나온다.
- [ ] 객체 JSON은 스키마의 인스턴스로 읽힌다. 글 전체가 ```` ```json ```` 또는 ```` ``` ```` 울타리 하나로 싸여 있어도 읽힌다.
- [ ] JSON 앞뒤에 다른 글이 있으면, 최상위가 배열·문자열·숫자이면, 울타리가 둘이면 `INVALID_JSON`이다.
- [ ] 필드가 빠졌거나 타입이 다르면 `SCHEMA_MISMATCH`다.
- [ ] 커밋: `feat: read a structured answer against a schema`

## 작업 5. 공통 흐름과 가짜 LLM

**파일:** `app/llm/base.py`, `app/llm/fake.py`, `tests/llm/test_fake.py`

```python
GATEWAY_VERSION = "0.1.0"

@dataclass(frozen=True)
class Outcome:                      # 요청 한 번(전송 재시도 포함)의 결과
    text: Optional[str]; failure: Optional[LLMFailureReason]
    attempts: tuple[Attempt, ...]
    prompt_tokens: Optional[int] = None; completion_tokens: Optional[int] = None

class BaseLLM:
    model: Optional[str]
    def _request(self, messages: Sequence[Message], max_tokens: Optional[int]) -> Outcome  # 하위 클래스
    def complete(self, messages, *, prompt_id, prompt_version, max_tokens=None) -> TextResult
    def complete_structured(self, messages, schema, *, prompt_id, prompt_version, max_tokens=None) -> StructuredResult[T]

class FakeLLM(BaseLLM):
    def __init__(self, answers: Sequence[str], model: str = "fake-model")
    calls: list[tuple[Message, ...]]
```

`FakeLLM`의 `answers`에서 실패 사유 코드와 같은 글은 그 사유의 실패로 돌려준다.

테스트:

- [ ] 텍스트 호출이 응답 글과 기록(모델, 프롬프트 ID와 버전, 게이트웨이 버전, 시도 하나)을 돌려준다.
- [ ] 실패 사유를 정해 두면 `FAILED`와 그 사유가 나오고 `text`는 없다.
- [ ] 구조화 호출이 지시 메시지를 맨 뒤에 붙여 보내고 `value`와 `text`를 돌려준다.
- [ ] 형식이 틀린 응답 뒤에 맞는 응답이 오면 `OK`이고 시도가 둘이다. 두 번 다 틀리면 `FAILED`이고 세 번째 호출은 없다.
- [ ] 형식 실패가 아닌 실패(`AUTH_ERROR`)는 다시 호출하지 않는다.
- [ ] 응답이 다 떨어지면, `_request`가 예외를 내면, `INTERNAL_ERROR`다. 예외는 밖으로 나오지 않는다.
- [ ] 로그 한 줄에 프롬프트 ID, 상태, 사유, 시도 횟수가 있고 프롬프트와 응답 글은 없다.
- [ ] 커밋: `feat: add the shared call flow and a fake LLM`

## 작업 6. 게이트웨이

**파일:** `app/llm/gateway.py`, `tests/llm/test_gateway.py`, `tests/llm/conftest.py`

```python
class LLMGateway(BaseLLM):
    def __init__(self, loaded: SettingsResult, *, http_client=None,
                 sleep=time.sleep, clock=time.monotonic, new_id=lambda: str(uuid.uuid4()))
    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None, **kwargs) -> LLMGateway
    config_failure: Optional[LLMFailureReason]; config_variables: tuple[str, ...]

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)
```

분류: `APITimeoutError` → `TIMEOUT`, 그 밖의 `APIConnectionError` → `CONNECTION_ERROR`, `APIStatusError`는 상태 코드로(408 `TIMEOUT`, 429 `RATE_LIMITED`, 5xx `SERVER_ERROR`, 401·403 `AUTH_ERROR`, 나머지 `BAD_REQUEST`), `json.JSONDecodeError`와 그 밖의 `OpenAIError`, `choices`가 없는 응답 → `UNEXPECTED_RESPONSE`, `finish_reason`이 `length` → `TRUNCATED`, `content_filter` → `CONTENT_FILTERED`, 글이 없거나 공백 → `EMPTY_RESPONSE`.

테스트(`conftest.py`의 `make_gateway(handler)`가 `MockTransport`를 끼운 게이트웨이와 기다린 시간 목록을 준다):

- [ ] 요청의 주소가 `<base>/chat/completions`이고 본문에 `model`, `messages`, `temperature: 0`이 있다. `max_tokens`는 줄 때만 있다.
- [ ] 고정 헤더 4개의 값이 설정과 같고 `User-Type`은 `AD_ID`다.
- [ ] `Prompt-Msg-Id`와 `Completion-Msg-Id`가 UUID이고, 서로 다르고, 호출마다 다르고, 기록의 값과 같다.
- [ ] 정상 응답의 토큰 사용량이 기록에 들어간다. `usage`가 없으면 `None`이다.
- [ ] 위 분류표의 경우마다 사유와 `http_status`가 맞다.
- [ ] 재시도하는 사유는 세 번 시도하고 1초, 2초를 기다린다. 시도마다 UUID가 다르다. 두 번째에 성공하면 `OK`이고 시도가 둘이다.
- [ ] 재시도하지 않는 사유는 한 번만 보낸다.
- [ ] 설정이 없으면 `CONFIG_MISSING`이고 전송 계층이 한 번도 불리지 않는다. `OPENAI_BASE_URL`이 환경에 있어도 같다.
- [ ] 전송 계층이 모르는 예외를 내면 `INTERNAL_ERROR`다.
- [ ] 오류 응답의 본문, 주소, 인증값이 로그와 결과의 `repr`에 없다.
- [ ] 구조화 호출이 실제 SDK 경로로 동작한다.
- [ ] 커밋: `feat: call the in-house LLM through the openai SDK`

## 작업 7. 연결 확인 명령

**파일:** `app/llm/__main__.py`, `tests/llm/test_cli.py`

```python
def main(argv=None, *, env=None, gateway_factory=LLMGateway.from_env) -> int
```

테스트:

- [ ] 두 호출이 모두 `OK`이면 종료 코드 0이고 화면에 `text call: OK`와 `structured call: OK` 줄이 나온다.
- [ ] 하나라도 실패하면 2이고 사유와 `http` 상태가 나온다.
- [ ] 설정이 없으면 2이고 빠진 변수의 이름이 나온다. 값은 나오지 않는다.
- [ ] `--env-file`의 값이 쓰이고, 실제 환경변수가 파일보다 우선한다. 파일을 읽지 못하면 2다.
- [ ] 화면에 응답 글, 주소, 인증값이 없다.
- [ ] 커밋: `feat: add the connection check command`

## 작업 8. 문서

**파일:** `config/example.env`, `CLAUDE.md`, `README.md`, `docs/DECISIONS.md`, `docs/INHOUSE_CHECK.md`, `docs/INHOUSE_GUIDE.md`

- [ ] `example.env`에 `DS_LLM_TIMEOUT_SECONDS`를 더한다.
- [ ] `DECISIONS.md`에 D-015(OpenAI SDK와 단위 ②의 범위), D-016(호출은 결과 객체를 돌려주고 `FAILED`는 UNKNOWN으로 이어진다)을 더한다.
- [ ] `CLAUDE.md`의 현재 상태, 명령어, 코드 구조를 고친다. `README.md`의 현재 단계를 고친다.
- [ ] 사내 문서 두 개에 연결 확인 절차와 가지고 나올 것을 더한다.
- [ ] 전체 테스트와 ruff를 돌린 뒤 커밋: `docs: describe unit 2 and its in-house check`
