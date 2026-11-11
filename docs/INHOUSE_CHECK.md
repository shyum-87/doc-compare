# 사내 확인 절차 (단위 ①)

테스트는 가상 샘플만 쓴다. 실제 변환 산출물의 표기와 "원문과 번역본이 요소 단위로 1:1 대응한다"([D-008](DECISIONS.md))는 가정은 사내에서만 확인할 수 있다. 이 문서는 사내에서 무엇을 실행하고 무엇을 가지고 나오는지 적는다. 저장소를 받은 뒤의 전체 순서와 기록 양식은 [사내 작업 순서 안내](INHOUSE_GUIDE.md)에 있다.

이 저장소는 공개 저장소다. 가지고 나오는 것은 1절에 적은 커밋 해시, Python 버전과 설치 사실, 설치된 패키지의 이름과 버전, 실패한 테스트의 이름과 오류 종류(2절), 3절과 4절에 적은 개수·코드·오류 종류, 5절 질문의 짧은 답뿐이다. **문서 본문, 문서에 적힌 숫자와 설비·문서 번호 같은 토큰 값, 결과 JSON, 파일 이름, 폴더 경로, 문서 ID, 사용자 ID, 사내 주소는 가지고 나오지 않는다.** 사내 반출 규정이 이 문서보다 엄격하면 그 규정을 따른다.

## 1. 준비

명령은 Git Bash 기준이다. PowerShell에서는 `.venv\Scripts\python`, Linux에서는 `.venv/bin/python`을 쓴다.

받은 코드의 커밋 해시를 적어 둔다. 어느 시점의 코드로 확인했는지 알기 위한 값이고, 공개 저장소에 있는 값이다.

```bash
git log -1 --format=%h
```

Python 3.10.11에서 가상환경을 만들고 사내 PyPI 미러로 설치한다. `python --version`이 3.10.11이 아니면 나온 버전을 적어 온다.

```bash
python --version
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]" -c constraints.txt
```

미러에 `constraints.txt`의 버전이 없어 설치가 실패하면 `-c constraints.txt`를 빼고 설치한 뒤, 그 사실을 적어 온다.

설치된 버전을 적어 둔다. Python 3.10에서는 pytest가 `exceptiongroup`과 `tomli`를 더 설치하는데, 이 둘은 `constraints.txt`에 없다.

```bash
.venv/Scripts/python -m pip freeze --exclude-editable
```

`이름==버전` 꼴의 줄만 적는다. `-e`로 시작하는 줄이나 `@` 뒤에 경로·주소가 붙은 줄에는 사내 주소나 폴더 경로가 들어 있으므로 적지 않는다.

## 2. 테스트

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
```

둘 중 하나라도 실패하면 실제 파일을 넣기 전에 멈춘다. 실패한 테스트의 이름과 오류 종류(예: `ImportError`)를 적어 온다. 이 테스트는 가상 샘플만 쓰므로 테스트 이름과 오류 종류에는 사내 정보가 없다. Traceback에는 폴더 경로가 나오므로 옮기지 않고, 오류 종류만 적는다.

## 3. 실제 파일로 실행

기준 문서 몇 건과 대상 문서 몇 쌍을 고른다. 원문 언어(베트남어, 영어, 중국어)가 고루 들어가게 한다.

대상 문서(번역본 `rag_ko.md` + 원문 `rag.md`):

```bash
.venv/Scripts/python -m app.parsing <rag_ko.md 경로> --doc-id <문서 ID> --version <버전> --original-language vi --source <rag.md 경로> --out out/<이름>.json
```

한국어 기준 문서:

```bash
.venv/Scripts/python -m app.parsing <기준 문서 경로> --doc-id <문서 ID> --version <버전> --original-language ko --out out/<이름>.json
```

`--original-language`에는 원문 언어에 맞춰 `vi`, `en`, `zh`, `ko` 중 하나를 준다. 경로나 문서 ID에 공백이 있으면 따옴표로 감싼다.

프로그램은 어느 파일이 번역본이고 어느 파일이 원문인지, `--original-language`가 맞는지 확인하지 않는다. 두 파일을 바꿔 넣거나 언어를 틀리게 주어도 `OK`가 나올 수 있다. 실행하기 전에 주 파일이 한국어 `rag_ko.md`이고 `--source`가 번역 전 `rag.md`인지, 언어가 맞는지 직접 확인한다. 한국어 기준 문서로 넣는 파일이 실제로 한국어 문서인지도 확인한다.

실제 파일은 이 저장소 폴더 밖에 두고 경로로 가리킨다. `.gitignore`는 `.md` 파일을 걸러 주지 않으므로, 저장소 폴더 안에 두면 커밋에 섞일 수 있다.

화면(stderr)에 아래와 같은 줄이 나온다. 이 줄에는 본문이 없다. 한국어 기준 문서는 읽은 파일 줄이 `read the source file` 하나만 나온다(번역하지 않은 문서는 그 자체가 원문이다).

```text
INFO app.parsing.ingest: read the translated file: 114 lines, 49 elements
INFO app.parsing.ingest: read the source file: 114 lines, 49 elements
INFO app.parsing.ingest: status: OK
INFO app.parsing.ingest: findings: IMAGE_PRESENT=6
```

`FAILED`이면 `status:` 줄과 `findings:` 줄이 없고 아래 둘 중 하나와 같은 `ERROR` 줄이 나온다.

```text
ERROR app.parsing.ingest: cannot read the translated file: NOT_UTF8
ERROR app.parsing.ingest: internal error: KeyError at tokens.py:120
```

파일을 읽지 못한 사유는 `FILE_UNREADABLE`, `NOT_UTF8`, `EMPTY_DOCUMENT` 중 하나다. `ERROR app.parsing:`으로 시작하는 줄은 명령줄 쪽의 오류다. `internal error: KeyError`처럼 위치 없이 오류 종류만 나오거나, `status:` 줄이나 앞의 `ERROR` 줄 뒤에 `cannot write the result file: PermissionError`처럼 결과 파일을 쓰지 못했다고 나온다. 이 두 경우에는 결과 파일이 없다.

종료 코드는 `OK` 0, `REVIEW_REQUIRED` 1, `FAILED` 2다. 사용법 오류이거나 결과 파일을 쓰지 못했을 때도 2다. 종료 코드는 실행 직후 `echo $?`(PowerShell에서는 `$LASTEXITCODE`)로 본다. `--out`에 입력 파일을 주면 사용법 오류다. 결과 JSON은 `out/` 아래에 두고 사내에서만 연다.

사용법 오류의 `usage:` 줄과 `error:` 줄은 입력한 값을 그대로 보여 주고, Python이 직접 내는 Traceback에는 폴더 경로가 나온다. 둘 다 옮기지 않는다. Traceback이 나오면 예외 이름과 이 저장소 파일의 `파일 이름:줄 번호`만 적는다.

## 4. 가지고 나올 것

실행한 건마다 아래만 적는다.

| 항목 | 예 |
|---|---|
| 문서 종류와 원문 언어 | 대상 문서, `vi` |
| 줄 수와 요소 수 | 번역본 114줄 49개, 원문 114줄 49개 |
| `status:` 줄의 값. 이 줄 없이 `ERROR` 줄이 나오면 `FAILED` | `REVIEW_REQUIRED` |
| `findings:` 줄의 코드별 개수 | `IMAGE_PRESENT=6, TOKEN_MISMATCH=2` |
| `ERROR` 줄이 나왔을 때 그 사유 | `NOT_UTF8`, 또는 `internal error: KeyError at tokens.py:120` |

그리고 1절에서 적은 커밋 해시와 설치 버전, 5절 질문의 답.

## 5. 함께 확인할 질문

결과 JSON을 사내에서 열어 보고 답만 적는다. 본문과 토큰 값은 옮기지 않는다.

1. **번역기가 숫자 표기를 바꾸는가.** 베트남어 원문의 `1,5` 같은 소수가 번역본에 `1,5`로 남는가, `1.5`로 바뀌는가. 이 경우는 남아도 바뀌어도 일치로 읽혀 발견 항목이 나오지 않는다. 결과 JSON에서 원문 요소에 소수점 쉼표가 있는 짝을 몇 개 골라 번역본 쪽 요소를 직접 본다. 글자로 쓴 수(`hai lần`, `once`)가 번역본에서 숫자로 바뀌는가. 이 경우와, `1.000`이나 `1,500`처럼 한국어에서 다르게 읽히는 표기가 번역본에 그대로 남은 경우는 `TOKEN_MISMATCH`로 나온다.
2. **원문과 번역본의 페이지 마커와 헤딩이 같은 수로 나오는가.** `SKELETON_MISMATCH`가 나온 건이 있으면, 어느 쪽에 무엇이 더 있는지(예: "번역본에 헤딩이 하나 더 있다")만 적는다.
3. **미분류 줄은 어떤 형태인가.** `UNCLASSIFIED_LINE`이 붙은 줄의 형태를 일반화해서 적는다(예: "구분 줄이 없는 표", "HTML 태그 줄", "`>` 인용").
4. **`TOKEN_MISMATCH` 중 실제 오역이 아닌 것은 어떤 유형인가.** 예: "단위가 한글로 옮겨졌다", "날짜 표기가 바뀌었다".

## 6. 결과를 읽는 법

| 많이 나온 코드 | 뜻 | 다음에 할 일 |
|---|---|---|
| `UNCLASSIFIED_LINE` | 파일에 파서가 모르는 표기가 있다 | 형태를 보고 파싱 규칙을 추가할지 정한다 |
| `AMBIGUOUS_LIST_OR_NEGATIVE` | 공백 없는 `-` 뒤에 숫자가 온다. 목록인지 음수인지 추측하지 않았다 | 실제 표기를 보고 규칙을 정한다 |
| `SEGMENT_UNALIGNED`, `SKELETON_MISMATCH`, `TABLE_SHAPE_MISMATCH` | 원문과 번역본이 요소 단위로 1:1이 아니다(표는 행 수나 열 수가 다르다) | D-008의 가정을 다시 본다 |
| `NUMBER_FORMAT_AMBIGUOUS` | 숫자 표기가 언어별 가정과 다르다 | 숫자 표기 규칙을 고친다 |
| `TOKEN_MISMATCH` | 숫자·단위·코드가 다르다 | 5절 4번의 유형을 보고 토큰 규칙을 고칠지 정한다 |
| `TABLE_ROW_WIDTH_MISMATCH` | 표의 열 수가 행마다 다르다 | 변환 단계의 문제인지 확인한다 |

`IMAGE_PRESENT`는 참고 항목이며 상태를 바꾸지 않는다. 코드 전체는 [단위 ① 설계 문서](superpowers/specs/2026-11-11-foundation-rag-adapter-design.md)의 7.2절에 있다.

파싱 규칙이나 토큰 규칙을 고치면 `app/parsing/ingest.py`의 `PARSER_VERSION`을 올린다. 규칙을 어떻게 고칠지는 가지고 나온 숫자를 보고 다시 정하며, 이 문서만 보고 정하지 않는다.
