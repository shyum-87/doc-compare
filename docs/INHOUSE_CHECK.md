# 사내 확인 절차 (단위 ①)

테스트는 가상 샘플만 쓴다. 실제 변환 산출물의 표기와 "원문과 번역본이 요소 단위로 1:1 대응한다"(D-008)는 가정은 사내에서만 확인할 수 있다. 이 문서는 사내에서 무엇을 실행하고 무엇을 가지고 나오는지 적는다.

이 저장소는 공개 저장소다. 가지고 나오는 것은 4절에 적은 개수와 5절 질문의 짧은 답뿐이다. **문서 본문, 결과 JSON, 파일 이름, 문서 ID, 사내 주소는 가지고 나오지 않는다.** 사내 반출 규정이 이 문서보다 엄격하면 그 규정을 따른다.

## 1. 준비

Python 3.10.11에서 가상환경을 만들고 사내 PyPI 미러로 설치한다.

```bash
python --version
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]" -c constraints.txt
```

미러에 `constraints.txt`의 버전이 없어 설치가 실패하면 `-c constraints.txt`를 빼고 설치한 뒤, 그 사실을 적어 온다.

설치된 버전을 적어 둔다. Python 3.10에서는 pytest가 `exceptiongroup`과 `tomli`를 더 설치하는데, 이 둘은 `constraints.txt`에 없다.

```bash
.venv/Scripts/python -m pip freeze
```

## 2. 테스트

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
```

둘 중 하나라도 실패하면 실제 파일을 넣기 전에 멈춘다. 실패한 테스트의 이름과 오류 종류(예: `ImportError`)를 적어 온다. 이 테스트는 가상 샘플만 쓰므로 테스트 이름과 오류 종류에는 사내 정보가 없다.

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

화면(stderr)에 아래와 같은 줄이 나온다. 이 줄에는 본문이 없다.

```text
INFO app.parsing.ingest: read the translated file: 114 lines, 49 elements
INFO app.parsing.ingest: read the source file: 114 lines, 49 elements
INFO app.parsing.ingest: status: OK
INFO app.parsing.ingest: findings: IMAGE_PRESENT=6
```

종료 코드는 `OK` 0, `REVIEW_REQUIRED` 1, `FAILED` 2다. 사용법 오류이거나 결과 파일을 쓰지 못했을 때도 2다. `--out`에 입력 파일을 주면 사용법 오류다. 결과 JSON은 `out/` 아래에 두고 사내에서만 연다.

## 4. 가지고 나올 것

실행한 건마다 아래만 적는다.

| 항목 | 예 |
|---|---|
| 문서 종류와 원문 언어 | 대상 문서, `vi` |
| 줄 수와 요소 수 | 번역본 114줄 49개, 원문 114줄 49개 |
| `status:` 줄의 값 | `REVIEW_REQUIRED` |
| `findings:` 줄의 코드별 개수 | `IMAGE_PRESENT=6, TOKEN_MISMATCH=2` |
| `FAILED`일 때 로그의 사유 | `NOT_UTF8`, 또는 `internal error: KeyError at tokens.py:120` |

그리고 1절에서 적은 설치 버전, 5절 질문의 답.

## 5. 함께 확인할 질문

결과 JSON을 사내에서 열어 보고 답만 적는다. 본문은 옮기지 않는다.

1. **번역기가 숫자 표기를 바꾸는가.** 베트남어 원문의 `1,5` 같은 소수가 번역본에 `1,5`로 남는가, `1.5`로 바뀌는가. 글자로 쓴 수(`hai lần`, `once`)가 번역본에서 숫자로 바뀌는가. `TOKEN_MISMATCH`와 `NUMBER_FORMAT_AMBIGUOUS`가 붙은 요소를 보면 알 수 있다.
2. **원문과 번역본의 페이지 마커와 헤딩이 같은 수로 나오는가.** `SKELETON_MISMATCH`가 나온 건이 있으면, 어느 쪽에 무엇이 더 있는지(예: "번역본에 헤딩이 하나 더 있다")만 적는다.
3. **미분류 줄은 어떤 형태인가.** `UNCLASSIFIED_LINE`이 붙은 줄의 형태를 일반화해서 적는다(예: "구분 줄이 없는 표", "HTML 태그 줄", "`>` 인용").
4. **`TOKEN_MISMATCH` 중 실제 오역이 아닌 것은 어떤 유형인가.** 예: "단위가 한글로 옮겨졌다", "날짜 표기가 바뀌었다".

## 6. 결과를 읽는 법

| 많이 나온 코드 | 뜻 | 다음에 할 일 |
|---|---|---|
| `UNCLASSIFIED_LINE` | 파일에 파서가 모르는 표기가 있다 | 형태를 보고 파싱 규칙을 추가할지 정한다 |
| `SEGMENT_UNALIGNED`, `SKELETON_MISMATCH` | 원문과 번역본이 요소 단위로 1:1이 아니다 | D-008의 가정을 다시 본다 |
| `NUMBER_FORMAT_AMBIGUOUS` | 숫자 표기가 언어별 가정과 다르다 | 숫자 표기 규칙을 고친다 |
| `TOKEN_MISMATCH` | 숫자·단위·코드가 다르다 | 5절 4번의 유형을 보고 토큰 규칙을 고칠지 정한다 |
| `TABLE_ROW_WIDTH_MISMATCH` | 표의 열 수가 행마다 다르다 | 변환 단계의 문제인지 확인한다 |

파싱 규칙이나 토큰 규칙을 고치면 `app/parsing/ingest.py`의 `PARSER_VERSION`을 올린다. 규칙을 어떻게 고칠지는 가지고 나온 숫자를 보고 다시 정하며, 이 문서만 보고 정하지 않는다.
