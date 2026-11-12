# 사내 LLM 연결 확인 절차 (단위 ②)

개발 환경에서는 사내 LLM에 접근할 수 없다([D-002](DECISIONS.md)). 게이트웨이의 테스트는 가짜 전송 계층만 쓰므로, 실제 주소와 헤더로 호출이 되는지는 사내에서 처음 확인된다. 이 문서는 그 확인을 어떻게 하고 무엇을 가지고 나오는지 적는다.

저장소를 받고 설치하고 테스트하는 순서는 [사내 작업 순서 안내](INHOUSE_GUIDE.md)의 1~3단계와 같다. 이 확인은 3단계(테스트)가 통과한 뒤에 한다. 단위 ①의 실제 파일 확인과는 서로 독립이라 어느 쪽을 먼저 해도 된다.

이 저장소는 공개 저장소다. **가지고 나오는 것은 4절에 적은 것뿐이다.** 주소, 인증값, 사용자 ID, 시스템 이름, 모델 이름, 응답 글은 가지고 나오지 않는다.

## 1. 무엇을 보내는가

명령은 호출을 두 번 한다. 재시도가 있으면 더 보낸다.

- 텍스트 호출: 영어 한 문장("OK라고만 답하라")을 보낸다.
- 구조화 호출: 영어 한 문장과 JSON 형식 지시를 보낸다.

문서 내용은 보내지 않는다. 요청에는 설정한 인증값과 식별값이 헤더로 들어가고, 주소는 `DS_API_BASE_URL`에 적은 곳 하나뿐이다.

## 2. 설정

환경변수를 직접 설정하거나 파일에 적는다. 파일을 쓰려면 `config/example.env`를 저장소 루트의 `.env`로 복사해 값을 채운다. `.env`는 `.gitignore`에 들어 있어 커밋되지 않는다. `config/example.env` 자체에는 값을 적지 않는다.

| 환경변수 | 필수 | 내용 |
|---|---|---|
| `DS_API_BASE_URL` | 예 | 사내 OpenAI 호환 API의 주소. `http://` 또는 `https://`로 시작한다 |
| `DS_CREDENTIAL` | 예 | 헤더 `x-dep-ticket`의 값 |
| `DS_SYSTEM_NAME` | 예 | 헤더 `Send-System-Name`의 값 |
| `DS_USER_ID` | 예 | 헤더 `User-Id`의 값 |
| `DS_LLM_MODEL` | 예 | 모델 이름 |
| `DS_OPENAI_API_KEY` | 아니오 | 없으면 `placeholder`를 보낸다 |
| `DS_LLM_TIMEOUT_SECONDS` | 아니오 | 시도 한 번의 시간 제한(초). 없으면 60 |

같은 변수가 환경과 파일에 모두 있으면 환경의 값을 쓴다.

## 3. 실행

```bash
.venv/Scripts/python -m app.llm check --env-file .env
echo $?
```

환경변수를 직접 설정했으면 `--env-file`을 뺀다. PowerShell에서는 `.venv\Scripts\python`을 쓰고 종료 코드를 `$LASTEXITCODE`로 본다.

화면(stderr)에 아래 꼴의 줄이 나온다. 이 줄들에는 주소, 인증값, 응답 글이 없다.

```text
INFO app.llm.base: call llm.check.text: OK, attempts=1, 850 ms
INFO app.llm: text call: OK, attempts=1, 850 ms, usage=yes
INFO app.llm.base: call llm.check.structured: OK, attempts=1, 910 ms
INFO app.llm: structured call: OK, attempts=1, 910 ms, usage=yes
```

실패하면 `ERROR` 줄이 나온다.

```text
ERROR app.llm: configuration: CONFIG_MISSING: DS_CREDENTIAL, DS_USER_ID
ERROR app.llm: text call: FAILED AUTH_ERROR (http 401), attempts=1, 120 ms
ERROR app.llm: cannot read the env file: FileNotFoundError
```

종료 코드는 두 호출이 모두 `OK`이면 0, 그 밖에는 2다. 텍스트 호출이 실패해도 구조화 호출은 한다.

- `attempts`는 보낸 횟수다. 2 이상이면 재시도했거나(시간 초과, 연결 실패, 429, 5xx), 구조화 응답의 형식이 틀려 한 번 더 물은 것이다.
- `usage=yes`는 응답에 토큰 사용량이 들어 있었다는 뜻이다.

## 4. 가지고 나올 것

- 커밋 해시(`git log -1 --format=%h`)
- 3절의 화면에 나온 줄 전부와 종료 코드
- 두세 번 더 실행했을 때 `ms` 값의 대략적인 범위

Python이 직접 내는 Traceback이 나오면 예외 이름과 이 저장소 파일의 `파일 이름:줄 번호`만 적는다. Traceback에는 폴더 경로가 나온다.

## 5. 결과를 읽는 법

| 나온 것 | 뜻 | 할 일 |
|---|---|---|
| `CONFIG_MISSING: 이름들` | 그 환경변수가 없거나 비어 있다 | 값을 채운다 |
| `CONFIG_INVALID: 이름` | 주소가 `http(s)://`로 시작하지 않거나 시간 제한이 양수가 아니다 | 값을 고친다 |
| `CONNECTION_ERROR` | 주소에 연결하지 못했다 | 주소, 프록시 설정, 사내 인증서를 확인한다 |
| `TIMEOUT` | 시간 제한 안에 응답이 오지 않았다 | `DS_LLM_TIMEOUT_SECONDS`를 늘려 다시 본다 |
| `AUTH_ERROR (http 401/403)` | 인증값이나 식별 헤더가 거부되었다 | 인증값, 시스템 이름, 사용자 ID를 확인한다 |
| `BAD_REQUEST (http 404)` | 주소의 경로나 모델 이름이 틀렸을 가능성이 크다 | 주소가 `/chat/completions` 앞까지인지, 모델 이름이 맞는지 확인한다 |
| `BAD_REQUEST (http 400/422)` | 요청의 어떤 값을 받지 않는다(예: `temperature`) | 사유와 상태 코드를 적어 온다. 사외에서 요청을 고친다 |
| `RATE_LIMITED`, `SERVER_ERROR` | 한도 초과 또는 서버 쪽 오류 | 시간을 두고 다시 실행한다 |
| `UNEXPECTED_RESPONSE` | 200으로 응답이 왔지만 OpenAI 호환 형식이 아니다(로그인 페이지 등) | 주소와 프록시를 확인한다 |
| `EMPTY_RESPONSE`, `TRUNCATED`, `CONTENT_FILTERED` | 응답 글이 비었거나 잘렸거나 걸러졌다 | 적어 온다 |
| 구조화 호출만 `INVALID_JSON`, `SCHEMA_MISMATCH` | 모델이 JSON만 답하라는 지시를 따르지 않았다 | 적어 온다. 사외에서 지시 문장이나 방식을 고친다 |
| `usage=no` | 응답에 토큰 사용량이 없다 | 적어 온다. 호출 기록의 토큰 수가 비게 된다 |

게이트웨이의 규칙(지시 메시지, 재시도, 분류)을 고치면 `app/llm/base.py`의 `GATEWAY_VERSION`을 올린다.

## 6. 정리

- `.env`에는 인증값이 들어 있다. 확인이 끝나면 사내 규정에 따라 지우거나 보관한다.
- `git status`에 `.env`가 보이지 않는지 확인한다. 보이지 않는 것이 정상이다.
