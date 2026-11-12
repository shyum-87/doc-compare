# 단위 ② 설계: LLM 게이트웨이

- 작성일: 2026-11-12
- 상태: 승인됨 (2026-11-12). 구현 계획은 [2026-11-12-llm-gateway.md](../plans/2026-11-12-llm-gateway.md)
- 관련 문서: [DECISIONS.md](../../DECISIONS.md), [SYSTEM_DESIGN.md](../../SYSTEM_DESIGN.md) §6

## 1. 목적과 위치

사내 OpenAI 호환 LLM을 호출하는 유일한 통로다. 체크리스트 추출(단위 ③)과 판정(단위 ④)은 이 게이트웨이만 부르고 SDK를 직접 쓰지 않는다. 단위 ①의 코드와 결과에는 의존하지 않는다.

개발 환경에서는 사내 LLM에 접근할 수 없다(D-002). 그래서 이 단위는 네트워크 없이 테스트할 수 있어야 하고, 실제 연동은 사내에서 연결 확인 명령으로 처음 확인한다.

## 2. 범위

### 만드는 것

- 설정 읽기: 환경변수에서 주소, 인증값, 식별값, 모델 이름을 읽는다.
- 텍스트 호출: 메시지 목록을 보내고 응답 글을 받는다.
- 구조화 호출: JSON 응답을 받아 호출자가 준 Pydantic 스키마로 검증한다.
- 재시도와 실패 분류: 호출은 예외를 올리지 않고 결과 객체를 돌려준다.
- 호출 기록: 모델, 프롬프트 ID와 버전, 호출별 UUID, 시도 횟수, 소요 시간, 토큰 사용량.
- 테스트용 가짜 LLM.
- 명령줄 `python -m app.llm check`: 사내 연결 확인.

### 만들지 않는 것

이미지 입력, 스트리밍, 여러 모델 라우팅, LangChain 연동, 응답 캐시, 프롬프트 저장소. 프롬프트 글은 그것을 쓰는 단위(③, ④)가 갖는다.

### 완료 기준

- 테스트와 ruff가 통과한다. 테스트는 네트워크를 쓰지 않는다.
- 호출하는 동안 일어난 어떤 일에도 호출 함수에서 예외가 나오지 않는다. 호출자의 실수(메시지가 없다, 프롬프트 ID가 비었다, 스키마가 Pydantic 모델이 아니다)만 보내기 전에 `ValueError`나 `TypeError`로 올린다.
- 로그와 결과 객체의 `repr`에 주소, 인증값, 사용자 ID, 프롬프트, 응답 본문이 나오지 않는다.

## 3. 설정

| 환경변수 | 필수 | 쓰는 곳 |
|---|---|---|
| `DS_API_BASE_URL` | 예 | 호출 주소 |
| `DS_CREDENTIAL` | 예 | 헤더 `x-dep-ticket` |
| `DS_SYSTEM_NAME` | 예 | 헤더 `Send-System-Name` |
| `DS_USER_ID` | 예 | 헤더 `User-Id` |
| `DS_LLM_MODEL` | 예 | 요청의 `model` |
| `DS_OPENAI_API_KEY` | 아니오 | SDK의 `api_key`. 없으면 `placeholder` |
| `DS_LLM_TIMEOUT_SECONDS` | 아니오 | 시도 한 번의 시간 제한. 없으면 60 |

- 헤더 `User-Type`의 값은 `AD_ID`로 고정한다.
- 값이 없거나 공백뿐이면 없는 것으로 본다. 필수 값이 없으면 `CONFIG_MISSING`이다. 주소가 `http://`나 `https://`로 시작하지 않거나 시간 제한이 양수가 아니면 `CONFIG_INVALID`다.
- **기본 주소는 없다.** 주소가 없으면 어디로도 보내지 않는다. SDK가 자기 환경변수(`OPENAI_BASE_URL` 등)로 주소를 정하는 일이 없도록 주소를 항상 직접 넘긴다.
- 설정이 잘못되어도 게이트웨이를 만들 때 예외가 나지 않는다. 그 게이트웨이의 모든 호출이 `FAILED`를 돌려준다.
- 설정 객체의 `repr`은 값을 보여 주지 않는다. 빠진 변수는 이름만 알려 준다.
- 명령줄은 `--env-file`로 `KEY=VALUE` 꼴의 파일을 읽을 수 있다. 실제 환경변수가 파일보다 우선한다. 그 파일은 `.gitignore`에 걸리는 이름(`.env`)으로 저장소 밖이나 루트에 둔다.

## 4. 호출

```python
gateway = LLMGateway.from_env()
result = gateway.complete(messages, prompt_id="checklist.extract", prompt_version="1")
result = gateway.complete_structured(messages, Schema, prompt_id=..., prompt_version=...)
```

- `messages`는 `Message(role, content)`의 목록이고 `role`은 `system`, `user`, `assistant` 중 하나다.
- `prompt_id`와 `prompt_version`은 호출자가 반드시 준다. 판정마다 어떤 프롬프트로 만든 결과인지 기록하기 위해서다.
- `temperature`는 0으로 보낸다. `max_tokens`는 호출자가 줄 때만 보낸다.
- 요청마다 고정 헤더 4개(`x-dep-ticket`, `Send-System-Name`, `User-Id`, `User-Type`)와 `Prompt-Msg-Id`, `Completion-Msg-Id`를 붙인다. 뒤의 둘은 **시도마다 새 UUID**다. 재시도도 새 UUID를 받는다.
- SDK의 자체 재시도는 끈다(`max_retries=0`). 켜 두면 같은 UUID로 다시 보내기 때문이다.

### 4.1 구조화 호출

1. 호출자의 메시지 뒤에 지시 메시지 하나를 붙인다. "JSON 객체 하나만 답하라"는 문장과 스키마의 JSON Schema가 들어 있다.
2. 응답 글을 JSON으로 읽는다. 글 전체가 코드 울타리(```` ``` ````) 하나로 싸여 있으면 울타리만 벗긴다. 글 속에서 `{`를 찾아 잘라 내는 식의 추측은 하지 않는다.
3. 최상위가 객체가 아니거나 JSON이 아니면 `INVALID_JSON`, 스키마 검증에 실패하면 `SCHEMA_MISMATCH`다. 검증은 엄격하게 한다. 숫자 자리에 문자열 `"3"`이 오면 맞지 않는 것으로 본다.
4. 이 둘은 같은 요청으로 한 번만 더 호출한다. 두 번째도 실패하면 `FAILED`다.

SDK의 `response_format`은 쓰지 않는다. 사내 모델이 지원하는지 확인되지 않았다.

스키마를 통과했다는 것은 형식이 맞다는 뜻일 뿐이다. 내용이 문서의 근거와 맞는지는 호출한 단위가 따로 대조한다.

## 5. 결과

```text
TextResult        status, text, failure, record
StructuredResult  status, value, text, failure, record
CallRecord        model, prompt_id, prompt_version, gateway_version, attempts, duration_ms,
                  prompt_tokens, completion_tokens
Attempt           prompt_msg_id, completion_msg_id, outcome, http_status, duration_ms
```

- `status`는 `OK` 또는 `FAILED`다. `OK`이면 `text`(구조화 호출은 `value`도)가 있고 `failure`가 없다. `FAILED`이면 그 반대다. 모델이 이 규칙을 검증하므로 실패한 결과에 응답 내용이 실릴 수 없다.
- 구조화 결과의 `text`는 응답 원문이고 `value`는 그것을 스키마로 읽은 것이다. 둘을 따로 둔다.
- `attempts`에는 재시도를 포함한 모든 시도가 순서대로 들어간다.
- 토큰 사용량은 응답에 있을 때만 채운다. 사내 게이트웨이가 주는지는 확인되지 않았다.
- 결과 객체는 프롬프트를 담지 않는다.

### 5.1 실패 사유

| 코드 | 뜻 | 재시도 |
|---|---|---|
| `CONFIG_MISSING` | 필수 환경변수가 없다 | 아니오 |
| `CONFIG_INVALID` | 주소나 시간 제한 값이 잘못되었다 | 아니오 |
| `TIMEOUT` | 시간 초과(HTTP 408 포함) | 예 |
| `CONNECTION_ERROR` | 연결하지 못했다 | 예 |
| `RATE_LIMITED` | HTTP 429 | 예 |
| `SERVER_ERROR` | HTTP 5xx | 예 |
| `AUTH_ERROR` | HTTP 401, 403 | 아니오 |
| `BAD_REQUEST` | 그 밖의 HTTP 4xx | 아니오 |
| `UNEXPECTED_RESPONSE` | 응답이 OpenAI 호환 형식이 아니다 | 아니오 |
| `EMPTY_RESPONSE` | 응답 글이 없거나 공백뿐이다 | 아니오 |
| `TRUNCATED` | `finish_reason`이 `length`다 | 아니오 |
| `CONTENT_FILTERED` | `finish_reason`이 `content_filter`다 | 아니오 |
| `INVALID_JSON` | 구조화 호출의 응답이 JSON 객체가 아니다 | 한 번 |
| `SCHEMA_MISMATCH` | JSON이 스키마에 맞지 않는다 | 한 번 |
| `INTERNAL_ERROR` | 게이트웨이 안의 예상하지 못한 오류 | 아니오 |

- 재시도하는 사유는 시도를 최대 3번 한다. 기다리는 시간은 1초, 2초다.
- 잘린 응답(`TRUNCATED`)은 글이 있어도 `FAILED`다. 일부만 읽고 판정하지 않는다.
- `FAILED`인 결과로 만든 판정은 UNKNOWN이다. 이 규칙은 단위 ④가 지킨다.

## 6. 로그

호출이 끝날 때마다 한 줄을 남긴다. 프롬프트 ID, 상태, 실패 사유, 시도 횟수, 소요 시간만 들어간다.

```text
INFO app.llm.base: call checklist.extract: OK, attempts=1, 850 ms
ERROR app.llm.base: call checklist.extract: FAILED AUTH_ERROR, attempts=1, 120 ms
```

SDK의 전송 계층(`httpx2`)은 요청마다 주소 전체를 INFO로 남기고, SDK는 요청과 응답을 DEBUG로 남긴다. 게이트웨이는 `httpx2`, `httpcore2`, `openai` 로거를 꺼서 프로그램이 어떤 로그 수준을 정해도 이 줄들이 나오지 않게 한다.

주소, 헤더 값, 사용자 ID, 모델 이름, 프롬프트, 응답 본문은 로그에 남기지 않는다. 예외는 타입과 이 저장소 파일의 위치만 남기고 메시지는 남기지 않는다. SDK 예외의 메시지에는 주소와 응답 본문이 들어갈 수 있다.

## 7. 가짜 LLM

`FakeLLM`은 게이트웨이와 같은 두 함수를 갖는다. 미리 정한 응답 글 또는 실패 사유를 순서대로 돌려주고, 받은 메시지를 기록한다. 구조화 호출의 JSON 읽기, 스키마 검증, 한 번 더 호출하기는 게이트웨이와 같은 코드를 쓴다. 정해 둔 응답이 다 떨어지면 `INTERNAL_ERROR`로 실패한다.

## 8. 명령줄

```bash
python -m app.llm check [--env-file .env]
```

문서와 무관한 고정 문장으로 텍스트 호출 한 번과 구조화 호출 한 번을 한다. 화면(stderr)에는 아래 꼴의 줄만 나온다.

```text
INFO app.llm.base: call llm.check.text: OK, attempts=1, 850 ms
INFO app.llm: text call: OK, attempts=1, 850 ms, usage=yes
INFO app.llm.base: call llm.check.structured: OK, attempts=1, 910 ms
INFO app.llm: structured call: OK, attempts=1, 910 ms, usage=yes
```

`app.llm.base`의 줄은 6절의 호출 로그다.

```text
ERROR app.llm: configuration: CONFIG_MISSING: DS_CREDENTIAL, DS_USER_ID
ERROR app.llm: text call: FAILED AUTH_ERROR (http 401), attempts=1, 120 ms
```

종료 코드는 둘 다 `OK`이면 0, 아니면 2다. 응답 글은 출력하지 않는다.

## 9. 파일 구성

```text
app/models/llm.py     Message, Attempt, CallRecord, TextResult, StructuredResult, 실패 사유
app/llm/config.py     LLMSettings, load_settings, read_env_file
app/llm/structured.py 지시 메시지 만들기, JSON 읽기와 스키마 검증
app/llm/base.py       complete, complete_structured의 공통 흐름과 기록, 로그
app/llm/gateway.py    LLMGateway: SDK 호출, 헤더, 재시도, 오류 분류
app/llm/fake.py       FakeLLM
app/llm/__main__.py   연결 확인 명령
```

`base.py`의 공통 클래스는 "요청 한 번을 보내고 글 또는 실패 사유와 시도 목록을 돌려주는" 함수 하나만 하위 클래스에 맡긴다. `gateway.py`와 `fake.py`가 그 함수를 구현한다.

게이트웨이의 규칙(지시 메시지, 재시도, 분류)을 바꾸면 `app/llm/base.py`의 `GATEWAY_VERSION`을 올린다. 이 값은 호출 기록에 들어간다.

## 10. 의존성

`openai` 3.49.0(Apache-2.0)을 쓴다. Python 3.10에서 설치되는 하위 의존성은 `httpx2` 2.14.0, `httpcore2` 2.14.0(BSD-3-Clause), `jiter` 0.18.0, `anyio`, `h11`, `truststore`(MIT), `idna`(BSD-3-Clause), `sniffio`(MIT 또는 Apache-2.0)다. `httpx2`, `httpcore2`, `jiter`의 최신 버전은 Python 3.11 이상만 지원하므로 위 버전으로 고정한다. 모두 `constraints.txt`에 적는다.

이 목록은 pip에 Python 3.10을 대상으로 지정해 얻은 것이다. 실제 Python 3.10에서 설치해 보지는 않았다. 테스트는 Python 3.14에서 위 버전으로 돌렸다.

## 11. 테스트

- SDK에 `httpx2.MockTransport`를 끼워 실제 SDK 경로를 지난다. 요청의 주소, 헤더, 본문과 응답별 분류를 확인한다.
- 기다리는 함수, 시계, UUID 발급 함수를 주입해 재시도를 시간 없이 테스트한다.
- 로그와 `repr`에 인증값, 주소, 프롬프트, 응답 본문이 없는지 확인한다.
- 주소가 없을 때 전송 계층이 한 번도 불리지 않는지 확인한다.

### 사내 확인

`python -m app.llm check`를 실행하고 화면의 줄과 종료 코드만 가지고 나온다. 절차는 [INHOUSE_LLM_CHECK.md](../../INHOUSE_LLM_CHECK.md)에 있다.

## 12. 미결

- 사내 게이트웨이가 토큰 사용량을 돌려주는지, `temperature=0`을 받는지 모른다. 사내 확인 결과로 정한다.
- 적절한 시간 제한과 재시도 횟수는 실제 응답 시간을 보고 정한다.
- 사내 모델이 `response_format`을 지원하면 구조화 호출에 쓸지 다시 본다.
