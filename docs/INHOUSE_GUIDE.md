# 사내 작업 순서 안내 (단위 ①)

회사에서 이 저장소를 `git clone`으로 받은 뒤 무엇을 어떤 순서로 하는지 적는다. 실행할 명령과 통과 기준은 이 문서에 있고, 적어 올 항목의 세부와 결과를 읽는 법은 [사내 확인 절차](INHOUSE_CHECK.md)에 있다. 두 문서가 다르면 사내 확인 절차가 우선한다.

## 먼저 알아 둘 것

- **이 저장소는 공개 저장소다.** 개발은 사외에서 하고 사내에서는 실행만 한다([D-002](DECISIONS.md)). 사내에서 받은 폴더에서는 커밋도 푸시도 하지 않는다. 사내에서 밖으로 나가는 것은 6단계의 기록 양식에 적은 것뿐이다.
- 지금 구현된 것은 단위 ①이다. 변환 파이프라인이 만든 `rag_ko.md`(한국어 번역본)와 번역 전 `rag.md`(원문)를 읽어 번역본 점검과 품질 점검을 한다. DOCX와 PDF를 직접 읽지 않고, LLM을 호출하지 않는다. 이 문서의 단계에서는 `config/example.env`의 값을 채울 필요가 없다.
- 단위 ②(LLM 게이트웨이)의 사내 연결 확인은 [사내 LLM 연결 확인 절차](INHOUSE_LLM_CHECK.md)에 따로 있다. 이 문서의 3단계까지 마친 뒤에 한다.
- 개발 환경에서는 Python 3.14로만 확인했다. 사내의 Python 3.10.11에서 테스트가 통과하는지는 3단계에서 처음 확인된다.
- 명령은 Git Bash 기준이다. PowerShell에서는 `.venv/Scripts/python`을 `.venv\Scripts\python`으로, Linux에서는 `.venv/bin/python`으로 바꾼다. 가상환경을 활성화하지 않아도 된다.

## 한눈에 보는 순서

| 단계 | 할 일 | 통과 기준 |
|---|---|---|
| 1 | 저장소 받기 | 폴더가 생겼고 커밋 해시를 적었다 |
| 2 | Python 확인과 설치 | 설치가 오류 없이 끝났고 패키지 버전을 적었다 |
| 3 | 테스트 | `failed`와 `error` 없이 `passed`만 나오고, ruff가 `All checks passed!`를 낸다 |
| 4 | 샘플로 실행 | `status: OK`, 종료 코드 0 |
| 5 | 실제 파일로 실행 | 건마다 화면의 줄과 종료 코드를 확인했다 |
| 6 | 기록 | 기록 양식을 채웠다 |
| 7 | 가지고 나오기 | 기록 양식에 적은 것만 가지고 나왔다 |
| 8 | 정리 | 결과 JSON을 사내 규정대로 처리했다 |

3단계가 통과하지 않으면 5단계로 가지 않는다. 그때는 6단계의 환경 부분만 적어 가지고 나온다.

## 1단계. 저장소 받기

```bash
git clone https://github.com/shyum-87/doc-compare.git
cd doc-compare
git log -1 --format=%h
```

마지막 명령이 보여 주는 커밋 해시를 적어 둔다. 어느 시점의 코드로 확인했는지 알기 위한 값이고, 공개 저장소에 있는 값이다.

실수로 푸시하지 않도록 푸시 주소를 막아 둘 수 있다. 받아 오기(`git pull`)는 그대로 된다.

```bash
git remote set-url --push origin no-push
```

## 2단계. Python 확인과 설치

```bash
python --version
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]" -c constraints.txt
.venv/Scripts/python -m pip freeze --exclude-editable
```

- `python --version`이 3.10.11이 아니면 나온 버전을 적는다.
- 패키지는 사내 PyPI 미러에서 받는다. 미러에 `constraints.txt`의 버전이 없어 설치가 실패하면 `-c constraints.txt`를 빼고 설치한 뒤 그 사실을 적는다.
- 마지막 명령의 출력에서 `이름==버전` 꼴의 줄만 적는다. `-e`로 시작하는 줄이나 `@` 뒤에 경로·주소가 붙은 줄은 적지 않는다. Python 3.10에서는 `exceptiongroup`과 `tomli`가 더 설치되는데, 이 둘의 버전이 특히 필요하다.

자세한 내용은 사내 확인 절차 1절에 있다.

## 3단계. 테스트

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
```

이 안내문을 쓸 때는 `956 passed`였다. 테스트가 늘면 숫자는 커진다. `failed`나 `error`가 없고 ruff가 `All checks passed!`를 내면 통과다.

하나라도 실패하면 여기서 멈춘다. 실패한 테스트의 이름과 오류 종류(예: `ImportError`)만 적는다. Traceback에는 폴더 경로가 나오므로 옮기지 않는다. 테스트의 기준값과 `tests/fixtures/`의 샘플은 사내에서 고치지 않는다.

## 4단계. 샘플로 실행

실제 파일을 넣기 전에 저장소의 가상 샘플로 명령이 도는지 본다.

```bash
.venv/Scripts/python -m app.parsing tests/fixtures/rag_ko/sample_bakery_sop.md --doc-id SOP-SAMPLE --version 1 --original-language vi --source tests/fixtures/rag/sample_bakery_sop.vi.md --out out/sample.json
echo $?
```

화면에 아래 줄이 나오고 종료 코드가 0이면 된다. PowerShell에서는 종료 코드를 `$LASTEXITCODE`로 본다.

```text
INFO app.parsing.ingest: read the translated file: 114 lines, 49 elements
INFO app.parsing.ingest: read the source file: 114 lines, 49 elements
INFO app.parsing.ingest: status: OK
INFO app.parsing.ingest: findings: IMAGE_PRESENT=6
```

한국어 기준 문서의 꼴도 한 번 본다. `--source`가 없고 `--original-language`가 `ko`다.

```bash
.venv/Scripts/python -m app.parsing tests/fixtures/rag_ko/sample_bakery_sop.md --doc-id SOP-SAMPLE --version 1 --original-language ko --out out/sample_ko.json
```

```text
INFO app.parsing.ingest: read the source file: 114 lines, 49 elements
INFO app.parsing.ingest: status: OK
INFO app.parsing.ingest: findings: IMAGE_PRESENT=3
```

이 출력과 다르면 5단계로 가지 않고, 다르게 나온 `INFO` 줄과 `ERROR` 줄을 적는다. 샘플은 가상 데이터라 이 줄들은 그대로 적어도 된다. Traceback이 나오면 예외 이름과 이 저장소 파일의 `파일 이름:줄 번호`만 적는다.

## 5단계. 실제 파일로 실행

준비할 것:

- 사내 변환 파이프라인이 만든 파일. 대상 문서는 `rag_ko.md`와 번역 전 `rag.md`의 쌍, 한국어 기준 문서는 파일 하나다.
- 기준 문서 몇 건과 대상 문서 몇 쌍. 원문 언어(베트남어, 영어, 중국어)가 고루 들어가게 고른다.
- **실제 파일은 저장소 폴더 밖에 두고 경로로 가리킨다.** `.gitignore`는 `.md` 파일을 걸러 주지 않는다.

대상 문서(번역본 + 원문):

```bash
.venv/Scripts/python -m app.parsing <rag_ko.md 경로> --doc-id <문서 ID> --version <버전> --original-language vi --source <rag.md 경로> --out out/<이름>.json
```

한국어 기준 문서:

```bash
.venv/Scripts/python -m app.parsing <기준 문서 경로> --doc-id <문서 ID> --version <버전> --original-language ko --out out/<이름>.json
```

실행할 때 지킬 것:

- `--original-language`는 원문 언어에 맞춰 `vi`, `en`, `zh`, `ko` 중 하나를 준다.
- 프로그램은 어느 파일이 번역본이고 어느 파일이 원문인지, 언어가 맞는지 확인하지 않는다. 바꿔 넣거나 언어를 틀리게 주어도 `OK`가 나올 수 있다. 실행하기 전에 직접 확인한다.
- 결과 파일은 `out/` 아래에만 쓴다. 결과 JSON에는 문서 본문이 들어간다.
- 실행 직후 `echo $?`로 종료 코드를 본다. `OK`는 0, `REVIEW_REQUIRED`는 1, `FAILED`와 사용법 오류, 결과 파일을 쓰지 못한 경우는 2다.

`REVIEW_REQUIRED`와 `FAILED`는 실행이 잘못된 것이 아니라 확인하려던 결과다. 멈추지 말고 나머지 건도 실행한다. 화면에 나오는 줄의 꼴과 `ERROR` 줄을 읽는 법은 사내 확인 절차 3절에 있다.

## 6단계. 기록

아래 양식을 채운다. 여기 없는 것은 적지 않는다.

```text
[환경]
커밋 해시:
Python 버전:
설치: constraints.txt 그대로 / constraints.txt 없이
설치된 패키지(이름==버전):
테스트: 모두 통과 / 실패한 테스트 이름과 오류 종류
ruff: 통과 / 실패

[실행한 건마다]
문서 종류와 원문 언어:        (예: 대상 문서, vi)
줄 수와 요소 수:              (예: 번역본 114줄 49개, 원문 114줄 49개)
status:                       (ERROR 줄만 나왔으면 FAILED)
findings의 코드별 개수:       (예: IMAGE_PRESENT=6, TOKEN_MISMATCH=2)
ERROR 줄의 사유:              (예: NOT_UTF8, 또는 internal error: KeyError at tokens.py:120)

[질문의 답]
1. 번역기가 숫자 표기를 바꾸는가:
2. 페이지 마커와 헤딩이 같은 수로 나오는가:
3. 미분류 줄은 어떤 형태인가:
4. TOKEN_MISMATCH 중 실제 오역이 아닌 것은 어떤 유형인가:
```

질문 네 개는 결과 JSON을 사내에서 열어 보고 답한다. 무엇을 보고 어떻게 답하는지는 사내 확인 절차 5절에 있다. 답은 "단위가 한글로 옮겨졌다"처럼 유형으로만 적고, 본문과 숫자 값은 옮기지 않는다.

## 7단계. 가지고 나오기

가지고 나오는 것은 6단계의 양식에 적은 것뿐이다.

**가지고 나오지 않는 것:** 문서 본문, 문서에 적힌 숫자와 설비·문서 번호 같은 토큰 값, 결과 JSON, 파일 이름, 폴더 경로, 문서 ID, 사용자 ID, 사내 주소, Traceback 전체, 사용법 오류의 `usage:` 줄과 `error:` 줄.

사내 반출 규정이 이 문서보다 엄격하면 그 규정을 따른다. 반출 방법과 승인도 사내 규정을 따른다.

가지고 나온 기록은 사외 개발 환경에서 파싱 규칙과 토큰 규칙을 고치는 데 쓴다. 코드별 개수가 무엇을 뜻하는지는 사내 확인 절차 6절에 있다.

## 8단계. 정리

- `out/` 아래의 결과 JSON에는 문서 본문이 들어 있다. 확인이 끝나면 사내 규정에 따라 지우거나 보관한다.
- `git status`에 `out/`이나 실제 파일이 보이지 않는지 확인한다. `out/`은 `.gitignore`에 들어 있어 보이지 않는 것이 정상이다.

## 코드가 바뀐 뒤 다시 확인할 때

사외에서 규칙을 고쳐 푸시하면 사내에서 다시 받는다.

```bash
git pull origin main
git log -1 --format=%h
.venv/Scripts/python -m pip install -e ".[dev]" -c constraints.txt
```

설치 명령은 `pyproject.toml`이나 `constraints.txt`가 바뀌었을 때만 필요하지만, 다시 실행해도 문제는 없다. 그 뒤 3단계부터 같은 순서로 다시 한다. 같은 파일을 다시 넣어 코드별 개수가 어떻게 달라졌는지 적으면 규칙을 고친 효과를 볼 수 있다.

## 사내에서 받은 폴더에서 하지 않는 것

- `git commit`, `git push`. 코드는 사내에서 고치지 않는다. 가지고 나온 기록을 보고 사외에서 고친다.
- 실제 파일이나 결과 JSON을 저장소 폴더 안(`out/` 밖)에 두는 것.
- `tests/fixtures/`의 샘플과 테스트의 기준값을 고치는 것.
- 사내 주소, 사용자 ID, 인증 정보를 저장소의 파일에 적는 것.

## 막혔을 때

| 증상 | 할 일 |
|---|---|
| `git clone`이 되지 않는다 | 사내에서 외부 저장소를 받는 방법은 사내 규정을 따른다. 그 방법이나 주소를 이 저장소에 적지 않는다. |
| `python --version`이 3.10.11이 아니다 | 3.10.11을 가리키는 실행 파일로 `-m venv .venv`를 실행한다. Windows에 여러 버전이 있으면 `py -3.10 -m venv .venv`를 쓸 수 있다. 3.10.11이 없으면 나온 버전을 적고 계속한다. |
| 설치할 때 버전을 찾지 못한다 | `-c constraints.txt`를 빼고 설치하고 그 사실과 설치된 버전을 적는다. |
| 테스트가 실패한다 | 멈춘다. 테스트 이름과 오류 종류만 적는다. 사내에서 코드를 고치지 않는다. |
| 샘플 실행의 출력이 4단계와 다르다 | 멈춘다. 다르게 나온 줄을 적는다. |
| `ERROR app.parsing:`으로 시작하는 줄이 나온다 | 명령줄 쪽의 오류다. 사내 확인 절차 3절을 본다. 입력한 값이 그대로 보이는 줄은 옮기지 않는다. |
| Traceback이 나온다 | 예외 이름과 이 저장소 파일의 `파일 이름:줄 번호`만 적는다. |
