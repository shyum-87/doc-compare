# 기반 + rag_ko.md 어댑터 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 외부 변환 파이프라인이 만든 `rag_ko.md`(와 번역 전 `rag.md`)를 위치를 가리킬 수 있는 요소 목록으로 읽고, 번역본 점검과 품질 점검을 거쳐 `FAILED` / `REVIEW_REQUIRED` / `OK` 상태와 발견 항목을 내는 어댑터를 만든다.

**Architecture:** 파일 읽기 → 줄 단위 파서 → (원문이 있으면) 번역본 점검 → 품질 판정 순서로 이어지는 Python 함수형 파이프라인이다. 모델은 바꿀 수 없는(frozen) Pydantic 모델이고, 발견 항목은 문서 안에 넣지 않고 `element_id`로 문서를 가리킨다. 예상한 입력 문제는 상태와 발견 항목으로 돌려주고, 예상하지 못한 예외는 맨 바깥에서 `FAILED`로 바꾼다(fail closed).

**Tech Stack:** Python 3.10, Pydantic 2, pytest, ruff. 파서는 직접 쓴 줄 단위 파서다(D-010). Markdown 라이브러리, LLM, DB는 쓰지 않는다.

---

## 먼저 읽을 것

- 설계: [docs/superpowers/specs/2026-11-11-foundation-rag-adapter-design.md](../specs/2026-11-11-foundation-rag-adapter-design.md). 아래에서 "설계 §5"처럼 가리킨다.
- 입력 형식: [docs/RAG_KO_FORMAT.md](../../RAG_KO_FORMAT.md)
- 결정 기록: [docs/DECISIONS.md](../../DECISIONS.md). 특히 D-003(Python 3.10.11), D-008(원문과 번역본의 1:1 대응 가정), D-009(의존성 확인), D-010(줄 단위 파서), D-011(대상 언어), D-013(요소 단위로 막는다), D-014(가상 데이터).
- 저장소 규칙: [CLAUDE.md](../../../CLAUDE.md)의 "보안"과 "반드시 지킬 설계 불변조건".

이 계획의 코드, 명령, 기대 출력은 저장소를 새로 클론한 폴더에서 Task 순서대로 실제로 실행해 얻은 것이다. 실행한 환경은 Windows, Git Bash, Python 3.14.4다. **사내 실행 환경인 Python 3.10.11에서는 아직 실행하지 않았다.** 그 확인은 Task 19에서 만드는 `docs/INHOUSE_CHECK.md`의 절차로 한다.

## 작업 규칙

- **명령은 저장소 루트에서 Git Bash로 실행한다.** PowerShell에서는 `.venv/Scripts/python`을 `.venv\Scripts\python`으로, Linux와 macOS에서는 `.venv/bin/python`으로 바꾼다.
- **코드는 적힌 그대로 넣는다.** 코드 블록은 `ruff check`와 `ruff format --check`를 통과한 상태다. 파일 하나를 통째로 보여 주므로 일부만 옮기지 않는다.
- **테스트를 먼저 쓴다.** Task마다 테스트 작성 → 실패 확인 → 구현 → 통과 확인 → 커밋 순서다. "실패한다"고 적힌 단계에서 통과하거나 "통과한다"고 적힌 단계에서 실패하면 멈추고 사용자에게 알린다.
- **샘플과 기준값을 고치지 않는다.** `tests/fixtures/`의 파일과 테스트에 적힌 기대값은 기준이다. 테스트가 실패하면 코드를 고친다. 샘플의 오탈자(`합께`, `패덜`)는 일부러 넣은 것이다.
- **커밋은 `main`에 바로 하고 푸시한다.** 브랜치와 PR을 만들지 않는다. `git add`에는 파일 경로를 하나씩 적고 `git add -A`와 `git add .`을 쓰지 않는다. 커밋 메시지는 각 Task의 마지막 단계에 적힌 것을 쓴다.
- **공개 저장소다.** 사내 문서, 사내 주소, 인증 정보, 사용자 ID를 코드·테스트·커밋·로그에 넣지 않는다. 명령줄 결과 JSON에는 문서 본문이 들어가므로 `out/` 아래에만 쓰고 커밋하지 않는다.
- **Python 3.10에서 동작해야 한다.** `match` 문, `X | Y` 타입 표기의 런타임 사용, `tomllib`, `typing.Self`처럼 3.10 뒤에 생겼거나 3.10에서 다르게 동작하는 기능을 쓰지 않는다. 이 계획의 코드는 `Optional`, `Union`과 `from __future__ import annotations`를 쓴다.
- **정책을 임의로 정하지 않는다.** 설계와 이 계획에 없는 동작이 필요해지면 사용자에게 묻는다.

## 파일 구성

| 파일 | 맡는 일 | Task |
|---|---|---|
| `pyproject.toml` | 패키지 정의, pytest와 ruff 설정 | 1 |
| `constraints.txt` | 테스트를 돌려 본 정확한 버전 | 1 |
| `.gitattributes` | `tests/fixtures/**`의 줄 끝을 LF로 고정 | 1 |
| `.gitignore` | `out/` 추가 | 1 |
| `config/example.env` | 환경변수 자리표시자 | 1 |
| `app/models/document.py` | 문서, 요소, 위치 정보 | 2 |
| `app/models/findings.py` | 발견 항목, 번역본 점검 결과, 전체 결과 | 3 |
| `app/parsing/reader.py` | 파일 → 줄 목록, sha256 | 4 |
| `app/parsing/line_parser.py` | 줄 목록 → 요소 목록과 발견 항목, 줄 누락 검사 | 5~9 |
| `app/parsing/tokens.py` | 숫자 표기 해석, 토큰 추출, 토큰 비교 | 11~13 |
| `app/parsing/translation_check.py` | 원문과 번역본의 짝짓기, 토큰 비교 결과 | 14 |
| `app/parsing/quality.py` | 발견 항목 → 결과 상태, 막힌 요소 | 16 |
| `app/parsing/ingest.py` | 전체 흐름. 내부 오류를 `FAILED`로 바꾼다 | 17 |
| `app/parsing/__main__.py` | 명령줄 | 18 |
| `tests/conftest.py` | 샘플 파일 경로 픽스처 | 9 |
| `tests/parsing/conftest.py` | `parse`, `make_document` 픽스처 | 5 |
| `tests/models/`, `tests/parsing/` | 테스트 | 2~18 |
| `docs/INHOUSE_CHECK.md` | 사내 확인 절차 | 19 |
| `CLAUDE.md` | 현재 상태와 명령어 | 19 |

설계 §9의 파일 구성과 다른 점은 두 가지다. `constraints.txt`가 더 있고(설계 §9의 "버전을 고정한다"를 이 파일로 한다), 테스트 폴더에 `tests/models/`와 `conftest.py` 두 개가 더 있다.

`line_parser.py`와 `tokens.py`는 여러 Task에 걸쳐 자란다. 그 Task들은 "무엇이 바뀌는지"를 먼저 적고 파일 전체를 다시 보여 준다. 파일을 통째로 바꿔 넣으면 된다.

## 설계 문서에 없어서 계획에서 정한 동작

설계가 정하지 않은 세부를 구현하면서 아래처럼 정했다. 모두 테스트로 고정되어 있다. 바꾸려면 테스트와 함께 바꾸고 사용자에게 알린다.

**모델**

- 결과는 문서를 `documents` 튜플로 갖는다. 주 문서가 먼저, 원문이 그다음이다.
- 주 문서의 `variant`는 원문 언어가 `ko`이면 `source`, 아니면 `translated`다. 주 문서의 `language`는 항상 `ko`다.
- 실패 정보는 `Failure(reason, document)`다. `document`는 어느 파일인지(`translated` / `source`)이고, 내부 오류일 때는 비운다.
- 상세의 토큰은 문자열로 적는다: `num:<적힌 그대로>`, `unit:<단위>`(정규화한 꼴), `sym:±`, `sym:~`, `sym:neg`, `code:<코드>`.

**파서**

- 페이지 마커 자신의 `section_path`는 바로 앞 헤딩까지의 경로다.
- 규칙 8(미분류) 중 코드 펜스(` ``` `, `~~~`), `>` 인용, 구분선(`---`, `***`, `___`), HTML 태그 줄은 규칙 6(목록 항목)보다 먼저 검사한다. 그러지 않으면 `---`와 `***`가 목록 항목으로 읽힌다.
- 표 발견 항목의 줄 번호는 어긋난 그 행의 줄이다.
- 페이지 마커가 하나 있고 다른 줄이 있으면 정상 문서다. 빈 줄뿐인 파일만 `EMPTY_DOCUMENT`다.

**토큰**

- 정규화는 NFKC에 두 글자를 더 접는다: U+2212(−) → `-`, U+301C(〜) → `~`. NFKC는 이 둘을 바꾸지 않는다.
- 코드 구간은 ASCII 영문자에서 시작한다. `Bánh1`에서는 `nh1`이 코드로 나온다. 양쪽 문서에 같은 글자가 있으면 일치하고, 한쪽에만 있으면 불일치로 드러나므로 그대로 둔다.

**번역본 점검**

- 뼈대의 짝(페이지 마커끼리, 헤딩끼리)도 짝 목록에 `match`로 넣는다. 헤딩은 제목의 토큰을 비교한다. 뼈대를 맞추는 열쇠는 헤딩 단계와 조항 번호다.
- 뼈대가 다른 구간에 뼈대 요소가 들어 있으면 그 구간 전체를 `SKELETON_MISMATCH`로 짝 없음에 둔다.
- 이미지 ID가 다르면 그 이미지 한 쌍만 `SEGMENT_UNALIGNED`로 짝 없음에 둔다. 구간의 다른 요소는 짝짓는다.
- 표의 모양이 다르면 `TABLE_SHAPE_MISMATCH`를 내고 짝 없음에 두며, 셀은 하나도 비교하지 않는다.
- 구간에 걸린 발견 항목은 `document="translated"`로 내고, `element_ids`에 번역본 쪽, `counterpart_element_ids`에 원문 쪽 요소를 적는다.
- `NUMBER_FORMAT_AMBIGUOUS`는 표기에 맞지 않는 숫자가 있는 쪽 문서에 붙이고 토큰 값은 적지 않는다.
- 셀의 줄 번호는 `표의 line_start + 1 + 행 번호`다(머리글이 0행, 구분 줄이 그다음 줄).

**품질과 흐름**

- `blocked_element_ids(문서, 발견 항목)`는 그 문서에서 막힌 요소 ID를 돌려준다. 범위가 문서인 코드는 모든 요소를 막는다. 그 밖에는 발견 항목이 가리키는 문서에서는 `element_ids`를, 상대 문서에서는 `counterpart_element_ids`를 막는다. 등급이 "참고"인 것은 아무것도 막지 않는다.
- `ingest()`에 원문 언어 `ko`와 원문 파일을 함께 주면 `ValueError`를 낸다. 호출하는 쪽의 잘못이기 때문이다. 명령줄은 `ingest()`를 부르기 전에 사용법 오류(종료 코드 2)로 처리한다.
- 로그는 `status:` 줄 다음에 `findings:` 줄을 쓴다. 내부 오류는 예외의 종류와 코드 위치만 쓴다. 예외 메시지는 문서 본문을 인용할 수 있으므로 쓰지 않는다.

## 구현 전에 알아 둘 열린 문제

- **번역본 쪽이 빈 구간.** 원문에만 있는 요소 때문에 생긴 `SEGMENT_UNALIGNED`는 `element_ids`가 비고 줄 범위도 없다. 번역본에는 막을 요소가 없다. 이 경우를 판정에서 어떻게 다룰지는 단위 ④에서 정한다(설계 §11).
- **Python 3.10에서만 설치되는 패키지.** pytest는 3.10에서 `exceptiongroup`과 `tomli`를 더 설치한다. 3.14에는 설치되지 않아 `constraints.txt`에 넣지 못했다. 사내에서 설치된 버전을 적어 온다.

---

### Task 1: 프로젝트 뼈대

**Files:**
- Create: `pyproject.toml`, `constraints.txt`, `.gitattributes`, `config/example.env`
- Create: `app/__init__.py`, `app/models/__init__.py`, `app/parsing/__init__.py` (빈 파일)
- Modify: `.gitignore` (끝에 덧붙인다)

- [ ] **Step 1: Python 버전을 확인하고 가상환경을 만든다**

```bash
python --version
python -m venv .venv
```

Expected: `Python 3.10` 이상의 버전이 나온다(사내는 `Python 3.10.11`). `.venv/` 폴더가 생긴다. `.venv/`는 이미 `.gitignore`에 있다.

- [ ] **Step 2: `pyproject.toml`을 만든다**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "doc-compare"
version = "0.1.0"
description = "Checklist-based document compliance checking (PoC)"
requires-python = ">=3.10"
dependencies = ["pydantic>=2.7,<3"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
target-version = "py310"
line-length = 100
# ruff also formats Python code blocks inside Markdown; the documents are not ruff's to rewrite
extend-exclude = ["*.md"]

[tool.ruff.lint]
select = ["E", "F", "I", "B"]
```

`pythonpath = ["."]`는 pytest가 저장소 루트의 `app` 패키지를 찾게 한다. `target-version = "py310"`은 ruff가 3.10에서 쓸 수 없는 문법을 잡게 한다. `extend-exclude = ["*.md"]`가 없으면 ruff가 `docs/` 문서 안의 Python 코드 블록까지 고치려 한다.

- [ ] **Step 3: `constraints.txt`를 만든다**

```text
# Exact versions the test suite was run with (spec section 9: versions are pinned).
# Use:  python -m pip install -e ".[dev]" -c constraints.txt
# Every version below supports Python 3.10 and has a permissive licence (see the plan, Task 1).
# On Python 3.10 pytest also installs exceptiongroup and tomli. They are not listed because
# they were not installed where these versions were checked (Python 3.14).
annotated-types==0.8.0
colorama==0.4.6
iniconfig==2.3.1
packaging==26.3
pluggy==1.7.0
pydantic==2.13.0
pydantic-core==2.46.0
pygments==2.21.0
pytest==9.2.0
ruff==0.17.4
typing-extensions==4.16.0
typing-inspection==0.4.5
```

`pyproject.toml`에는 범위를 두고 정확한 버전은 이 파일에 둔다. 도입 전에 확인한 내용(D-009)은 아래와 같다. 모두 PyPI의 메타데이터에서 읽었다.

| 패키지 | 버전 | Requires-Python | 라이선스 | 용도 |
|---|---|---|---|---|
| pydantic | 2.13.0 | >=3.9 | MIT | 실행 |
| pydantic-core | 2.46.0 | >=3.9 | MIT | pydantic이 요구 |
| typing-extensions | 4.16.0 | >=3.9 | PSF-2.0 | pydantic이 요구 |
| annotated-types | 0.8.0 | >=3.10 | MIT | pydantic이 요구 |
| typing-inspection | 0.4.5 | >=3.10 | MIT | pydantic이 요구 |
| pytest | 9.2.0 | >=3.10 | MIT | 개발 |
| pluggy | 1.7.0 | >=3.10 | MIT | pytest가 요구 |
| iniconfig | 2.3.1 | >=3.10 | MIT | pytest가 요구 |
| packaging | 26.3 | >=3.9 | Apache-2.0 OR BSD-2-Clause | pytest가 요구 |
| pygments | 2.21.0 | >=3.9 | BSD-2-Clause | pytest가 요구 |
| colorama | 0.4.6 | 2.7, 3.7 이상 | BSD-3-Clause | pytest가 Windows에서 요구 |
| ruff | 0.17.4 | >=3.7 | MIT | 개발 |

- [ ] **Step 4: `.gitattributes`를 만든다**

```text
# Test fixtures are compared line by line and hashed: keep LF on every platform.
tests/fixtures/** text eol=lf
```

`sha256`은 파일 바이트로 계산하므로 줄 끝이 바뀌면 해시가 바뀐다. 이 설정은 다음에 체크아웃할 때부터 적용되고, 이미 받아 둔 파일은 바꾸지 않는다. 테스트는 CRLF와 LF 어느 쪽에서도 통과한다.

- [ ] **Step 5: `.gitignore` 끝에 `out/`을 덧붙인다**

```text
# 명령줄 결과(JSON에 문서 본문이 들어간다)
out/
```

- [ ] **Step 6: `config/example.env`를 만든다**

```text
# Copy to .env and fill in the real values there. This repository is public:
# only placeholders belong in this file.
DS_API_BASE_URL=https://llm-gateway.example.invalid/v1
DS_CREDENTIAL=replace-me
DS_SYSTEM_NAME=replace-me
DS_USER_ID=replace-me
DS_LLM_MODEL=replace-me
DS_OPENAI_API_KEY=replace-me
```

단위 ①은 이 값을 읽지 않는다. 단위 ②(LLM 게이트웨이)가 읽을 환경변수의 이름만 미리 적어 둔다. 실제 값은 이 파일에 넣지 않는다.

- [ ] **Step 7: 빈 패키지 파일 세 개를 만든다**

```bash
mkdir -p app/models app/parsing
touch app/__init__.py app/models/__init__.py app/parsing/__init__.py
```


- [ ] **Step 8: 설치한다**

Run: `.venv/Scripts/python -m pip install -e ".[dev]" -c constraints.txt`

Expected: 출력에 `Successfully installed`로 시작하는 줄이 있고, 그 줄에 `doc-compare-0.1.0`, `pydantic-2.13.0`, `pytest-9.2.0`, `ruff-0.17.4`가 들어 있다(pip 새 버전 안내가 그 뒤에 나올 수 있다). Python 3.10에서는 `exceptiongroup`과 `tomli`도 함께 설치된다.

설치가 `constraints.txt`의 버전을 찾지 못해 실패하면 멈추고 사용자에게 알린다. 버전을 임의로 바꾸지 않는다.

- [ ] **Step 9: 패키지가 불러와지는지 확인한다**

Run: `.venv/Scripts/python -c "import app.models, app.parsing, pydantic; print(pydantic.VERSION)"`

Expected: 종료 코드 0, 출력은 아래와 같다.

```text
2.13.0
```

- [ ] **Step 10: pytest와 ruff가 도는지 확인한다**

Run: `.venv/Scripts/python -m pytest -q`

Expected: 종료 코드 5, 출력은 아래와 같다.

```text
no tests ran
```

아직 테스트가 없으므로 종료 코드 5(수집된 테스트 없음)가 맞다.

Run: `.venv/Scripts/python -m ruff check .`

Expected: 종료 코드 0, 출력은 아래와 같다.

```text
All checks passed!
```

Run: `.venv/Scripts/python -m ruff format --check .`

Expected: 종료 코드 0, 출력은 아래와 같다.

```text
3 files already formatted
```

- [ ] **Step 11: 커밋한다**

```bash
git add pyproject.toml constraints.txt .gitattributes .gitignore config/example.env app/__init__.py app/models/__init__.py app/parsing/__init__.py
git commit -m "chore: add project skeleton for unit 1" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 2: 문서 모델

설계 §4. 문서, 일곱 가지 요소, 위치 정보를 Pydantic 모델로 만든다. 모델은 만들어진 뒤 바꿀 수 없고(frozen), 모르는 필드를 받지 않는다(`extra="forbid"`).

**Files:**
- Create: `app/models/document.py`
- Test: `tests/models/test_document.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/models/test_document.py`:

```python
"""Structured document model: IDs, immutability, JSON round trip."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.document import (
    Document,
    Locator,
    Paragraph,
    Table,
    TableCell,
    cell_ref,
    element_id_for,
)


def _locator(line_start: int, line_end: int) -> Locator:
    return Locator(page=9, section_path=("3", "3.2"), line_start=line_start, line_end=line_end)


def _document() -> Document:
    paragraph = Paragraph(
        element_id="e0001", locator=_locator(1, 1), raw="  계량한다.  ", text="계량한다."
    )
    table = Table(
        element_id="e0002",
        locator=_locator(3, 5),
        raw="|항목|기준|\n|---|---|\n|중량|±1.0%|",
        text="항목 | 기준\n중량 | ±1.0%",
        table_index=1,
        header=("항목", "기준"),
        rows=((TableCell(row=1, col=1, text="중량"), TableCell(row=1, col=2, text="±1.0%")),),
    )
    return Document(
        doc_id="SOP-SAMPLE",
        version="1",
        variant="source",
        language="ko",
        file_name="sample.md",
        sha256="0" * 64,
        elements=(paragraph, table),
    )


def test_element_id_is_the_position_in_four_digits():
    assert element_id_for(1) == "e0001"
    assert element_id_for(49) == "e0049"


def test_cell_ref_names_the_element_row_and_column():
    assert cell_ref("e0017", 2, 3) == "e0017:r2c3"
    assert cell_ref("e0017", 0, 1) == "e0017:r0c1"  # row 0 is the header


def test_models_are_frozen():
    document = _document()
    with pytest.raises(ValidationError):
        document.elements[0].text = "다른 문장"
    with pytest.raises(ValidationError):
        document.version = "2"


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        Locator(page=1, section_path=(), line_start=1, line_end=1, bbox=(0, 0, 1, 1))


def test_document_survives_a_json_round_trip():
    document = _document()
    restored = Document.model_validate_json(document.model_dump_json())
    assert restored == document
    assert [type(element) for element in restored.elements] == [Paragraph, Table]
    assert restored.elements[1].rows[0][1].text == "±1.0%"


def test_an_element_of_unknown_kind_is_rejected():
    data = _document().model_dump()
    data["elements"][0]["kind"] = "footnote"
    with pytest.raises(ValidationError):
        Document.model_validate(data)
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/models/test_document.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ModuleNotFoundError: No module named 'app.models.document'
1 error
```

- [ ] **Step 3: 모델을 구현한다**

`app/models/document.py`:

```python
"""Structured document model: a flat, ordered list of elements with locators."""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["ko", "vi", "en", "zh"]
Variant = Literal["translated", "source"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Locator(FrozenModel):
    page: Optional[int]
    section_path: tuple[str, ...]
    line_start: int
    line_end: int


class ElementBase(FrozenModel):
    element_id: str
    locator: Locator
    raw: str
    text: str


class PageMarker(ElementBase):
    kind: Literal["page_marker"] = "page_marker"
    page: int


class Heading(ElementBase):
    kind: Literal["heading"] = "heading"
    level: int
    number: Optional[str]
    title: str


class Paragraph(ElementBase):
    kind: Literal["paragraph"] = "paragraph"


class ListItem(ElementBase):
    kind: Literal["list_item"] = "list_item"
    marker: str


class TableCell(FrozenModel):
    row: int
    col: int
    text: str


class Table(ElementBase):
    kind: Literal["table"] = "table"
    table_index: int
    header: tuple[str, ...]
    rows: tuple[tuple[TableCell, ...], ...]


class Image(ElementBase):
    kind: Literal["image"] = "image"
    image_id: str
    file_name: str
    title: str


class Unclassified(ElementBase):
    kind: Literal["unclassified"] = "unclassified"


Element = Annotated[
    Union[PageMarker, Heading, Paragraph, ListItem, Table, Image, Unclassified],
    Field(discriminator="kind"),
]


class Document(FrozenModel):
    doc_id: str
    version: str
    variant: Variant
    language: Language
    file_name: str
    sha256: str
    elements: tuple[Element, ...]


def element_id_for(index: int) -> str:
    """1-based position in the document -> 'e0001'."""
    return f"e{index:04d}"


def cell_ref(element_id: str, row: int, col: int) -> str:
    """Reference to one table cell, e.g. 'e0017:r2c3'. The header row is row 0."""
    return f"{element_id}:r{row}c{col}"
```

`Element`는 `kind`로 갈리는 구별 유니온이다. JSON에서 다시 읽을 때 `kind` 값으로 어느 요소인지 정한다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/models/test_document.py -q`

Expected: 마지막 줄이 `6 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `6 passed`, `All checks passed!`, `5 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/models/test_document.py app/models/document.py
git commit -m "feat: add document and element models" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 3: 발견 항목과 결과 모델

설계 §6.4, §7.1, §7.2. 발견 항목 코드 14개와 등급, 번역본 점검 결과, 전체 결과를 만든다. 등급은 코드가 정한다(D-013). 호출하는 쪽이 등급을 고르지 못하게 `new_finding()`으로만 만든다.

**Files:**
- Create: `app/models/findings.py`
- Test: `tests/models/test_findings.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/models/test_findings.py`:

```python
"""Findings and the ingest result."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from app.models.findings import (
    DOCUMENT_SCOPE_CODES,
    INFO_CODES,
    Failure,
    FindingCode,
    IngestResult,
    new_finding,
)

ALL_CODES = get_args(FindingCode)


def test_there_are_fourteen_finding_codes():
    assert len(ALL_CODES) == 14
    assert INFO_CODES <= set(ALL_CODES)
    assert DOCUMENT_SCOPE_CODES <= set(ALL_CODES)


@pytest.mark.parametrize("code", ALL_CODES)
def test_the_grade_is_fixed_by_the_code(code):
    expected = "info" if code in {"HEADING_NUMBER_MISMATCH", "IMAGE_PRESENT"} else "review_required"
    assert new_finding(code, "translated").grade == expected


def test_a_finding_points_at_elements_and_lines():
    finding = new_finding(
        "TOKEN_MISMATCH",
        "translated",
        element_ids=("e0017",),
        counterpart_element_ids=("e0017",),
        cell_ref="e0017:r2c3",
        line_start=39,
        line_end=39,
        missing_tokens=("num:1,0",),
        extra_tokens=("num:2.0",),
    )
    assert finding.document == "translated"
    assert finding.cell_ref == "e0017:r2c3"
    assert (finding.line_start, finding.line_end) == (39, 39)


def test_an_unknown_code_is_rejected():
    with pytest.raises(ValidationError):
        new_finding("SOMETHING_ELSE", "translated")


def test_a_failure_names_the_file_unless_the_error_is_internal():
    assert Failure(reason="NOT_UTF8", document="source").document == "source"
    assert Failure(reason="INTERNAL_ERROR").document is None


def test_a_failed_result_carries_no_documents():
    result = IngestResult(
        status="FAILED", parser_version="0.1.0", failure=Failure(reason="EMPTY_DOCUMENT")
    )
    assert result.documents == ()
    assert result.findings == ()
    assert result.translation_check is None
    assert IngestResult.model_validate_json(result.model_dump_json()) == result
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/models/test_findings.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ModuleNotFoundError: No module named 'app.models.findings'
1 error
```

- [ ] **Step 3: 모델을 구현한다**

`app/models/findings.py`:

```python
"""Findings, translation-check results and the overall ingest result.

These objects point at documents by element_id; they are never stored inside a Document.
"""

from __future__ import annotations

from typing import Literal, Optional

from app.models.document import Document, FrozenModel, Variant

Status = Literal["FAILED", "REVIEW_REQUIRED", "OK"]
Grade = Literal["review_required", "info"]
FindingCode = Literal[
    "UNCLASSIFIED_LINE",
    "AMBIGUOUS_LIST_OR_NEGATIVE",
    "TABLE_ROW_WIDTH_MISMATCH",
    "NO_PAGE_MARKER",
    "CONTENT_BEFORE_FIRST_PAGE",
    "PAGE_NUMBER_NOT_INCREASING",
    "SOURCE_NOT_PROVIDED",
    "SKELETON_MISMATCH",
    "SEGMENT_UNALIGNED",
    "TABLE_SHAPE_MISMATCH",
    "TOKEN_MISMATCH",
    "NUMBER_FORMAT_AMBIGUOUS",
    "HEADING_NUMBER_MISMATCH",
    "IMAGE_PRESENT",
]
FailureReason = Literal["FILE_UNREADABLE", "NOT_UTF8", "EMPTY_DOCUMENT", "INTERNAL_ERROR"]

INFO_CODES: frozenset[str] = frozenset({"HEADING_NUMBER_MISMATCH", "IMAGE_PRESENT"})
DOCUMENT_SCOPE_CODES: frozenset[str] = frozenset({"NO_PAGE_MARKER", "SOURCE_NOT_PROVIDED"})


class Finding(FrozenModel):
    code: FindingCode
    grade: Grade
    document: Variant
    element_ids: tuple[str, ...] = ()
    counterpart_element_ids: tuple[str, ...] = ()
    cell_ref: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    missing_tokens: tuple[str, ...] = ()
    extra_tokens: tuple[str, ...] = ()


def new_finding(
    code: FindingCode,
    document: Variant,
    *,
    element_ids: tuple[str, ...] = (),
    counterpart_element_ids: tuple[str, ...] = (),
    cell_ref: Optional[str] = None,
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
    missing_tokens: tuple[str, ...] = (),
    extra_tokens: tuple[str, ...] = (),
) -> Finding:
    """Build a finding; the grade is fixed by the code (D-013)."""
    grade: Grade = "info" if code in INFO_CODES else "review_required"
    return Finding(
        code=code,
        grade=grade,
        document=document,
        element_ids=element_ids,
        counterpart_element_ids=counterpart_element_ids,
        cell_ref=cell_ref,
        line_start=line_start,
        line_end=line_end,
        missing_tokens=missing_tokens,
        extra_tokens=extra_tokens,
    )


class PairResult(FrozenModel):
    translated_ref: str
    source_ref: str
    status: Literal["match", "token_mismatch"]
    missing_tokens: tuple[str, ...] = ()
    extra_tokens: tuple[str, ...] = ()


class UnpairedSegment(FrozenModel):
    reason: Literal["SKELETON_MISMATCH", "SEGMENT_UNALIGNED", "TABLE_SHAPE_MISMATCH"]
    translated_element_ids: tuple[str, ...]
    source_element_ids: tuple[str, ...]


class TranslationCheck(FrozenModel):
    pairs: tuple[PairResult, ...]
    unpaired: tuple[UnpairedSegment, ...]


class Failure(FrozenModel):
    reason: FailureReason
    document: Optional[Variant] = None  # which file; None for an internal error


class IngestResult(FrozenModel):
    status: Status
    parser_version: str
    failure: Optional[Failure] = None
    documents: tuple[Document, ...] = ()
    findings: tuple[Finding, ...] = ()
    translation_check: Optional[TranslationCheck] = None
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/models/test_findings.py -q`

Expected: 마지막 줄이 `19 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `25 passed`, `All checks passed!`, `7 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/models/test_findings.py app/models/findings.py
git commit -m "feat: add finding and ingest result models" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 4: 파일 읽기

설계 §3. 파일을 UTF-8로 읽어 줄 목록과 `sha256`을 돌려준다. 앞머리 BOM은 무시하고, CRLF와 LF를 모두 받는다. 해시는 파일 바이트 그대로 계산한다. 읽을 수 없는 파일은 예외가 아니라 `error` 값으로 알린다.

**Files:**
- Create: `app/parsing/reader.py`
- Test: `tests/parsing/test_reader.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/parsing/test_reader.py`:

```python
"""Reading a file into lines: encoding, line endings, hash, expected failures."""

from __future__ import annotations

import hashlib

from app.parsing.reader import read_lines

TEXT = "[PAGE 1]\n\n## 1. 개요\n\n본문이다.\n"


def test_lines_and_hash_of_a_plain_file(tmp_path):
    path = tmp_path / "sample.md"
    path.write_bytes(TEXT.encode("utf-8"))
    result = read_lines(path)
    assert result.error is None
    assert result.file_name == "sample.md"
    assert result.lines == ("[PAGE 1]", "", "## 1. 개요", "", "본문이다.")
    assert result.sha256 == hashlib.sha256(TEXT.encode("utf-8")).hexdigest()


def test_crlf_gives_the_same_lines_as_lf(tmp_path):
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes(TEXT.encode("utf-8"))
    crlf.write_bytes(TEXT.replace("\n", "\r\n").encode("utf-8"))
    assert read_lines(crlf).lines == read_lines(lf).lines
    assert read_lines(crlf).sha256 != read_lines(lf).sha256  # the hash is of the raw bytes


def test_a_bom_is_ignored_but_hashed(tmp_path):
    data = b"\xef\xbb\xbf" + TEXT.encode("utf-8")
    path = tmp_path / "bom.md"
    path.write_bytes(data)
    result = read_lines(path)
    assert result.lines[0] == "[PAGE 1]"
    assert result.sha256 == hashlib.sha256(data).hexdigest()


def test_a_missing_last_newline_changes_nothing(tmp_path):
    path = tmp_path / "no_newline.md"
    path.write_bytes(TEXT.rstrip("\n").encode("utf-8"))
    assert read_lines(path).lines == ("[PAGE 1]", "", "## 1. 개요", "", "본문이다.")


def test_a_missing_file_is_unreadable(tmp_path):
    result = read_lines(tmp_path / "nothing.md")
    assert result.error == "FILE_UNREADABLE"
    assert result.sha256 is None
    assert result.lines == ()


def test_a_directory_is_unreadable(tmp_path):
    assert read_lines(tmp_path).error == "FILE_UNREADABLE"


def test_bytes_that_are_not_utf8_are_reported(tmp_path):
    path = tmp_path / "cp949.md"
    path.write_bytes("본문이다.".encode("cp949"))
    result = read_lines(path)
    assert result.error == "NOT_UTF8"
    assert result.lines == ()
    assert result.sha256 is not None


def test_a_file_without_text_is_empty(tmp_path):
    for name, data in [("empty.md", b""), ("blank.md", b"\n  \n\t\r\n")]:
        path = tmp_path / name
        path.write_bytes(data)
        assert read_lines(path).error == "EMPTY_DOCUMENT"
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_reader.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ModuleNotFoundError: No module named 'app.parsing.reader'
1 error
```

- [ ] **Step 3: 구현한다**

`app/parsing/reader.py`:

```python
"""Read an input file into lines. Expected input problems are returned, not raised."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.models.findings import FailureReason

_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class ReadResult:
    file_name: str
    sha256: Optional[str]
    lines: tuple[str, ...]
    error: Optional[FailureReason]


def read_lines(path: Path) -> ReadResult:
    """Decode as UTF-8 (BOM ignored), accept CRLF and LF, hash the raw bytes."""
    file_name = path.name
    try:
        data = path.read_bytes()
    except OSError:
        return ReadResult(file_name=file_name, sha256=None, lines=(), error="FILE_UNREADABLE")
    digest = hashlib.sha256(data).hexdigest()
    body = data[len(_BOM) :] if data.startswith(_BOM) else data
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return ReadResult(file_name=file_name, sha256=digest, lines=(), error="NOT_UTF8")
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not any(line.strip() for line in lines):
        return ReadResult(file_name=file_name, sha256=digest, lines=(), error="EMPTY_DOCUMENT")
    return ReadResult(file_name=file_name, sha256=digest, lines=tuple(lines), error=None)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_reader.py -q`

Expected: 마지막 줄이 `8 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `33 passed`, `All checks passed!`, `9 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/parsing/test_reader.py app/parsing/reader.py
git commit -m "feat: read a file into lines with its sha256" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 5: 파서 — 빈 줄, 페이지 마커, 헤딩, 문단

설계 §5의 규칙 1, 2, 3, 7과 §4.3, §5.3. 형식이 어긋난 `[PAGE x]`와 공백 없는 `##제목`은 미분류로 둔다(규칙 8의 일부). 표, 이미지, 목록은 다음 Task들에서 넣는다. 이 Task가 끝난 시점에는 그런 줄이 문단으로 읽힌다.

**Files:**
- Create: `app/parsing/line_parser.py`
- Create: `tests/parsing/conftest.py`
- Test: `tests/parsing/test_parser_basics.py`

- [ ] **Step 1: 테스트용 픽스처를 만든다**

`tests/parsing/conftest.py`:

```python
"""Small builders for parser tests."""

from __future__ import annotations

from typing import Callable, Sequence

import pytest

from app.models.document import Document, Element, Language, Variant
from app.models.findings import Finding
from app.parsing.line_parser import parse_lines

Parsed = tuple[tuple[Element, ...], tuple[Finding, ...]]


@pytest.fixture
def parse() -> Callable[..., Parsed]:
    """parse("line 1\\nline 2") -> (elements, findings)"""

    def _parse(text: str, variant: Variant = "source") -> Parsed:
        return parse_lines(tuple(text.split("\n")), variant)

    return _parse


@pytest.fixture
def make_document() -> Callable[..., Document]:
    """make_document(lines, "translated", "ko") -> Document built by the parser"""

    def _make(lines: Sequence[str], variant: Variant, language: Language) -> Document:
        elements, _ = parse_lines(tuple(lines), variant)
        return Document(
            doc_id="SOP-SAMPLE",
            version="1",
            variant=variant,
            language=language,
            file_name="memory.md",
            sha256="0" * 64,
            elements=elements,
        )

    return _make
```

`parse("줄1", "줄2")`는 줄 목록을 파서에 넣고 `(요소 목록, 발견 항목 목록)`을 돌려준다. `make_document`는 줄 목록으로 `Document`를 만든다. Task 14부터 쓴다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/parsing/test_parser_basics.py`:

```python
"""Blank lines, page markers, headings, paragraphs and where each element is."""

from __future__ import annotations

import pytest

from app.parsing.line_parser import clean_text


def test_blank_lines_make_no_element(parse):
    elements, _ = parse("\n   \n\t\n본문이다.\n\n")
    assert [element.kind for element in elements] == ["paragraph"]
    assert (elements[0].locator.line_start, elements[0].locator.line_end) == (4, 4)


def test_element_ids_follow_the_order_in_the_file(parse):
    elements, _ = parse("[PAGE 1]\n## 1. 개요\n첫 문단이다.\n\n둘째 문단이다.")
    assert [element.element_id for element in elements] == ["e0001", "e0002", "e0003", "e0004"]
    assert [element.locator.line_start for element in elements] == [1, 2, 3, 5]


@pytest.mark.parametrize("line, page", [("[PAGE 8]", 8), ("[PAGE9]", 9), ("  [PAGE 10]  ", 10)])
def test_page_marker(parse, line, page):
    elements, findings = parse(line)
    assert elements[0].kind == "page_marker"
    assert elements[0].page == page
    assert elements[0].locator.page == page
    assert elements[0].raw == line
    assert findings == ()


def test_a_page_marker_sets_the_page_of_what_follows(parse):
    elements, _ = parse("[PAGE 8]\n첫 쪽 문단이다.\n[PAGE 9]\n다음 쪽 문단이다.")
    assert [element.locator.page for element in elements] == [8, 8, 9, 9]


@pytest.mark.parametrize("line", ["[PAGE x]", "[PAGE 8] 본문", "[page 8]", "[PAGE  8]", "[PAGE 8"])
def test_a_malformed_page_marker_is_unclassified(parse, line):
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "unclassified"
    assert elements[1].text == line
    assert elements[1].locator.page == 1  # it did not change the page
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"]
    assert findings[0].grade == "review_required"
    assert findings[0].element_ids == ("e0002",)
    assert (findings[0].line_start, findings[0].line_end) == (2, 2)


@pytest.mark.parametrize(
    "line, level, number, title",
    [
        ("## 3. 제조 작업 절차", 2, "3", "제조 작업 절차"),
        ("### 3.1 배합 전 원료 투입 List 조회", 3, "3.1", "배합 전 원료 투입 List 조회"),
        ("#### 3.1.2. 세부 절차", 4, "3.1.2", "세부 절차"),
        ("# 개요", 1, None, "개요"),
        ("## 2024년 생산 계획", 2, None, "2024년 생산 계획"),
    ],
)
def test_heading(parse, line, level, number, title):
    elements, findings = parse("[PAGE 1]\n" + line)
    heading = elements[1]
    assert heading.kind == "heading"
    assert (heading.level, heading.number, heading.title) == (level, number, title)
    assert heading.text == line.lstrip("# ")
    assert findings == ()


def test_the_section_path_follows_the_headings(parse):
    text = "\n".join(
        [
            "[PAGE 1]",
            "첫 제목보다 앞에 있는 문단이다.",
            "## 3. 제조",
            "### 3.1 조회",
            "문단 가.",
            "### 3.2 계량",
            "문단 나.",
            "## 4. 기록",
            "문단 다.",
            "# 부록",
            "문단 라.",
        ]
    )
    elements, _ = parse(text)
    paths = {element.text: element.locator.section_path for element in elements}
    assert paths["첫 제목보다 앞에 있는 문단이다."] == ()
    assert paths["3.1 조회"] == ("3", "3.1")  # a heading is inside its own section
    assert paths["문단 가."] == ("3", "3.1")
    assert paths["문단 나."] == ("3", "3.2")
    assert paths["문단 다."] == ("4",)
    assert paths["문단 라."] == ("부록",)  # no number: the title is used


@pytest.mark.parametrize("line", ["##제목", "####### 일곱 단계", "#", "##"])
def test_a_malformed_heading_is_unclassified(parse, line):
    elements, findings = parse("[PAGE 1]\n## 1. 개요\n" + line + "\n문단이다.")
    assert elements[2].kind == "unclassified"
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"]
    assert elements[3].locator.section_path == ("1",)  # the section did not change


def test_one_line_is_one_paragraph(parse):
    elements, _ = parse("[PAGE 1]\n첫 줄이다.\n둘째 줄이다.")
    assert [element.kind for element in elements[1:]] == ["paragraph", "paragraph"]
    assert [element.text for element in elements[1:]] == ["첫 줄이다.", "둘째 줄이다."]


def test_raw_keeps_the_line_and_text_is_trimmed(parse):
    line = "  **주의:**LotNo.가 없는 원료는 투입하지 않는다.  "
    elements, _ = parse("[PAGE 1]\n" + line)
    assert elements[1].raw == line
    assert elements[1].text == "주의:LotNo.가 없는 원료는 투입하지 않는다."


def test_typos_are_kept(parse):
    elements, _ = parse("[PAGE 1]\n온도와 상대 습도를 합께 기재한다.")
    assert "합께" in elements[1].text
    assert "합께" in elements[1].raw


@pytest.mark.parametrize(
    "value, expected",
    [
        ("**굵게**", "굵게"),
        ("**주의:**본문", "주의:본문"),
        ("**가** 와 **나**", "가 와 나"),
        ("가<br>나", "가\n나"),
        ("가<BR/>나<br />다", "가\n나\n다"),
        ("짝이 없는 ** 표시", "짝이 없는 ** 표시"),
        ("2 * 3", "2 * 3"),
    ],
)
def test_clean_text(value, expected):
    assert clean_text(value) == expected
```

- [ ] **Step 3: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_parser_basics.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ModuleNotFoundError: No module named 'app.parsing.line_parser'
```

`conftest.py`가 아직 없는 모듈을 불러오므로 수집 단계에서 멈춘다.

- [ ] **Step 4: 파서를 구현한다**

`app/parsing/line_parser.py`:

```python
"""Hand-written line parser for rag_ko.md / rag.md (D-010).

Each non-blank line is classified by the first matching rule. Nothing is guessed:
lines that look structural but fit no rule become `unclassified` elements with a finding.
"""

from __future__ import annotations

import re
from typing import Optional

from app.models.document import (
    Element,
    Heading,
    Locator,
    PageMarker,
    Paragraph,
    Unclassified,
    Variant,
    element_id_for,
)
from app.models.findings import Finding, FindingCode, new_finding

_PAGE_RE = re.compile(r"\[PAGE ?(\d+)\]")
_HEADING_RE = re.compile(r"(#{1,6}) +(\S.*)")
_HEADING_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)*)\.?\s+(\S.*)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def clean_text(value: str) -> str:
    """Strip paired ** and turn <br> into newlines. Characters are never changed."""
    return _BOLD_RE.sub(r"\1", _BR_RE.sub("\n", value))


class _Builder:
    def __init__(self, variant: Variant) -> None:
        self.variant: Variant = variant
        self.elements: list[Element] = []
        self.findings: list[Finding] = []
        self.page: Optional[int] = None
        self.headings: list[tuple[int, str]] = []  # (level, label)

    def next_id(self) -> str:
        return element_id_for(len(self.elements) + 1)

    def locator(self, line_start: int, line_end: int) -> Locator:
        return Locator(
            page=self.page,
            section_path=tuple(label for _, label in self.headings),
            line_start=line_start,
            line_end=line_end,
        )

    def add(self, element: Element) -> None:
        self.elements.append(element)

    def flag(self, code: FindingCode, element: Element) -> None:
        self.findings.append(
            new_finding(
                code,
                self.variant,
                element_ids=(element.element_id,),
                line_start=element.locator.line_start,
                line_end=element.locator.line_end,
            )
        )

    def page_marker(self, number: int, line_no: int, raw: str) -> None:
        self.page = number
        self.add(
            PageMarker(
                element_id=self.next_id(),
                locator=self.locator(line_no, line_no),
                raw=raw,
                text=raw.strip(),
                page=number,
            )
        )

    def heading(self, level: int, rest: str, line_no: int, raw: str) -> None:
        match = _HEADING_NUMBER_RE.fullmatch(rest)
        number = match.group(1) if match else None
        title = clean_text(match.group(2) if match else rest)
        while self.headings and self.headings[-1][0] >= level:
            self.headings.pop()
        self.headings.append((level, number if number is not None else title))
        self.add(
            Heading(
                element_id=self.next_id(),
                locator=self.locator(line_no, line_no),
                raw=raw,
                text=clean_text(rest),
                level=level,
                number=number,
                title=title,
            )
        )

    def paragraph(self, stripped: str, line_no: int, raw: str) -> None:
        self.add(
            Paragraph(
                element_id=self.next_id(),
                locator=self.locator(line_no, line_no),
                raw=raw,
                text=clean_text(stripped),
            )
        )

    def unclassified(self, stripped: str, line_no: int, raw: str) -> None:
        element = Unclassified(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=stripped,
        )
        self.add(element)
        self.flag("UNCLASSIFIED_LINE", element)


def parse_lines(
    lines: tuple[str, ...], variant: Variant
) -> tuple[tuple[Element, ...], tuple[Finding, ...]]:
    """Turn file lines into elements plus the findings the parser can see on its own."""
    builder = _Builder(variant)
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        line_no = index + 1
        index += 1

        # 1. blank line
        if not stripped:
            continue

        # 2. page marker
        if stripped.upper().startswith("[PAGE"):
            match = _PAGE_RE.fullmatch(stripped)
            if match:
                builder.page_marker(int(match.group(1)), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 3. heading
        if stripped.startswith("#"):
            match = _HEADING_RE.fullmatch(stripped)
            if match:
                builder.heading(len(match.group(1)), match.group(2), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 7. paragraph: one line is one paragraph
        builder.paragraph(stripped, line_no, raw)

    return tuple(builder.elements), tuple(builder.findings)
```

`_Builder`가 현재 페이지와 헤딩 경로를 들고 다니며 요소에 `element_id`와 `locator`를 붙인다. `parse_lines()`의 반복문은 설계 §5의 규칙 번호를 주석으로 달아 둔다.

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_parser_basics.py -q`

Expected: 마지막 줄이 `31 passed`

- [ ] **Step 6: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `64 passed`, `All checks passed!`, `12 files already formatted`

- [ ] **Step 7: 커밋한다**

```bash
git add tests/parsing/conftest.py tests/parsing/test_parser_basics.py app/parsing/line_parser.py
git commit -m "feat: parse page markers, headings and paragraphs" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 6: 파서 — 페이지와 헤딩의 발견 항목

설계 §5.2와 §7.2. 네 가지 발견 항목을 낸다: `CONTENT_BEFORE_FIRST_PAGE`, `PAGE_NUMBER_NOT_INCREASING`, `NO_PAGE_MARKER`, `HEADING_NUMBER_MISMATCH`. 읽은 값은 고치지 않고 표시만 한다.

**Files:**
- Modify: `app/parsing/line_parser.py`
- Test: `tests/parsing/test_parser_page_heading_findings.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/parsing/test_parser_page_heading_findings.py`:

```python
"""Findings the parser raises about page markers and heading numbers."""

from __future__ import annotations


def _codes(findings):
    return [finding.code for finding in findings]


def test_content_before_the_first_page_marker(parse):
    elements, findings = parse("## 1. 개요\n쪽 표시보다 앞에 있다.\n[PAGE 1]\n쪽 표시 뒤에 있다.")
    assert [element.locator.page for element in elements] == [None, None, 1, 1]
    assert _codes(findings) == ["CONTENT_BEFORE_FIRST_PAGE"]
    assert findings[0].grade == "review_required"
    assert findings[0].element_ids == ("e0001", "e0002")
    assert (findings[0].line_start, findings[0].line_end) == (1, 2)


def test_a_document_that_starts_with_a_page_marker_has_no_such_finding(parse):
    _, findings = parse("\n\n[PAGE 1]\n문단이다.")
    assert findings == ()


def test_a_document_without_any_page_marker(parse):
    elements, findings = parse("## 1. 개요\n문단이다.")
    assert [element.locator.page for element in elements] == [None, None]
    assert _codes(findings) == ["NO_PAGE_MARKER"]  # and no CONTENT_BEFORE_FIRST_PAGE
    assert findings[0].grade == "review_required"
    assert findings[0].element_ids == ()  # it is about the whole document


def test_page_numbers_must_increase(parse):
    elements, findings = parse("[PAGE 8]\n가.\n[PAGE 8]\n나.\n[PAGE 7]\n다.\n[PAGE 9]\n라.")
    assert _codes(findings) == ["PAGE_NUMBER_NOT_INCREASING", "PAGE_NUMBER_NOT_INCREASING"]
    assert [finding.element_ids for finding in findings] == [("e0003",), ("e0005",)]
    assert [finding.line_start for finding in findings] == [3, 5]
    # the marker is still applied as written; nothing is corrected
    assert [element.locator.page for element in elements] == [8, 8, 8, 8, 7, 7, 9, 9]


def test_a_skipped_page_number_is_fine(parse):
    _, findings = parse("[PAGE 8]\n가.\n[PAGE 11]\n나.")
    assert findings == ()


def test_a_heading_number_that_does_not_continue_its_parent(parse):
    _, findings = parse("[PAGE 1]\n## 3. 제조\n### 4.1 조회\n### 3.2 계량")
    assert _codes(findings) == ["HEADING_NUMBER_MISMATCH"]
    assert findings[0].grade == "info"
    assert findings[0].element_ids == ("e0003",)
    assert (findings[0].line_start, findings[0].line_end) == (3, 3)


def test_heading_numbers_that_need_no_remark(parse):
    text = "\n".join(
        [
            "[PAGE 1]",
            "## 3. 제조",
            "### 3.1 조회",
            "#### 3.1.1 조건",
            "## 4. 기록",  # a sibling, not a child of 3
            "### 보관",  # no number
            "#### 4.1 기간",  # the parent has no number to compare with
            "## 31. 부록",
            "### 31.1 양식",
        ]
    )
    _, findings = parse(text)
    assert findings == ()


def test_a_number_that_only_starts_with_the_same_digits_is_a_mismatch(parse):
    _, findings = parse("[PAGE 1]\n## 3. 제조\n### 31.1 조회")
    assert _codes(findings) == ["HEADING_NUMBER_MISMATCH"]


def test_findings_name_the_document_they_are_about(parse):
    _, findings = parse("문단이다.", variant="translated")
    assert [finding.document for finding in findings] == ["translated"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_parser_page_heading_findings.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
FAILED tests/parsing/test_parser_page_heading_findings.py::test_content_before_the_first_page_marker
FAILED tests/parsing/test_parser_page_heading_findings.py::test_a_document_without_any_page_marker
FAILED tests/parsing/test_parser_page_heading_findings.py::test_page_numbers_must_increase
FAILED tests/parsing/test_parser_page_heading_findings.py::test_a_heading_number_that_does_not_continue_its_parent
FAILED tests/parsing/test_parser_page_heading_findings.py::test_a_number_that_only_starts_with_the_same_digits_is_a_mismatch
FAILED tests/parsing/test_parser_page_heading_findings.py::test_findings_name_the_document_they_are_about
6 failed, 3 passed
```

- [ ] **Step 3: 파서를 고친다**

이 단계에서 바뀌는 것:

- `_Builder`에 `seen_page_marker`와 `before_first_page`가 생긴다. 첫 페이지 마커를 만나기 전의 요소를 모아 두었다가, 첫 마커에서 `CONTENT_BEFORE_FIRST_PAGE` 하나로 낸다.
- `page_marker()`가 앞 페이지 번호와 비교해 같거나 작으면 `PAGE_NUMBER_NOT_INCREASING`을 낸다. 번호가 건너뛰는 것은 정상이다.
- `headings`가 `(단계, 경로에 넣을 이름, 조항 번호)` 세 값을 갖는다. `heading()`이 상위 헤딩의 조항 번호와 비교해, 자신의 번호가 `상위 번호 + "."`으로 시작하지 않으면 `HEADING_NUMBER_MISMATCH`를 낸다.
- `parse_lines()`가 끝에서 페이지 마커가 하나도 없으면 `NO_PAGE_MARKER`를 낸다.

`app/parsing/line_parser.py` 전체를 아래 내용으로 바꾼다:

```python
"""Hand-written line parser for rag_ko.md / rag.md (D-010).

Each non-blank line is classified by the first matching rule. Nothing is guessed:
lines that look structural but fit no rule become `unclassified` elements with a finding.
"""

from __future__ import annotations

import re
from typing import Optional

from app.models.document import (
    Element,
    Heading,
    Locator,
    PageMarker,
    Paragraph,
    Unclassified,
    Variant,
    element_id_for,
)
from app.models.findings import Finding, FindingCode, new_finding

_PAGE_RE = re.compile(r"\[PAGE ?(\d+)\]")
_HEADING_RE = re.compile(r"(#{1,6}) +(\S.*)")
_HEADING_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)*)\.?\s+(\S.*)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def clean_text(value: str) -> str:
    """Strip paired ** and turn <br> into newlines. Characters are never changed."""
    return _BOLD_RE.sub(r"\1", _BR_RE.sub("\n", value))


class _Builder:
    def __init__(self, variant: Variant) -> None:
        self.variant: Variant = variant
        self.elements: list[Element] = []
        self.findings: list[Finding] = []
        self.page: Optional[int] = None
        self.seen_page_marker = False
        self.before_first_page: list[Element] = []
        self.headings: list[tuple[int, str, Optional[str]]] = []  # (level, label, number)

    def next_id(self) -> str:
        return element_id_for(len(self.elements) + 1)

    def locator(self, line_start: int, line_end: int) -> Locator:
        return Locator(
            page=self.page,
            section_path=tuple(label for _, label, _ in self.headings),
            line_start=line_start,
            line_end=line_end,
        )

    def add(self, element: Element) -> None:
        self.elements.append(element)
        if not self.seen_page_marker:
            self.before_first_page.append(element)

    def flag(self, code: FindingCode, element: Element) -> None:
        self.findings.append(
            new_finding(
                code,
                self.variant,
                element_ids=(element.element_id,),
                line_start=element.locator.line_start,
                line_end=element.locator.line_end,
            )
        )

    def page_marker(self, number: int, line_no: int, raw: str) -> None:
        previous = self.page
        if not self.seen_page_marker and self.before_first_page:
            self.findings.append(
                new_finding(
                    "CONTENT_BEFORE_FIRST_PAGE",
                    self.variant,
                    element_ids=tuple(e.element_id for e in self.before_first_page),
                    line_start=self.before_first_page[0].locator.line_start,
                    line_end=self.before_first_page[-1].locator.line_end,
                )
            )
        self.seen_page_marker = True
        self.page = number
        element = PageMarker(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=raw.strip(),
            page=number,
        )
        self.add(element)
        if previous is not None and number <= previous:
            self.flag("PAGE_NUMBER_NOT_INCREASING", element)

    def heading(self, level: int, rest: str, line_no: int, raw: str) -> None:
        match = _HEADING_NUMBER_RE.fullmatch(rest)
        number = match.group(1) if match else None
        title = clean_text(match.group(2) if match else rest)
        while self.headings and self.headings[-1][0] >= level:
            self.headings.pop()
        parent_number = self.headings[-1][2] if self.headings else None
        mismatch = (
            number is not None
            and parent_number is not None
            and not number.startswith(parent_number + ".")
        )
        self.headings.append((level, number if number is not None else title, number))
        element = Heading(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=clean_text(rest),
            level=level,
            number=number,
            title=title,
        )
        self.add(element)
        if mismatch:
            self.flag("HEADING_NUMBER_MISMATCH", element)

    def paragraph(self, stripped: str, line_no: int, raw: str) -> None:
        self.add(
            Paragraph(
                element_id=self.next_id(),
                locator=self.locator(line_no, line_no),
                raw=raw,
                text=clean_text(stripped),
            )
        )

    def unclassified(self, stripped: str, line_no: int, raw: str) -> None:
        element = Unclassified(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=stripped,
        )
        self.add(element)
        self.flag("UNCLASSIFIED_LINE", element)


def parse_lines(
    lines: tuple[str, ...], variant: Variant
) -> tuple[tuple[Element, ...], tuple[Finding, ...]]:
    """Turn file lines into elements plus the findings the parser can see on its own."""
    builder = _Builder(variant)
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        line_no = index + 1
        index += 1

        # 1. blank line
        if not stripped:
            continue

        # 2. page marker
        if stripped.upper().startswith("[PAGE"):
            match = _PAGE_RE.fullmatch(stripped)
            if match:
                builder.page_marker(int(match.group(1)), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 3. heading
        if stripped.startswith("#"):
            match = _HEADING_RE.fullmatch(stripped)
            if match:
                builder.heading(len(match.group(1)), match.group(2), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 7. paragraph: one line is one paragraph
        builder.paragraph(stripped, line_no, raw)

    if not builder.seen_page_marker:
        builder.findings.append(new_finding("NO_PAGE_MARKER", variant))
    return tuple(builder.elements), tuple(builder.findings)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_parser_page_heading_findings.py -q`

Expected: 마지막 줄이 `9 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `73 passed`, `All checks passed!`, `13 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/parsing/test_parser_page_heading_findings.py app/parsing/line_parser.py
git commit -m "feat: flag page and heading irregularities" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 7: 파서 — 표

설계 §5의 규칙 4와 §5.1. `|`로 시작하는 줄이 이어지고 둘째 줄이 구분 줄이면 표 하나다. 구분 줄이 없는 `|` 줄은 줄마다 미분류로 둔다. 열 수가 머리글과 다른 행은 읽은 그대로 두고 `TABLE_ROW_WIDTH_MISMATCH`를 낸다.

**Files:**
- Modify: `app/parsing/line_parser.py`
- Test: `tests/parsing/test_parser_tables.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/parsing/test_parser_tables.py`:

```python
"""Tables: one element per table, cells addressed by row and column."""

from __future__ import annotations

import pytest

from app.parsing.line_parser import split_table_row

TABLE = "\n".join(
    [
        "[PAGE 9]",
        "### 3.2 계량",
        "",
        "|확인 항목|확인 방법|판정기준|",
        "|---|---|---|",
        "|품번|List와 원료 Label 대조|일치|",
        "|계량중량|전자저울 계량|배합표 대비 ±1.0% 이내|",
        "",
        "표 다음 문단이다.",
    ]
)


def test_a_table_is_one_element(parse):
    elements, findings = parse(TABLE)
    assert [element.kind for element in elements] == [
        "page_marker",
        "heading",
        "table",
        "paragraph",
    ]
    table = elements[2]
    assert table.element_id == "e0003"
    assert table.table_index == 1
    assert (table.locator.line_start, table.locator.line_end) == (4, 7)
    assert table.locator.page == 9
    assert table.locator.section_path == ("3.2",)
    assert table.header == ("확인 항목", "확인 방법", "판정기준")
    assert findings == ()


def test_cells_carry_their_row_and_column(parse):
    table = parse(TABLE)[0][2]
    assert len(table.rows) == 2
    assert [(cell.row, cell.col) for cell in table.rows[1]] == [(2, 1), (2, 2), (2, 3)]
    assert table.rows[1][2].text == "배합표 대비 ±1.0% 이내"


def test_raw_keeps_the_table_lines_and_text_drops_the_separator(parse):
    table = parse(TABLE)[0][2]
    assert table.raw == "\n".join(TABLE.split("\n")[3:7])
    assert table.text == "\n".join(
        [
            "확인 항목 | 확인 방법 | 판정기준",
            "품번 | List와 원료 Label 대조 | 일치",
            "계량중량 | 전자저울 계량 | 배합표 대비 ±1.0% 이내",
        ]
    )


def test_tables_are_numbered_in_order(parse):
    elements, _ = parse("[PAGE 1]\n|가|나|\n|---|---|\n|1|2|\n\n|다|라|\n|:--|--:|\n|3|4|")
    tables = [element for element in elements if element.kind == "table"]
    assert [table.table_index for table in tables] == [1, 2]
    assert [table.locator.line_start for table in tables] == [2, 6]


def test_a_table_may_have_no_data_rows(parse):
    elements, findings = parse("[PAGE 1]\n|가|나|\n|---|---|")
    assert elements[1].kind == "table"
    assert elements[1].rows == ()
    assert findings == ()


def test_markup_inside_cells_is_cleaned(parse):
    elements, _ = parse("[PAGE 1]\n|**구분**|기준|\n|---|---|\n|온도|2~8℃<br>냉장|")
    table = elements[1]
    assert table.header == ("구분", "기준")
    assert table.rows[0][1].text == "2~8℃\n냉장"
    assert "<br>" in table.raw


def test_a_row_with_a_different_number_of_cells(parse):
    elements, findings = parse("[PAGE 1]\n|가|나|다|\n|---|---|---|\n|1|2|3|\n|4|5|\n|6|7|8|9|")
    table = elements[1]
    assert table.kind == "table"
    assert [len(row) for row in table.rows] == [3, 2, 4]  # kept as written, nothing is padded
    assert [finding.code for finding in findings] == ["TABLE_ROW_WIDTH_MISMATCH"] * 2
    assert [finding.grade for finding in findings] == ["review_required"] * 2
    assert [finding.element_ids for finding in findings] == [("e0002",), ("e0002",)]
    assert [finding.line_start for finding in findings] == [5, 6]


def test_a_separator_with_a_different_number_of_cells(parse):
    _, findings = parse("[PAGE 1]\n|가|나|다|\n|---|---|\n|1|2|3|")
    assert [finding.code for finding in findings] == ["TABLE_ROW_WIDTH_MISMATCH"]
    assert (findings[0].line_start, findings[0].line_end) == (3, 3)


def test_pipe_lines_without_a_separator_are_unclassified(parse):
    elements, findings = parse("[PAGE 1]\n|가|나|\n|1|2|\n문단이다.")
    assert [element.kind for element in elements[1:]] == [
        "unclassified",
        "unclassified",
        "paragraph",
    ]
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"] * 2
    assert [finding.line_start for finding in findings] == [2, 3]


def test_a_single_pipe_line_is_unclassified(parse):
    elements, findings = parse("[PAGE 1]\n|가|나|")
    assert elements[1].kind == "unclassified"
    assert [finding.code for finding in findings] == ["UNCLASSIFIED_LINE"]


@pytest.mark.parametrize(
    "line, cells",
    [
        ("|가|나|", ["가", "나"]),
        ("| 가 | 나 |  ", ["가", "나"]),
        ("|가||다|", ["가", "", "다"]),
        ("|가|나", ["가", "나"]),
        (r"|가|나\|다|", ["가", "나|다"]),
        ("|**가**|1<br>2|", ["가", "1\n2"]),
    ],
)
def test_split_table_row(line, cells):
    assert split_table_row(line) == cells
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_parser_tables.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ImportError: cannot import name 'split_table_row' from 'app.parsing.line_parser'
1 error
```

- [ ] **Step 3: 파서를 고친다**

이 단계에서 바뀌는 것:

- `split_table_row()`와 `_is_separator_row()`가 생긴다. `\|`는 나누지 않는다.
- `_Builder.table()`이 생긴다. 표의 줄 전체를 요소 하나로 만들고 `table_index`를 1부터 매긴다. 머리글은 `header`에, 구분 줄 뒤의 행은 `rows`에 넣는다.
- `_Builder.flag()`가 줄 번호를 따로 받을 수 있다. 표의 발견 항목은 표 전체가 아니라 어긋난 행의 줄을 가리킨다.
- `parse_lines()`에 규칙 4가 들어간다. 헤딩 규칙 다음, 문단 규칙 앞이다.

`app/parsing/line_parser.py` 전체를 아래 내용으로 바꾼다:

```python
"""Hand-written line parser for rag_ko.md / rag.md (D-010).

Each non-blank line is classified by the first matching rule. Nothing is guessed:
lines that look structural but fit no rule become `unclassified` elements with a finding.
"""

from __future__ import annotations

import re
from typing import Optional

from app.models.document import (
    Element,
    Heading,
    Locator,
    PageMarker,
    Paragraph,
    Table,
    TableCell,
    Unclassified,
    Variant,
    element_id_for,
)
from app.models.findings import Finding, FindingCode, new_finding

_PAGE_RE = re.compile(r"\[PAGE ?(\d+)\]")
_HEADING_RE = re.compile(r"(#{1,6}) +(\S.*)")
_HEADING_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)*)\.?\s+(\S.*)")
_SEPARATOR_CELL_RE = re.compile(r":?-+:?")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def clean_text(value: str) -> str:
    """Strip paired ** and turn <br> into newlines. Characters are never changed."""
    return _BOLD_RE.sub(r"\1", _BR_RE.sub("\n", value))


def split_table_row(line: str) -> list[str]:
    """'|a|b| ' -> ['a', 'b']. An escaped pipe (\\|) does not split."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [clean_text(cell.strip().replace("\\|", "|")) for cell in _CELL_SPLIT_RE.split(body)]


def _is_separator_row(line: str) -> bool:
    body = line.strip()
    if not body.startswith("|"):
        return False
    cells = split_table_row(body)
    return bool(cells) and all(_SEPARATOR_CELL_RE.fullmatch(cell) for cell in cells)


class _Builder:
    def __init__(self, variant: Variant) -> None:
        self.variant: Variant = variant
        self.elements: list[Element] = []
        self.findings: list[Finding] = []
        self.page: Optional[int] = None
        self.seen_page_marker = False
        self.before_first_page: list[Element] = []
        self.headings: list[tuple[int, str, Optional[str]]] = []  # (level, label, number)
        self.table_count = 0

    def next_id(self) -> str:
        return element_id_for(len(self.elements) + 1)

    def locator(self, line_start: int, line_end: int) -> Locator:
        return Locator(
            page=self.page,
            section_path=tuple(label for _, label, _ in self.headings),
            line_start=line_start,
            line_end=line_end,
        )

    def add(self, element: Element) -> None:
        self.elements.append(element)
        if not self.seen_page_marker:
            self.before_first_page.append(element)

    def flag(self, code: FindingCode, element: Element, line: Optional[int] = None) -> None:
        self.findings.append(
            new_finding(
                code,
                self.variant,
                element_ids=(element.element_id,),
                line_start=line if line is not None else element.locator.line_start,
                line_end=line if line is not None else element.locator.line_end,
            )
        )

    def page_marker(self, number: int, line_no: int, raw: str) -> None:
        previous = self.page
        if not self.seen_page_marker and self.before_first_page:
            self.findings.append(
                new_finding(
                    "CONTENT_BEFORE_FIRST_PAGE",
                    self.variant,
                    element_ids=tuple(e.element_id for e in self.before_first_page),
                    line_start=self.before_first_page[0].locator.line_start,
                    line_end=self.before_first_page[-1].locator.line_end,
                )
            )
        self.seen_page_marker = True
        self.page = number
        element = PageMarker(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=raw.strip(),
            page=number,
        )
        self.add(element)
        if previous is not None and number <= previous:
            self.flag("PAGE_NUMBER_NOT_INCREASING", element)

    def heading(self, level: int, rest: str, line_no: int, raw: str) -> None:
        match = _HEADING_NUMBER_RE.fullmatch(rest)
        number = match.group(1) if match else None
        title = clean_text(match.group(2) if match else rest)
        while self.headings and self.headings[-1][0] >= level:
            self.headings.pop()
        parent_number = self.headings[-1][2] if self.headings else None
        mismatch = (
            number is not None
            and parent_number is not None
            and not number.startswith(parent_number + ".")
        )
        self.headings.append((level, number if number is not None else title, number))
        element = Heading(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=clean_text(rest),
            level=level,
            number=number,
            title=title,
        )
        self.add(element)
        if mismatch:
            self.flag("HEADING_NUMBER_MISMATCH", element)

    def table(self, block: list[str], line_start: int) -> None:
        self.table_count += 1
        header = split_table_row(block[0])
        rows = [split_table_row(line) for line in block[2:]]
        element = Table(
            element_id=self.next_id(),
            locator=self.locator(line_start, line_start + len(block) - 1),
            raw="\n".join(block),
            text="\n".join(" | ".join(cells) for cells in [header, *rows]),
            table_index=self.table_count,
            header=tuple(header),
            rows=tuple(
                tuple(TableCell(row=r, col=c, text=text) for c, text in enumerate(cells, start=1))
                for r, cells in enumerate(rows, start=1)
            ),
        )
        self.add(element)
        if len(split_table_row(block[1])) != len(header):
            self.flag("TABLE_ROW_WIDTH_MISMATCH", element, line_start + 1)
        for offset, cells in enumerate(rows, start=2):
            if len(cells) != len(header):
                self.flag("TABLE_ROW_WIDTH_MISMATCH", element, line_start + offset)

    def paragraph(self, stripped: str, line_no: int, raw: str) -> None:
        self.add(
            Paragraph(
                element_id=self.next_id(),
                locator=self.locator(line_no, line_no),
                raw=raw,
                text=clean_text(stripped),
            )
        )

    def unclassified(self, stripped: str, line_no: int, raw: str) -> None:
        element = Unclassified(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=stripped,
        )
        self.add(element)
        self.flag("UNCLASSIFIED_LINE", element)


def parse_lines(
    lines: tuple[str, ...], variant: Variant
) -> tuple[tuple[Element, ...], tuple[Finding, ...]]:
    """Turn file lines into elements plus the findings the parser can see on its own."""
    builder = _Builder(variant)
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        line_no = index + 1
        index += 1

        # 1. blank line
        if not stripped:
            continue

        # 2. page marker
        if stripped.upper().startswith("[PAGE"):
            match = _PAGE_RE.fullmatch(stripped)
            if match:
                builder.page_marker(int(match.group(1)), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 3. heading
        if stripped.startswith("#"):
            match = _HEADING_RE.fullmatch(stripped)
            if match:
                builder.heading(len(match.group(1)), match.group(2), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 4. table: consecutive pipe lines whose second line is a separator row
        if stripped.startswith("|"):
            block = [raw]
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index])
                index += 1
            if len(block) >= 2 and _is_separator_row(block[1]):
                builder.table(block, line_no)
            else:
                for offset, block_line in enumerate(block):
                    builder.unclassified(block_line.strip(), line_no + offset, block_line)
            continue

        # 7. paragraph: one line is one paragraph
        builder.paragraph(stripped, line_no, raw)

    if not builder.seen_page_marker:
        builder.findings.append(new_finding("NO_PAGE_MARKER", variant))
    return tuple(builder.elements), tuple(builder.findings)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_parser_tables.py -q`

Expected: 마지막 줄이 `16 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `89 passed`, `All checks passed!`, `14 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/parsing/test_parser_tables.py app/parsing/line_parser.py
git commit -m "feat: parse tables" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 8: 파서 — 이미지, 목록 항목, 미분류

설계 §5의 규칙 5, 6, 8과 §5.2의 첫 행. 이미지는 항상 `IMAGE_PRESENT`(참고)를 낸다. 공백 없는 `-` 뒤에 숫자가 오는 줄은 목록인지 음수인지 정하지 않고 문단으로 두며 `AMBIGUOUS_LIST_OR_NEGATIVE`를 낸다.

**Files:**
- Modify: `app/parsing/line_parser.py`
- Test: `tests/parsing/test_parser_blocks.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/parsing/test_parser_blocks.py`:

````python
"""Images, list items, the '-18' ambiguity and lines that are left unclassified."""

from __future__ import annotations

import pytest


def _codes(findings):
    return [finding.code for finding in findings]


@pytest.mark.parametrize(
    "line, image_id, file_name, title",
    [
        (
            '![img021](<img021.png "원료 투입 List 조회 화면">)',
            "img021",
            "img021.png",
            "원료 투입 List 조회 화면",
        ),
        ("![img021](<img021.png>)", "img021", "img021.png", ""),
        ('![img021](img021.png "조회 화면")', "img021", "img021.png", "조회 화면"),
        ("![img021](img021.png)", "img021", "img021.png", ""),
        ('![img 021](<조회 화면.png "제목">)', "img 021", "조회 화면.png", "제목"),
    ],
)
def test_image(parse, line, image_id, file_name, title):
    elements, findings = parse("[PAGE 1]\n" + line)
    image = elements[1]
    assert image.kind == "image"
    assert (image.image_id, image.file_name, image.title) == (image_id, file_name, title)
    assert image.text == title
    assert image.raw == line
    assert _codes(findings) == ["IMAGE_PRESENT"]
    assert findings[0].grade == "info"
    assert findings[0].element_ids == ("e0002",)
    assert (findings[0].line_start, findings[0].line_end) == (2, 2)


@pytest.mark.parametrize(
    "line", ["![img021](<img021.png>) 그림 설명", "![img021]", "![img021](img 021.png)", "![]("]
)
def test_a_malformed_image_is_unclassified(parse, line):
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "unclassified"
    assert _codes(findings) == ["UNCLASSIFIED_LINE"]


@pytest.mark.parametrize(
    "line, marker, text",
    [
        ("1) Favorites 탭에서 메뉴를 선택한다.", "1)", "Favorites 탭에서 메뉴를 선택한다."),
        ("2)조회 조건을 입력한다.", "2)", "조회 조건을 입력한다."),
        ("12) 열두째 단계", "12)", "열두째 단계"),
        ("1. 첫째 항목", "1.", "첫째 항목"),
        ("- 보관고 온도는 매일 1회 이상 확인한다", "-", "보관고 온도는 매일 1회 이상 확인한다"),
        ("* 별표 항목", "*", "별표 항목"),
        ("-붙여 쓴 항목", "-", "붙여 쓴 항목"),
        ("  - **주의** 들여 쓴 항목", "-", "주의 들여 쓴 항목"),
    ],
)
def test_list_item(parse, line, marker, text):
    elements, findings = parse("[PAGE 1]\n" + line)
    item = elements[1]
    assert item.kind == "list_item"
    assert (item.marker, item.text) == (marker, text)
    assert item.raw == line
    assert findings == ()


def test_each_list_line_is_its_own_element(parse):
    elements, _ = parse("[PAGE 1]\n1) 가\n2) 나\n3) 다")
    assert [element.kind for element in elements[1:]] == ["list_item"] * 3
    assert [element.locator.line_start for element in elements[1:]] == [2, 3, 4]


@pytest.mark.parametrize("line", ["3.5 이상 발생시 조치", "2024년 계획이다.", "1.5배로 늘린다."])
def test_a_line_that_starts_with_a_number_is_a_paragraph(parse, line):
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "paragraph"
    assert findings == ()


@pytest.mark.parametrize("line", ["-18℃ 이하로 보관한다.", "-5 ~ 0℃", "-18"])
def test_a_hyphen_before_a_digit_is_not_decided(parse, line):
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "paragraph"
    assert elements[1].text == line  # the hyphen stays in the text
    assert _codes(findings) == ["AMBIGUOUS_LIST_OR_NEGATIVE"]
    assert findings[0].grade == "review_required"
    assert findings[0].element_ids == ("e0002",)
    assert (findings[0].line_start, findings[0].line_end) == (2, 2)


def test_a_hyphen_a_space_and_a_digit_is_a_list_item(parse):
    elements, findings = parse("[PAGE 1]\n- 18℃ 이하로 보관한다.")
    assert elements[1].kind == "list_item"
    assert findings == ()


@pytest.mark.parametrize(
    "line",
    [
        "```",
        "```python",
        "~~~",
        "> 인용문",
        "---",
        "***",
        "_____",
        "<div>",
        "</table>",
        '<img src="a.png">',
        "-",
        "--",
        "-- 두 줄표",
    ],
)
def test_structural_lines_that_are_not_interpreted(parse, line):
    elements, findings = parse("[PAGE 1]\n" + line)
    assert elements[1].kind == "unclassified"
    assert elements[1].text == line
    assert _codes(findings) == ["UNCLASSIFIED_LINE"]
    assert findings[0].grade == "review_required"


def test_an_unclassified_line_does_not_hide_its_neighbours(parse):
    elements, findings = parse("[PAGE 1]\n앞 문단이다.\n> 인용문\n뒤 문단이다.")
    assert [element.kind for element in elements[1:]] == ["paragraph", "unclassified", "paragraph"]
    assert [finding.line_start for finding in findings] == [3]
````

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_parser_blocks.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
FAILED tests/parsing/test_parser_blocks.py::test_image
FAILED tests/parsing/test_parser_blocks.py::test_a_malformed_image_is_unclassified
FAILED tests/parsing/test_parser_blocks.py::test_list_item
FAILED tests/parsing/test_parser_blocks.py::test_each_list_line_is_its_own_element
FAILED tests/parsing/test_parser_blocks.py::test_a_hyphen_before_a_digit_is_not_decided
FAILED tests/parsing/test_parser_blocks.py::test_a_hyphen_a_space_and_a_digit_is_a_list_item
FAILED tests/parsing/test_parser_blocks.py::test_structural_lines_that_are_not_interpreted
FAILED tests/parsing/test_parser_blocks.py::test_an_unclassified_line_does_not_hide_its_neighbours
36 failed, 3 passed
```

- [ ] **Step 3: 파서를 고친다**

이 단계에서 바뀌는 것:

- `_Builder.image()`와 `_Builder.list_item()`이 생긴다. `paragraph()`는 만든 요소를 돌려준다(발견 항목을 붙이기 위해서다).
- `parse_lines()`에 규칙 5(이미지)가 들어간다. `![`로 시작하지만 두 형식 어느 쪽에도 맞지 않으면 미분류다.
- 규칙 8 중 코드 펜스, `>` 인용, 구분선, HTML 태그 줄을 목록 규칙보다 먼저 검사한다. `---`와 `***`가 목록 항목으로 읽히지 않게 하기 위해서다.
- 규칙 6(목록 항목)이 들어간다. `1)`, `1. `, `- `, `* `, 공백 없는 `-글자`다. `-` 뒤가 숫자이면 문단 + `AMBIGUOUS_LIST_OR_NEGATIVE`, `-`만 있거나 `--`이면 미분류다.

`app/parsing/line_parser.py` 전체를 아래 내용으로 바꾼다:

````python
"""Hand-written line parser for rag_ko.md / rag.md (D-010).

Each non-blank line is classified by the first matching rule. Nothing is guessed:
lines that look structural but fit no rule become `unclassified` elements with a finding.
"""

from __future__ import annotations

import re
from typing import Optional

from app.models.document import (
    Element,
    Heading,
    Image,
    ListItem,
    Locator,
    PageMarker,
    Paragraph,
    Table,
    TableCell,
    Unclassified,
    Variant,
    element_id_for,
)
from app.models.findings import Finding, FindingCode, new_finding

_PAGE_RE = re.compile(r"\[PAGE ?(\d+)\]")
_HEADING_RE = re.compile(r"(#{1,6}) +(\S.*)")
_HEADING_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)*)\.?\s+(\S.*)")
_SEPARATOR_CELL_RE = re.compile(r":?-+:?")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_IMAGE_ANGLE_RE = re.compile(r'!\[([^\]]*)\]\(<([^">]+?)(?:\s+"([^"]*)")?\s*>\)')
_IMAGE_PLAIN_RE = re.compile(r'!\[([^\]]*)\]\(([^\s"<>()]+)(?:\s+"([^"]*)")?\)')
_LIST_PAREN_RE = re.compile(r"(\d+\))\s*(\S.*)")
_LIST_DOT_RE = re.compile(r"(\d+\.)\s+(\S.*)")
_LIST_BULLET_RE = re.compile(r"([-*])\s+(\S.*)")
_RULE_LINE_RE = re.compile(r"(?:-{3,}|\*{3,}|_{3,})")
_HTML_LINE_RE = re.compile(r"</?[A-Za-z][^>]*>")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def clean_text(value: str) -> str:
    """Strip paired ** and turn <br> into newlines. Characters are never changed."""
    return _BOLD_RE.sub(r"\1", _BR_RE.sub("\n", value))


def split_table_row(line: str) -> list[str]:
    """'|a|b| ' -> ['a', 'b']. An escaped pipe (\\|) does not split."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [clean_text(cell.strip().replace("\\|", "|")) for cell in _CELL_SPLIT_RE.split(body)]


def _is_separator_row(line: str) -> bool:
    body = line.strip()
    if not body.startswith("|"):
        return False
    cells = split_table_row(body)
    return bool(cells) and all(_SEPARATOR_CELL_RE.fullmatch(cell) for cell in cells)


class _Builder:
    def __init__(self, variant: Variant) -> None:
        self.variant: Variant = variant
        self.elements: list[Element] = []
        self.findings: list[Finding] = []
        self.page: Optional[int] = None
        self.seen_page_marker = False
        self.before_first_page: list[Element] = []
        self.headings: list[tuple[int, str, Optional[str]]] = []  # (level, label, number)
        self.table_count = 0

    def next_id(self) -> str:
        return element_id_for(len(self.elements) + 1)

    def locator(self, line_start: int, line_end: int) -> Locator:
        return Locator(
            page=self.page,
            section_path=tuple(label for _, label, _ in self.headings),
            line_start=line_start,
            line_end=line_end,
        )

    def add(self, element: Element) -> None:
        self.elements.append(element)
        if not self.seen_page_marker:
            self.before_first_page.append(element)

    def flag(self, code: FindingCode, element: Element, line: Optional[int] = None) -> None:
        self.findings.append(
            new_finding(
                code,
                self.variant,
                element_ids=(element.element_id,),
                line_start=line if line is not None else element.locator.line_start,
                line_end=line if line is not None else element.locator.line_end,
            )
        )

    def page_marker(self, number: int, line_no: int, raw: str) -> None:
        previous = self.page
        if not self.seen_page_marker and self.before_first_page:
            self.findings.append(
                new_finding(
                    "CONTENT_BEFORE_FIRST_PAGE",
                    self.variant,
                    element_ids=tuple(e.element_id for e in self.before_first_page),
                    line_start=self.before_first_page[0].locator.line_start,
                    line_end=self.before_first_page[-1].locator.line_end,
                )
            )
        self.seen_page_marker = True
        self.page = number
        element = PageMarker(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=raw.strip(),
            page=number,
        )
        self.add(element)
        if previous is not None and number <= previous:
            self.flag("PAGE_NUMBER_NOT_INCREASING", element)

    def heading(self, level: int, rest: str, line_no: int, raw: str) -> None:
        match = _HEADING_NUMBER_RE.fullmatch(rest)
        number = match.group(1) if match else None
        title = clean_text(match.group(2) if match else rest)
        while self.headings and self.headings[-1][0] >= level:
            self.headings.pop()
        parent_number = self.headings[-1][2] if self.headings else None
        mismatch = (
            number is not None
            and parent_number is not None
            and not number.startswith(parent_number + ".")
        )
        self.headings.append((level, number if number is not None else title, number))
        element = Heading(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=clean_text(rest),
            level=level,
            number=number,
            title=title,
        )
        self.add(element)
        if mismatch:
            self.flag("HEADING_NUMBER_MISMATCH", element)

    def table(self, block: list[str], line_start: int) -> None:
        self.table_count += 1
        header = split_table_row(block[0])
        rows = [split_table_row(line) for line in block[2:]]
        element = Table(
            element_id=self.next_id(),
            locator=self.locator(line_start, line_start + len(block) - 1),
            raw="\n".join(block),
            text="\n".join(" | ".join(cells) for cells in [header, *rows]),
            table_index=self.table_count,
            header=tuple(header),
            rows=tuple(
                tuple(TableCell(row=r, col=c, text=text) for c, text in enumerate(cells, start=1))
                for r, cells in enumerate(rows, start=1)
            ),
        )
        self.add(element)
        if len(split_table_row(block[1])) != len(header):
            self.flag("TABLE_ROW_WIDTH_MISMATCH", element, line_start + 1)
        for offset, cells in enumerate(rows, start=2):
            if len(cells) != len(header):
                self.flag("TABLE_ROW_WIDTH_MISMATCH", element, line_start + offset)

    def image(self, match: re.Match[str], line_no: int, raw: str) -> None:
        title = match.group(3) or ""
        element = Image(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=title,
            image_id=match.group(1),
            file_name=match.group(2).strip(),
            title=title,
        )
        self.add(element)
        self.flag("IMAGE_PRESENT", element)

    def list_item(self, marker: str, body: str, line_no: int, raw: str) -> None:
        self.add(
            ListItem(
                element_id=self.next_id(),
                locator=self.locator(line_no, line_no),
                raw=raw,
                text=clean_text(body),
                marker=marker,
            )
        )

    def paragraph(self, stripped: str, line_no: int, raw: str) -> Paragraph:
        element = Paragraph(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=clean_text(stripped),
        )
        self.add(element)
        return element

    def unclassified(self, stripped: str, line_no: int, raw: str) -> None:
        element = Unclassified(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=stripped,
        )
        self.add(element)
        self.flag("UNCLASSIFIED_LINE", element)


def parse_lines(
    lines: tuple[str, ...], variant: Variant
) -> tuple[tuple[Element, ...], tuple[Finding, ...]]:
    """Turn file lines into elements plus the findings the parser can see on its own."""
    builder = _Builder(variant)
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        line_no = index + 1
        index += 1

        # 1. blank line
        if not stripped:
            continue

        # 2. page marker
        if stripped.upper().startswith("[PAGE"):
            match = _PAGE_RE.fullmatch(stripped)
            if match:
                builder.page_marker(int(match.group(1)), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 3. heading
        if stripped.startswith("#"):
            match = _HEADING_RE.fullmatch(stripped)
            if match:
                builder.heading(len(match.group(1)), match.group(2), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 4. table: consecutive pipe lines whose second line is a separator row
        if stripped.startswith("|"):
            block = [raw]
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index])
                index += 1
            if len(block) >= 2 and _is_separator_row(block[1]):
                builder.table(block, line_no)
            else:
                for offset, block_line in enumerate(block):
                    builder.unclassified(block_line.strip(), line_no + offset, block_line)
            continue

        # 5. image
        if stripped.startswith("!["):
            match = _IMAGE_ANGLE_RE.fullmatch(stripped) or _IMAGE_PLAIN_RE.fullmatch(stripped)
            if match:
                builder.image(match, line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 8 (checked early). lines that look structural but are not interpreted
        if (
            stripped.startswith(("```", "~~~", ">"))
            or _RULE_LINE_RE.fullmatch(stripped)
            or _HTML_LINE_RE.match(stripped)
        ):
            builder.unclassified(stripped, line_no, raw)
            continue

        # 6. list item
        match = (
            _LIST_PAREN_RE.fullmatch(stripped)
            or _LIST_DOT_RE.fullmatch(stripped)
            or _LIST_BULLET_RE.fullmatch(stripped)
        )
        if match:
            builder.list_item(match.group(1), match.group(2), line_no, raw)
            continue
        if stripped.startswith("-"):
            rest = stripped[1:]
            if rest[:1].isdigit():
                # '-18℃ ...': list item or negative number? Not decided here.
                element = builder.paragraph(stripped, line_no, raw)
                builder.flag("AMBIGUOUS_LIST_OR_NEGATIVE", element)
            elif rest and not rest.startswith("-"):
                builder.list_item("-", rest, line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 7. paragraph: one line is one paragraph
        builder.paragraph(stripped, line_no, raw)

    if not builder.seen_page_marker:
        builder.findings.append(new_finding("NO_PAGE_MARKER", variant))
    return tuple(builder.elements), tuple(builder.findings)
````

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_parser_blocks.py -q`

Expected: 마지막 줄이 `39 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `128 passed`, `All checks passed!`, `15 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/parsing/test_parser_blocks.py app/parsing/line_parser.py
git commit -m "feat: parse images and list items, keep uninterpreted lines as unclassified" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 9: 줄 누락 검사

설계 §7.3의 셋째 항목과 완료 기준 3. 빈 줄이 아닌 모든 줄이 정확히 한 요소에 속하는지 파싱 뒤에 코드로 확인한다. 어긋나면 `LineCoverageError`를 내고, Task 17의 `ingest()`가 이를 내부 오류(`FAILED`)로 바꾼다. 오류 메시지에는 요소 ID와 줄 번호만 넣는다.

**Files:**
- Modify: `app/parsing/line_parser.py`
- Create: `tests/conftest.py`
- Test: `tests/parsing/test_line_coverage.py`

- [ ] **Step 1: 샘플 파일 픽스처를 만든다**

`tests/conftest.py`:

```python
"""Paths of the sample documents. Everything under tests/fixtures is synthetic."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def ko_sample() -> Path:
    """Korean sample: a baseline document, and also the translation of the three below."""
    return FIXTURES / "rag_ko" / "sample_bakery_sop.md"


@pytest.fixture(scope="session")
def source_samples() -> dict[str, Path]:
    """The same sample before translation, by original language."""
    return {
        language: FIXTURES / "rag" / f"sample_bakery_sop.{language}.md"
        for language in ("en", "vi", "zh")
    }
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/parsing/test_line_coverage.py`:

```python
"""No line may be lost: every non-blank line belongs to exactly one element."""

from __future__ import annotations

import pytest

from app.parsing.line_parser import LineCoverageError, parse_lines, verify_line_coverage
from app.parsing.reader import read_lines

LINES = (
    "[PAGE 1]",
    "",
    "## 1. 개요",
    "문단이다.",
    "|가|나|",
    "|---|---|",
    "|1|2|",
    "",
    "> 해석하지 않는 줄",
    "- 항목",
)


def test_parsed_lines_are_covered():
    elements, _ = parse_lines(LINES, "source")
    verify_line_coverage(LINES, elements)  # does not raise


def test_a_lost_element_is_noticed():
    elements, _ = parse_lines(LINES, "source")
    with pytest.raises(LineCoverageError, match="line 4 is owned by 0 elements"):
        verify_line_coverage(LINES, elements[:2] + elements[3:])


def test_a_line_owned_twice_is_noticed():
    elements, _ = parse_lines(LINES, "source")
    with pytest.raises(LineCoverageError, match="line 4 is owned by 2 elements"):
        verify_line_coverage(LINES, elements + (elements[2],))


def test_an_element_on_a_blank_line_is_noticed():
    elements, _ = parse_lines(LINES, "source")
    paragraph = elements[2]
    moved = paragraph.model_copy(
        update={"locator": paragraph.locator.model_copy(update={"line_start": 2, "line_end": 2})}
    )
    with pytest.raises(LineCoverageError, match="line 2 is owned by 1 elements"):
        verify_line_coverage(LINES, elements[:2] + (moved,) + elements[3:])


def test_an_element_outside_the_file_is_noticed():
    elements, _ = parse_lines(LINES, "source")
    with pytest.raises(LineCoverageError, match="e0006 points outside the file"):
        verify_line_coverage(LINES[:-1], elements)


def test_the_message_holds_no_document_text():
    elements, _ = parse_lines(LINES, "source")
    with pytest.raises(LineCoverageError) as caught:
        verify_line_coverage(LINES, elements[:2] + elements[3:])
    assert "문단" not in str(caught.value)


def test_every_sample_is_covered(ko_sample, source_samples):
    for path in [ko_sample, *source_samples.values()]:
        lines = read_lines(path).lines
        elements, _ = parse_lines(lines, "source")
        verify_line_coverage(lines, elements)
        owned = {
            line_no
            for element in elements
            for line_no in range(element.locator.line_start, element.locator.line_end + 1)
        }
        not_blank = {line_no for line_no, line in enumerate(lines, start=1) if line.strip()}
        assert owned == not_blank
```

- [ ] **Step 3: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_line_coverage.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ImportError: cannot import name 'LineCoverageError' from 'app.parsing.line_parser'
1 error
```

- [ ] **Step 4: 검사를 구현한다**

이 단계에서 바뀌는 것:

- `LineCoverageError` 예외가 생긴다.
- 파일 끝에 `verify_line_coverage(lines, elements)`가 생긴다. 줄마다 그 줄을 가진 요소의 수를 세어, 빈 줄은 0, 그 밖의 줄은 1이어야 한다.

`app/parsing/line_parser.py` 전체를 아래 내용으로 바꾼다. 이것이 이 파일의 최종 모습이다:

````python
"""Hand-written line parser for rag_ko.md / rag.md (D-010).

Each non-blank line is classified by the first matching rule. Nothing is guessed:
lines that look structural but fit no rule become `unclassified` elements with a finding.
"""

from __future__ import annotations

import re
from typing import Optional

from app.models.document import (
    Element,
    Heading,
    Image,
    ListItem,
    Locator,
    PageMarker,
    Paragraph,
    Table,
    TableCell,
    Unclassified,
    Variant,
    element_id_for,
)
from app.models.findings import Finding, FindingCode, new_finding

_PAGE_RE = re.compile(r"\[PAGE ?(\d+)\]")
_HEADING_RE = re.compile(r"(#{1,6}) +(\S.*)")
_HEADING_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)*)\.?\s+(\S.*)")
_SEPARATOR_CELL_RE = re.compile(r":?-+:?")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_IMAGE_ANGLE_RE = re.compile(r'!\[([^\]]*)\]\(<([^">]+?)(?:\s+"([^"]*)")?\s*>\)')
_IMAGE_PLAIN_RE = re.compile(r'!\[([^\]]*)\]\(([^\s"<>()]+)(?:\s+"([^"]*)")?\)')
_LIST_PAREN_RE = re.compile(r"(\d+\))\s*(\S.*)")
_LIST_DOT_RE = re.compile(r"(\d+\.)\s+(\S.*)")
_LIST_BULLET_RE = re.compile(r"([-*])\s+(\S.*)")
_RULE_LINE_RE = re.compile(r"(?:-{3,}|\*{3,}|_{3,})")
_HTML_LINE_RE = re.compile(r"</?[A-Za-z][^>]*>")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


class LineCoverageError(Exception):
    """A non-blank line belongs to no element or to more than one. Internal error."""


def clean_text(value: str) -> str:
    """Strip paired ** and turn <br> into newlines. Characters are never changed."""
    return _BOLD_RE.sub(r"\1", _BR_RE.sub("\n", value))


def split_table_row(line: str) -> list[str]:
    """'|a|b| ' -> ['a', 'b']. An escaped pipe (\\|) does not split."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [clean_text(cell.strip().replace("\\|", "|")) for cell in _CELL_SPLIT_RE.split(body)]


def _is_separator_row(line: str) -> bool:
    body = line.strip()
    if not body.startswith("|"):
        return False
    cells = split_table_row(body)
    return bool(cells) and all(_SEPARATOR_CELL_RE.fullmatch(cell) for cell in cells)


class _Builder:
    def __init__(self, variant: Variant) -> None:
        self.variant: Variant = variant
        self.elements: list[Element] = []
        self.findings: list[Finding] = []
        self.page: Optional[int] = None
        self.seen_page_marker = False
        self.before_first_page: list[Element] = []
        self.headings: list[tuple[int, str, Optional[str]]] = []  # (level, label, number)
        self.table_count = 0

    def next_id(self) -> str:
        return element_id_for(len(self.elements) + 1)

    def locator(self, line_start: int, line_end: int) -> Locator:
        return Locator(
            page=self.page,
            section_path=tuple(label for _, label, _ in self.headings),
            line_start=line_start,
            line_end=line_end,
        )

    def add(self, element: Element) -> None:
        self.elements.append(element)
        if not self.seen_page_marker:
            self.before_first_page.append(element)

    def flag(self, code: FindingCode, element: Element, line: Optional[int] = None) -> None:
        self.findings.append(
            new_finding(
                code,
                self.variant,
                element_ids=(element.element_id,),
                line_start=line if line is not None else element.locator.line_start,
                line_end=line if line is not None else element.locator.line_end,
            )
        )

    def page_marker(self, number: int, line_no: int, raw: str) -> None:
        previous = self.page
        if not self.seen_page_marker and self.before_first_page:
            self.findings.append(
                new_finding(
                    "CONTENT_BEFORE_FIRST_PAGE",
                    self.variant,
                    element_ids=tuple(e.element_id for e in self.before_first_page),
                    line_start=self.before_first_page[0].locator.line_start,
                    line_end=self.before_first_page[-1].locator.line_end,
                )
            )
        self.seen_page_marker = True
        self.page = number
        element = PageMarker(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=raw.strip(),
            page=number,
        )
        self.add(element)
        if previous is not None and number <= previous:
            self.flag("PAGE_NUMBER_NOT_INCREASING", element)

    def heading(self, level: int, rest: str, line_no: int, raw: str) -> None:
        match = _HEADING_NUMBER_RE.fullmatch(rest)
        number = match.group(1) if match else None
        title = clean_text(match.group(2) if match else rest)
        while self.headings and self.headings[-1][0] >= level:
            self.headings.pop()
        parent_number = self.headings[-1][2] if self.headings else None
        mismatch = (
            number is not None
            and parent_number is not None
            and not number.startswith(parent_number + ".")
        )
        self.headings.append((level, number if number is not None else title, number))
        element = Heading(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=clean_text(rest),
            level=level,
            number=number,
            title=title,
        )
        self.add(element)
        if mismatch:
            self.flag("HEADING_NUMBER_MISMATCH", element)

    def table(self, block: list[str], line_start: int) -> None:
        self.table_count += 1
        header = split_table_row(block[0])
        rows = [split_table_row(line) for line in block[2:]]
        element = Table(
            element_id=self.next_id(),
            locator=self.locator(line_start, line_start + len(block) - 1),
            raw="\n".join(block),
            text="\n".join(" | ".join(cells) for cells in [header, *rows]),
            table_index=self.table_count,
            header=tuple(header),
            rows=tuple(
                tuple(TableCell(row=r, col=c, text=text) for c, text in enumerate(cells, start=1))
                for r, cells in enumerate(rows, start=1)
            ),
        )
        self.add(element)
        if len(split_table_row(block[1])) != len(header):
            self.flag("TABLE_ROW_WIDTH_MISMATCH", element, line_start + 1)
        for offset, cells in enumerate(rows, start=2):
            if len(cells) != len(header):
                self.flag("TABLE_ROW_WIDTH_MISMATCH", element, line_start + offset)

    def image(self, match: re.Match[str], line_no: int, raw: str) -> None:
        title = match.group(3) or ""
        element = Image(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=title,
            image_id=match.group(1),
            file_name=match.group(2).strip(),
            title=title,
        )
        self.add(element)
        self.flag("IMAGE_PRESENT", element)

    def list_item(self, marker: str, body: str, line_no: int, raw: str) -> None:
        self.add(
            ListItem(
                element_id=self.next_id(),
                locator=self.locator(line_no, line_no),
                raw=raw,
                text=clean_text(body),
                marker=marker,
            )
        )

    def paragraph(self, stripped: str, line_no: int, raw: str) -> Paragraph:
        element = Paragraph(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=clean_text(stripped),
        )
        self.add(element)
        return element

    def unclassified(self, stripped: str, line_no: int, raw: str) -> None:
        element = Unclassified(
            element_id=self.next_id(),
            locator=self.locator(line_no, line_no),
            raw=raw,
            text=stripped,
        )
        self.add(element)
        self.flag("UNCLASSIFIED_LINE", element)


def parse_lines(
    lines: tuple[str, ...], variant: Variant
) -> tuple[tuple[Element, ...], tuple[Finding, ...]]:
    """Turn file lines into elements plus the findings the parser can see on its own."""
    builder = _Builder(variant)
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        line_no = index + 1
        index += 1

        # 1. blank line
        if not stripped:
            continue

        # 2. page marker
        if stripped.upper().startswith("[PAGE"):
            match = _PAGE_RE.fullmatch(stripped)
            if match:
                builder.page_marker(int(match.group(1)), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 3. heading
        if stripped.startswith("#"):
            match = _HEADING_RE.fullmatch(stripped)
            if match:
                builder.heading(len(match.group(1)), match.group(2), line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 4. table: consecutive pipe lines whose second line is a separator row
        if stripped.startswith("|"):
            block = [raw]
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index])
                index += 1
            if len(block) >= 2 and _is_separator_row(block[1]):
                builder.table(block, line_no)
            else:
                for offset, block_line in enumerate(block):
                    builder.unclassified(block_line.strip(), line_no + offset, block_line)
            continue

        # 5. image
        if stripped.startswith("!["):
            match = _IMAGE_ANGLE_RE.fullmatch(stripped) or _IMAGE_PLAIN_RE.fullmatch(stripped)
            if match:
                builder.image(match, line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 8 (checked early). lines that look structural but are not interpreted
        if (
            stripped.startswith(("```", "~~~", ">"))
            or _RULE_LINE_RE.fullmatch(stripped)
            or _HTML_LINE_RE.match(stripped)
        ):
            builder.unclassified(stripped, line_no, raw)
            continue

        # 6. list item
        match = (
            _LIST_PAREN_RE.fullmatch(stripped)
            or _LIST_DOT_RE.fullmatch(stripped)
            or _LIST_BULLET_RE.fullmatch(stripped)
        )
        if match:
            builder.list_item(match.group(1), match.group(2), line_no, raw)
            continue
        if stripped.startswith("-"):
            rest = stripped[1:]
            if rest[:1].isdigit():
                # '-18℃ ...': list item or negative number? Not decided here.
                element = builder.paragraph(stripped, line_no, raw)
                builder.flag("AMBIGUOUS_LIST_OR_NEGATIVE", element)
            elif rest and not rest.startswith("-"):
                builder.list_item("-", rest, line_no, raw)
            else:
                builder.unclassified(stripped, line_no, raw)
            continue

        # 7. paragraph: one line is one paragraph
        builder.paragraph(stripped, line_no, raw)

    if not builder.seen_page_marker:
        builder.findings.append(new_finding("NO_PAGE_MARKER", variant))
    return tuple(builder.elements), tuple(builder.findings)


def verify_line_coverage(lines: tuple[str, ...], elements: tuple[Element, ...]) -> None:
    """Every non-blank line must belong to exactly one element; blank lines to none."""
    owners = [0] * (len(lines) + 1)
    for element in elements:
        for line_no in range(element.locator.line_start, element.locator.line_end + 1):
            if not 1 <= line_no <= len(lines):
                raise LineCoverageError(f"{element.element_id} points outside the file")
            owners[line_no] += 1
    for line_no, line in enumerate(lines, start=1):
        expected = 1 if line.strip() else 0
        if owners[line_no] != expected:
            raise LineCoverageError(f"line {line_no} is owned by {owners[line_no]} elements")
````

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_line_coverage.py -q`

Expected: 마지막 줄이 `7 passed`

- [ ] **Step 6: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `135 passed`, `All checks passed!`, `17 files already formatted`

- [ ] **Step 7: 커밋한다**

```bash
git add tests/conftest.py tests/parsing/test_line_coverage.py app/parsing/line_parser.py
git commit -m "feat: verify that every non-blank line belongs to one element" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 10: 샘플 기준값

설계 §10의 "샘플 기준값"과 완료 기준 1, 2, 4. 새 코드는 없다. 지금까지 만든 파서가 제빵 샘플 전체에서 설계에 적힌 값을 내는지 고정하는 테스트다.

**Files:**
- Test: `tests/parsing/test_sample_golden.py`

- [ ] **Step 1: 테스트를 쓴다**

`tests/parsing/test_sample_golden.py`:

```python
"""Reference values of the sample documents (spec section 2)."""

from __future__ import annotations

from collections import Counter

import pytest

from app.parsing.line_parser import parse_lines
from app.parsing.reader import read_lines

EXPECTED_KINDS = {
    "page_marker": 4,
    "heading": 6,
    "table": 5,
    "image": 3,
    "list_item": 14,
    "paragraph": 17,
}


def _parse(path):
    return parse_lines(read_lines(path).lines, "source")


def test_the_korean_sample_has_49_elements(ko_sample):
    elements, _ = _parse(ko_sample)
    assert len(elements) == 49
    assert Counter(element.kind for element in elements) == EXPECTED_KINDS  # no 'unclassified'
    assert [element.element_id for element in elements] == [f"e{n:04d}" for n in range(1, 50)]


def test_the_only_findings_are_the_three_images(ko_sample):
    _, findings = _parse(ko_sample)
    assert [finding.code for finding in findings] == ["IMAGE_PRESENT"] * 3
    assert {finding.grade for finding in findings} == {"info"}
    assert [finding.element_ids for finding in findings] == [("e0008",), ("e0021",), ("e0033",)]


def test_the_pages_are_8_to_11(ko_sample):
    elements, _ = _parse(ko_sample)
    markers = [element for element in elements if element.kind == "page_marker"]
    assert [marker.page for marker in markers] == [8, 9, 10, 11]
    assert [marker.element_id for marker in markers] == ["e0001", "e0014", "e0023", "e0036"]


def test_every_element_has_a_page_a_section_and_lines(ko_sample):
    elements, _ = _parse(ko_sample)
    for element in elements:
        assert element.locator.page is not None
        assert 1 <= element.locator.line_start <= element.locator.line_end <= 114
    # only the first page marker stands before the first heading
    assert [element.element_id for element in elements if not element.locator.section_path] == [
        "e0001"
    ]


def test_the_headings(ko_sample):
    elements, _ = _parse(ko_sample)
    headings = [element for element in elements if element.kind == "heading"]
    assert [(heading.level, heading.number) for heading in headings] == [
        (2, "3"),
        (3, "3.1"),
        (3, "3.2"),
        (3, "3.3"),
        (3, "3.4"),
        (3, "3.5"),
    ]
    assert [heading.locator.line_start for heading in headings] == [3, 5, 32, 56, 90, 105]


def test_the_weighing_table_is_e0017(ko_sample):
    elements, _ = _parse(ko_sample)
    table = elements[16]
    assert table.element_id == "e0017"
    assert table.kind == "table"
    assert table.table_index == 2
    assert table.locator.page == 9
    assert table.locator.section_path == ("3", "3.2")
    assert (table.locator.line_start, table.locator.line_end) == (36, 42)
    assert table.header == ("확인 항목", "확인 방법", "판정기준")
    assert len(table.rows) == 5
    assert table.rows[1][2].text == "배합표 대비 ±1.0% 이내"  # e0017:r2c3, line 39


def test_typos_in_the_sample_are_kept(ko_sample):
    elements, _ = _parse(ko_sample)
    text = "\n".join(element.text for element in elements)
    assert "합께" in text
    assert "패덜" in text


def test_the_minus_sign_in_a_table_cell_raises_no_finding(ko_sample):
    elements, findings = _parse(ko_sample)
    table = elements[41]
    assert table.element_id == "e0042"
    assert table.rows[3][1].text == "-18℃이하"  # e0042:r4c2, line 103
    assert "AMBIGUOUS_LIST_OR_NEGATIVE" not in {finding.code for finding in findings}


@pytest.mark.parametrize("language", ["en", "vi", "zh"])
def test_each_source_sample_has_the_same_shape(ko_sample, source_samples, language):
    korean, _ = _parse(ko_sample)
    elements, findings = _parse(source_samples[language])
    assert Counter(element.kind for element in elements) == EXPECTED_KINDS

    def shape(parsed):
        return [
            (e.kind, e.locator.page, e.locator.section_path, e.locator.line_start) for e in parsed
        ]

    assert shape(elements) == shape(korean)
    assert [finding.code for finding in findings] == ["IMAGE_PRESENT"] * 3
```

- [ ] **Step 2: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_sample_golden.py -q`

Expected: 마지막 줄이 `11 passed`

이 테스트는 처음부터 통과해야 한다. 실패하면 Task 5~9의 파서가 계획과 다른 것이다. **샘플 파일과 이 테스트의 기대값을 고치지 않는다.** 실패한 테스트 이름과 출력을 사용자에게 알린다.

- [ ] **Step 3: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `146 passed`, `All checks passed!`, `18 files already formatted`

- [ ] **Step 4: 커밋한다**

```bash
git add tests/parsing/test_sample_golden.py
git commit -m "test: pin the parsed shape of the bakery sample" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 11: 숫자 표기 해석

설계 §6.3. 숫자로 적힌 문자열을 문서 언어의 표기로 해석해 `Decimal`로 바꾼다. 표기에 맞지 않으면 `None`이다. 추측해서 값을 만들지 않는다.

| 언어 | 소수점 | 천 단위 구분 |
|---|---|---|
| `ko`, `en`, `zh` | `.` | `,` |
| `vi` | `,` | `.` |

**Files:**
- Create: `app/parsing/tokens.py`
- Test: `tests/parsing/test_number_notation.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/parsing/test_number_notation.py`:

```python
"""Number notation by language (spec section 6.3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.parsing.tokens import parse_number


@pytest.mark.parametrize(
    "raw, language, value",
    [
        # ko / en / zh: '.' is the decimal point, ',' groups thousands
        ("180", "ko", "180"),
        ("1.5", "ko", "1.5"),
        ("1.0", "en", "1.0"),
        ("1,000", "en", "1000"),
        ("1,000", "ko", "1000"),
        ("1,000", "zh", "1000"),
        ("10,000,000", "en", "10000000"),
        ("1,000.5", "en", "1000.5"),
        ("1.000", "en", "1.000"),  # one, written with three decimals
        # vi: ',' is the decimal point, '.' groups thousands
        ("180", "vi", "180"),
        ("1,5", "vi", "1.5"),
        ("1,0", "vi", "1.0"),
        ("0,5", "vi", "0.5"),
        ("1.000", "vi", "1000"),
        ("1.234.567", "vi", "1234567"),
        ("1.000,25", "vi", "1000.25"),
        ("1,000", "vi", "1.000"),  # one, written with three decimals
    ],
)
def test_numbers_that_fit_the_notation(raw, language, value):
    assert parse_number(raw, language) == Decimal(value)


@pytest.mark.parametrize(
    "raw, language",
    [
        ("1,5", "en"),  # a comma, but not three digits after it
        ("12,34", "ko"),
        ("1,00", "zh"),
        ("1.2.3", "ko"),
        ("1,000,5", "en"),
        ("1.5", "vi"),  # a dot, but not three digits after it
        ("12.34", "vi"),
        ("1,000.5", "vi"),
        ("10,000,000", "vi"),
        ("", "ko"),
        ("abc", "ko"),
    ],
)
def test_numbers_that_do_not_fit_the_notation(raw, language):
    assert parse_number(raw, language) is None


def test_the_same_digits_mean_different_values():
    assert parse_number("1.000", "vi") == 1000
    assert parse_number("1.000", "en") == 1
    assert parse_number("1,000", "en") == 1000
    assert parse_number("1,000", "vi") == 1


def test_values_compare_by_amount_not_by_spelling():
    assert parse_number("1,0", "vi") == parse_number("1.0", "ko")
    assert parse_number("1.50", "ko") == parse_number("1,5", "vi")
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_number_notation.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ModuleNotFoundError: No module named 'app.parsing.tokens'
1 error
```

- [ ] **Step 3: 구현한다**

`app/parsing/tokens.py`:

```python
"""Tokens compared between a translation and its source: numbers, units, symbols, codes.

Only these tokens are compared, by count and without regard to order. The stored text
is never changed; normalization happens only on the copy that is scanned here.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from app.models.document import Language

_PLAIN_DOT = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_GROUPED_DOT = re.compile(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?")
_PLAIN_COMMA = re.compile(r"[0-9]+(?:,[0-9]+)?")
_GROUPED_COMMA = re.compile(r"[0-9]{1,3}(?:\.[0-9]{3})+(?:,[0-9]+)?")


def parse_number(raw: str, language: Language) -> Optional[Decimal]:
    """Value of `raw` in the notation of `language`, or None if it does not fit.

    ko/en/zh: '.' decimal, ',' thousands. vi: ',' decimal, '.' thousands.
    A thousands separator counts only when exactly three digits follow it.
    """
    if language == "vi":
        if _PLAIN_COMMA.fullmatch(raw):
            return Decimal(raw.replace(",", "."))
        if _GROUPED_COMMA.fullmatch(raw):
            return Decimal(raw.replace(".", "").replace(",", "."))
        return None
    if _PLAIN_DOT.fullmatch(raw):
        return Decimal(raw)
    if _GROUPED_DOT.fullmatch(raw):
        return Decimal(raw.replace(",", ""))
    return None
```

`float`가 아니라 `Decimal`을 쓴다. `1.0`과 `1.00`이 같은 값으로 비교되고, 이진 부동소수점 오차가 끼어들지 않는다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_number_notation.py -q`

Expected: 마지막 줄이 `30 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `176 passed`, `All checks passed!`, `20 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/parsing/test_number_notation.py app/parsing/tokens.py
git commit -m "feat: read numbers in the notation of the document language" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 12: 토큰 추출

설계 §6.2. 글에서 숫자, 단위, 범위·공차 기호, 코드를 뽑는다. 비교할 때만 정규화하고 저장된 원문은 바꾸지 않는다.

**Files:**
- Modify: `app/parsing/tokens.py`
- Test: `tests/parsing/test_tokens.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/parsing/test_tokens.py`:

```python
"""Finding the tokens in a text: numbers, units, signs, codes (spec section 6.2)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.parsing.tokens import UNITS, extract_tokens, normalize


def _numbers(text, language="ko"):
    return [token.raw for token in extract_tokens(text, language).numbers]


def _others(text, language="ko"):
    return list(extract_tokens(text, language).others)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("１８０℃", "180°C"),  # full-width digits, one-character unit
        ("５ｋｇ", "5kg"),
        ("−18", "-18"),  # U+2212 minus sign
        ("2〜8", "2~8"),  # U+301C wave dash
        ("2～8", "2~8"),  # U+FF5E full-width tilde
        ("5µm", "5μm"),  # U+00B5 micro sign -> Greek mu
    ],
)
def test_normalize(text, expected):
    assert normalize(text) == expected


def test_numbers_are_found_with_their_value():
    tokens = extract_tokens("오븐 온도는 180℃, 시간은 12.5분으로 한다.", "ko")
    assert [(token.raw, token.value) for token in tokens.numbers] == [
        ("180", Decimal("180")),
        ("12.5", Decimal("12.5")),
    ]


def test_a_number_that_does_not_fit_the_notation_has_no_value():
    tokens = extract_tokens("1,5 kg", "en")
    assert [(token.raw, token.value) for token in tokens.numbers] == [("1,5", None)]
    assert extract_tokens("1,5 kg", "vi").numbers[0].value == Decimal("1.5")


def test_full_width_digits_are_read_as_digits():
    tokens = extract_tokens("１８０℃", "zh")
    assert [(token.raw, token.value) for token in tokens.numbers] == [("180", Decimal("180"))]
    assert tokens.others == ("unit:°C",)


def test_a_sentence_end_is_not_part_of_a_number():
    assert _numbers("기준은 5.") == ["5"]
    assert _numbers("3, 4 그리고 5") == ["3", "4", "5"]


@pytest.mark.parametrize("unit", UNITS)
def test_every_unit_in_the_table_is_found_after_a_number(unit):
    expected = ["unit:" + normalize(unit)]
    assert _others("5" + unit) == expected
    assert _others("5 " + unit) == expected  # one space is allowed


@pytest.mark.parametrize(
    "text, expected",
    [
        ("5 mm", ["unit:mm"]),  # the longest unit wins: not 'm'
        ("5 m", ["unit:m"]),
        ("5 MPa", ["unit:MPa"]),
        ("5  mm", []),  # two spaces
        ("mm 5", []),  # the unit must follow the number
        ("30 min", []),  # 'm' here starts a word
        ("5 Liter", []),
        ("5℃로 한다", ["unit:°C"]),  # a Korean particle may follow
        ("180 °C", ["unit:°C"]),
        ("길이 m", []),
    ],
)
def test_units(text, expected):
    assert _others(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("±1.0%", ["sym:±", "unit:%"]),
        ("2~8℃", ["sym:~", "unit:°C"]),
        ("2〜8℃", ["sym:~", "unit:°C"]),
        ("-18℃이하", ["sym:neg", "unit:°C"]),
        ("−18℃", ["sym:neg", "unit:°C"]),
        ("온도 -5", ["sym:neg"]),
        ("10-20", []),  # a hyphen between numbers is not a sign
        ("2024-11-11", []),
        ("가-나", []),
        ("- 항목", []),
    ],
)
def test_signs(text, expected):
    assert _others(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("WI-BK-204 에 따른다", ["code:WI-BK-204"]),
        ("설비 BK01", ["code:BK01"]),
        ("A-1 구역", ["code:A-1"]),
        ("LotNo.가 없는 원료", []),  # letters only: a word, not a code
        ("Favorites 탭", []),
        ("pH 7", []),
        ("BK01-", ["code:BK01"]),
    ],
)
def test_codes(text, expected):
    assert _others(text) == expected


def test_the_digits_of_a_code_are_not_counted_as_numbers():
    assert _numbers("WI-BK-204 에 따라 3회 확인한다") == ["3"]


def test_text_without_tokens():
    tokens = extract_tokens("원료를 확인한다.", "ko")
    assert tokens.numbers == ()
    assert tokens.others == ()
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_tokens.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ImportError: cannot import name 'UNITS' from 'app.parsing.tokens'
1 error
```

- [ ] **Step 3: 구현한다**

이 단계에서 바뀌는 것:

- 단위 표 `UNITS`가 생긴다. 단위는 이 한 곳에만 둔다.
- `normalize()`가 생긴다. NFKC에 더해 U+2212(−)를 `-`로, U+301C(〜)를 `~`로 접는다.
- `NumberToken(raw, value)`와 `Tokens(numbers, units, signs, codes)`가 생긴다.
- `extract_tokens(text, language)`가 생긴다. 코드를 먼저 찾아 그 자리를 비우고, 남은 글에서 숫자와 그 뒤의 단위, 앞의 음수 부호를 찾는다. 그래서 `WI-BK-204`의 `204`는 숫자로 세지 않는다.

`app/parsing/tokens.py` 전체를 아래 내용으로 바꾼다:

```python
"""Tokens compared between a translation and its source: numbers, units, symbols, codes.

Only these tokens are compared, by count and without regard to order. The stored text
is never changed; normalization happens only on the copy that is scanned here.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.models.document import Language

# One place for the unit table. Add units here when real documents show more.
UNITS: tuple[str, ...] = (
    "℃", "°C", "℉", "%", "μm", "mm", "cm", "m", "mg", "g", "kg",
    "mL", "L", "Pa", "kPa", "MPa", "rpm", "ppm",
)  # fmt: skip

# NFKC leaves these two alone, so they are folded by hand: U+2212 minus, U+301C wave dash.
_FOLD = str.maketrans({"−": "-", "〜": "~"})

_PLAIN_DOT = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_GROUPED_DOT = re.compile(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?")
_PLAIN_COMMA = re.compile(r"[0-9]+(?:,[0-9]+)?")
_GROUPED_COMMA = re.compile(r"[0-9]{1,3}(?:\.[0-9]{3})+(?:,[0-9]+)?")

_NUMBER_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
_CODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_ASCII_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_ASCII_DIGITS = frozenset("0123456789")
_ASCII_ALNUM = _ASCII_LETTERS | _ASCII_DIGITS


def normalize(text: str) -> str:
    """NFKC (full-width -> half-width, '℃' -> '°C') plus the two hand-folded signs."""
    return unicodedata.normalize("NFKC", text).translate(_FOLD)


_UNITS_LONGEST_FIRST: tuple[str, ...] = tuple(
    sorted({normalize(unit) for unit in UNITS}, key=lambda unit: (-len(unit), unit))
)


def parse_number(raw: str, language: Language) -> Optional[Decimal]:
    """Value of `raw` in the notation of `language`, or None if it does not fit.

    ko/en/zh: '.' decimal, ',' thousands. vi: ',' decimal, '.' thousands.
    A thousands separator counts only when exactly three digits follow it.
    """
    if language == "vi":
        if _PLAIN_COMMA.fullmatch(raw):
            return Decimal(raw.replace(",", "."))
        if _GROUPED_COMMA.fullmatch(raw):
            return Decimal(raw.replace(".", "").replace(",", "."))
        return None
    if _PLAIN_DOT.fullmatch(raw):
        return Decimal(raw)
    if _GROUPED_DOT.fullmatch(raw):
        return Decimal(raw.replace(",", ""))
    return None


@dataclass(frozen=True)
class NumberToken:
    raw: str
    value: Optional[Decimal]


@dataclass(frozen=True)
class Tokens:
    numbers: tuple[NumberToken, ...]
    others: tuple[str, ...]  # 'unit:°C', 'sym:±', 'sym:~', 'sym:neg', 'code:BK01'


def _is_latin_letter(char: str) -> bool:
    return char.isalpha() and "LATIN" in unicodedata.name(char, "")


def _unit_at(text: str, position: int) -> Optional[tuple[str, int]]:
    """Unit right after a number (zero or one space). Returns (unit, end position)."""
    start = position + 1 if text.startswith(" ", position) else position
    for unit in _UNITS_LONGEST_FIRST:
        if not text.startswith(unit, start):
            continue
        end = start + len(unit)
        if end < len(text) and _is_latin_letter(text[end]):
            continue  # '30 min': the 'm' is the start of a word, not a unit
        return unit, end
    return None


def extract_tokens(text: str, language: Language) -> Tokens:
    scanned = normalize(text)
    numbers: list[NumberToken] = []
    others: list[str] = []
    position = 0
    while position < len(scanned):
        char = scanned[position]
        if char in "±~":
            others.append("sym:" + char)
            position += 1
        elif char == "-":
            following = scanned[position + 1 : position + 2]
            previous = scanned[position - 1 : position]
            if following in _ASCII_DIGITS and previous not in _ASCII_ALNUM:
                others.append("sym:neg")
            position += 1
        elif char in _ASCII_LETTERS:
            match = _CODE_RE.match(scanned, position)
            assert match is not None
            word = match.group().rstrip("-_")
            if any(letter in _ASCII_DIGITS for letter in word):
                others.append("code:" + word)
            position = match.end()
        elif char in _ASCII_DIGITS:
            match = _NUMBER_RE.match(scanned, position)
            assert match is not None
            raw = match.group()
            numbers.append(NumberToken(raw=raw, value=parse_number(raw, language)))
            position = match.end()
            unit = _unit_at(scanned, position)
            if unit is not None:
                others.append("unit:" + unit[0])
                position = unit[1]
        else:
            position += 1
    return Tokens(numbers=tuple(numbers), others=tuple(others))
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_tokens.py -q`

Expected: 마지막 줄이 `57 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `233 passed`, `All checks passed!`, `21 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/parsing/test_tokens.py app/parsing/tokens.py
git commit -m "feat: extract numbers, units, signs and codes" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 13: 토큰 비교

설계 §6.2의 "개수까지 비교한다. 순서는 보지 않는다"와 §6.3의 비교 순서 1~3. 번역본 쪽 토큰과 원문 쪽 토큰을 비교해 빠진 것과 더해진 것을 낸다.

**Files:**
- Modify: `app/parsing/tokens.py`
- Test: `tests/parsing/test_token_compare.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/parsing/test_token_compare.py`:

```python
"""Comparing the tokens of a translated text with those of its source."""

from __future__ import annotations

from app.parsing.tokens import compare_tokens, extract_tokens


def _diff(translated, source, source_language):
    """The translation is always Korean."""
    return compare_tokens(extract_tokens(translated, "ko"), extract_tokens(source, source_language))


def test_the_same_tokens_match():
    diff = _diff("배합표 대비 ±1.0% 이내", "Within ±1.0% of the formula sheet", "en")
    assert diff.is_match
    assert (diff.missing, diff.extra) == ((), ())
    assert not diff.ambiguous_translated
    assert not diff.ambiguous_source


def test_the_order_does_not_matter():
    assert _diff("8℃ 이하, 2℃ 이상", "2℃ or above, 8℃ or below", "en").is_match


def test_a_vietnamese_decimal_comma_matches_by_value():
    assert _diff("±1.0% 이내", "Trong phạm vi ±1,0%", "vi").is_match
    assert _diff("1.5 kg", "1,5 kg", "vi").is_match


def test_a_vietnamese_thousands_dot_matches_by_value():
    assert _diff("1000 g", "1.000 g", "vi").is_match
    assert not _diff("1.000 g", "1.000 g", "vi").is_match  # one gram against a thousand


def test_an_english_thousands_comma_matches_by_value():
    assert _diff("1000 g", "1,000 g", "en").is_match
    assert _diff("1,000 g", "1,000 g", "en").is_match


def test_full_width_digits_match():
    assert _diff("180℃", "１８０℃", "zh").is_match


def test_a_changed_number_is_reported_from_both_sides():
    diff = _diff("±2.0% 이내", "Trong phạm vi ±1,0%", "vi")
    assert not diff.is_match
    assert diff.missing == ("num:1,0",)  # in the source, not in the translation
    assert diff.extra == ("num:2.0",)  # in the translation, not in the source
    assert not diff.ambiguous_translated
    assert not diff.ambiguous_source


def test_a_changed_unit_is_reported():
    diff = _diff("±1.0℃ 이내", "Within ±1.0%", "en")
    assert diff.missing == ("unit:%",)
    assert diff.extra == ("unit:°C",)


def test_a_dropped_sign_is_reported():
    assert _diff("18℃ 이하", "-18℃ or below", "en").missing == ("sym:neg",)
    assert _diff("1.0% 이내", "Within ±1.0%", "en").missing == ("sym:±",)
    assert _diff("2, 8℃", "2~8℃", "en").missing == ("sym:~",)


def test_a_changed_code_is_reported():
    diff = _diff("WI-BK-205 에 따른다", "Follow WI-BK-204", "en")
    assert diff.missing == ("code:WI-BK-204",)
    assert diff.extra == ("code:WI-BK-205",)


def test_tokens_are_counted():
    diff = _diff("2회, 2회, 3회", "2 times, 3 times", "en")
    assert diff.missing == ()
    assert diff.extra == ("num:2",)


def test_numbers_that_fit_neither_notation_are_compared_as_strings():
    diff = _diff("1.2.3 항", "Clause 1.2.3", "en")
    assert diff.is_match
    assert not diff.ambiguous_translated
    assert not diff.ambiguous_source


def test_a_number_that_fits_one_side_only_is_compared_as_a_string():
    assert _diff("1,5", "1,5", "en").is_match  # neither fits: same string
    assert _diff("1.5", "1.5", "vi").is_match  # fits Korean only: same string


def test_an_unmatched_number_that_does_not_fit_is_marked_ambiguous():
    diff = _diff("1.5 kg", "1,5 kg", "en")  # '1,5' is not English notation
    assert diff.missing == ("num:1,5",)
    assert diff.extra == ("num:1.5",)
    assert diff.ambiguous_source
    assert not diff.ambiguous_translated

    diff = _diff("1,5 kg", "1.5 kg", "en")
    assert diff.ambiguous_translated
    assert not diff.ambiguous_source


def test_text_without_tokens_matches():
    assert _diff("원료를 확인한다.", "Check the raw material.", "en").is_match
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_token_compare.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ImportError: cannot import name 'compare_tokens' from 'app.parsing.tokens'
1 error
```

- [ ] **Step 3: 구현한다**

이 단계에서 바뀌는 것:

- `TokenDiff`가 생긴다. `missing`은 원문에 있는데 번역본에 없는 토큰, `extra`는 번역본에만 있는 토큰이다. 표기에 맞지 않아 남은 숫자가 어느 쪽에 있는지도 갖는다.
- `compare_tokens(translated, source)`가 생긴다. 숫자는 ① 양쪽 모두 표기에 맞는 것끼리 값으로 지우고 ② 남은 것 중 한쪽이라도 표기에 맞지 않는 것을 문자열로 지우고 ③ 그래도 남으면 불일치다. 단위, 기호, 코드는 개수를 세어 비교한다.

`app/parsing/tokens.py` 전체를 아래 내용으로 바꾼다. 이것이 이 파일의 최종 모습이다:

```python
"""Tokens compared between a translation and its source: numbers, units, symbols, codes.

Only these tokens are compared, by count and without regard to order. The stored text
is never changed; normalization happens only on the copy that is scanned here.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional

from app.models.document import Language

# One place for the unit table. Add units here when real documents show more.
UNITS: tuple[str, ...] = (
    "℃", "°C", "℉", "%", "μm", "mm", "cm", "m", "mg", "g", "kg",
    "mL", "L", "Pa", "kPa", "MPa", "rpm", "ppm",
)  # fmt: skip

# NFKC leaves these two alone, so they are folded by hand: U+2212 minus, U+301C wave dash.
_FOLD = str.maketrans({"−": "-", "〜": "~"})

_PLAIN_DOT = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_GROUPED_DOT = re.compile(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?")
_PLAIN_COMMA = re.compile(r"[0-9]+(?:,[0-9]+)?")
_GROUPED_COMMA = re.compile(r"[0-9]{1,3}(?:\.[0-9]{3})+(?:,[0-9]+)?")

_NUMBER_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
_CODE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_ASCII_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_ASCII_DIGITS = frozenset("0123456789")
_ASCII_ALNUM = _ASCII_LETTERS | _ASCII_DIGITS


def normalize(text: str) -> str:
    """NFKC (full-width -> half-width, '℃' -> '°C') plus the two hand-folded signs."""
    return unicodedata.normalize("NFKC", text).translate(_FOLD)


_UNITS_LONGEST_FIRST: tuple[str, ...] = tuple(
    sorted({normalize(unit) for unit in UNITS}, key=lambda unit: (-len(unit), unit))
)


def parse_number(raw: str, language: Language) -> Optional[Decimal]:
    """Value of `raw` in the notation of `language`, or None if it does not fit.

    ko/en/zh: '.' decimal, ',' thousands. vi: ',' decimal, '.' thousands.
    A thousands separator counts only when exactly three digits follow it.
    """
    if language == "vi":
        if _PLAIN_COMMA.fullmatch(raw):
            return Decimal(raw.replace(",", "."))
        if _GROUPED_COMMA.fullmatch(raw):
            return Decimal(raw.replace(".", "").replace(",", "."))
        return None
    if _PLAIN_DOT.fullmatch(raw):
        return Decimal(raw)
    if _GROUPED_DOT.fullmatch(raw):
        return Decimal(raw.replace(",", ""))
    return None


@dataclass(frozen=True)
class NumberToken:
    raw: str
    value: Optional[Decimal]


@dataclass(frozen=True)
class Tokens:
    numbers: tuple[NumberToken, ...]
    others: tuple[str, ...]  # 'unit:°C', 'sym:±', 'sym:~', 'sym:neg', 'code:BK01'


def _is_latin_letter(char: str) -> bool:
    return char.isalpha() and "LATIN" in unicodedata.name(char, "")


def _unit_at(text: str, position: int) -> Optional[tuple[str, int]]:
    """Unit right after a number (zero or one space). Returns (unit, end position)."""
    start = position + 1 if text.startswith(" ", position) else position
    for unit in _UNITS_LONGEST_FIRST:
        if not text.startswith(unit, start):
            continue
        end = start + len(unit)
        if end < len(text) and _is_latin_letter(text[end]):
            continue  # '30 min': the 'm' is the start of a word, not a unit
        return unit, end
    return None


def extract_tokens(text: str, language: Language) -> Tokens:
    scanned = normalize(text)
    numbers: list[NumberToken] = []
    others: list[str] = []
    position = 0
    while position < len(scanned):
        char = scanned[position]
        if char in "±~":
            others.append("sym:" + char)
            position += 1
        elif char == "-":
            following = scanned[position + 1 : position + 2]
            previous = scanned[position - 1 : position]
            if following in _ASCII_DIGITS and previous not in _ASCII_ALNUM:
                others.append("sym:neg")
            position += 1
        elif char in _ASCII_LETTERS:
            match = _CODE_RE.match(scanned, position)
            assert match is not None
            word = match.group().rstrip("-_")
            if any(letter in _ASCII_DIGITS for letter in word):
                others.append("code:" + word)
            position = match.end()
        elif char in _ASCII_DIGITS:
            match = _NUMBER_RE.match(scanned, position)
            assert match is not None
            raw = match.group()
            numbers.append(NumberToken(raw=raw, value=parse_number(raw, language)))
            position = match.end()
            unit = _unit_at(scanned, position)
            if unit is not None:
                others.append("unit:" + unit[0])
                position = unit[1]
        else:
            position += 1
    return Tokens(numbers=tuple(numbers), others=tuple(others))


@dataclass(frozen=True)
class TokenDiff:
    missing: tuple[str, ...]  # in the source, not in the translation
    extra: tuple[str, ...]  # in the translation, not in the source
    ambiguous_translated: bool
    ambiguous_source: bool

    @property
    def is_match(self) -> bool:
        return not self.missing and not self.extra


def _fits(token: NumberToken) -> bool:
    return token.value is not None


def _unfit(token: NumberToken) -> bool:
    return token.value is None


def _value(token: NumberToken) -> object:
    return token.value


def _raw(token: NumberToken) -> object:
    return token.raw


def _cancel(
    left: list[NumberToken],
    right: list[NumberToken],
    left_ok: Callable[[NumberToken], bool],
    right_ok: Callable[[NumberToken], bool],
    key: Callable[[NumberToken], object],
) -> None:
    """Remove pairs (one from each list) that pass the filters and share a key."""
    for token in list(left):
        if not left_ok(token):
            continue
        for candidate in right:
            if right_ok(candidate) and key(candidate) == key(token):
                left.remove(token)
                right.remove(candidate)
                break


def compare_tokens(translated: Tokens, source: Tokens) -> TokenDiff:
    left = list(translated.numbers)
    right = list(source.numbers)
    # 1. both sides fit their own notation: compare by value
    _cancel(left, right, _fits, _fits, _value)
    # 2. at least one side does not fit: compare as strings
    _cancel(left, right, _unfit, _unfit, _raw)
    _cancel(left, right, _unfit, _fits, _raw)
    _cancel(left, right, _fits, _unfit, _raw)
    # 3. whatever is left is a mismatch

    other_left = Counter(translated.others)
    other_right = Counter(source.others)
    missing = ["num:" + token.raw for token in right]
    missing += sorted((other_right - other_left).elements())
    extra = ["num:" + token.raw for token in left]
    extra += sorted((other_left - other_right).elements())
    return TokenDiff(
        missing=tuple(missing),
        extra=tuple(extra),
        ambiguous_translated=any(_unfit(token) for token in left),
        ambiguous_source=any(_unfit(token) for token in right),
    )
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_token_compare.py -q`

Expected: 마지막 줄이 `15 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `248 passed`, `All checks passed!`, `22 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/parsing/test_token_compare.py app/parsing/tokens.py
git commit -m "feat: compare tokens by value, then by spelling" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 14: 번역본 점검

설계 §6.1과 §6.4. 원문과 번역본의 요소를 짝짓고, 짝마다 토큰을 비교한다.

1. 뼈대(페이지 마커와 헤딩)를 `difflib.SequenceMatcher`로 맞춘다.
2. 맞은 뼈대 사이의 구간마다 요소의 종류가 순서대로 같으면 순번대로 짝짓는다. 다르면 구간 전체를 짝 없음으로 둔다.
3. 표는 행 수와 열 수가 같을 때만 셀끼리 짝짓는다. 이미지는 ID가 같아야 짝이 된다.

**Files:**
- Create: `app/parsing/translation_check.py`
- Test: `tests/parsing/test_translation_check.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/parsing/test_translation_check.py`:

```python
"""Checking a Korean translation against its source (spec section 6)."""

from __future__ import annotations

import pytest

from app.parsing.reader import read_lines
from app.parsing.translation_check import check_translation


@pytest.fixture
def check(make_document):
    """check(korean_lines, source_lines, "en") -> (TranslationCheck, findings)"""

    def _check(translated_lines, source_lines, source_language="en"):
        translated = make_document(translated_lines, "translated", "ko")
        source = make_document(source_lines, "source", source_language)
        return check_translation(translated, source)

    return _check


@pytest.mark.parametrize("language", ["en", "vi", "zh"])
def test_the_sample_translation_matches_its_source(
    make_document, ko_sample, source_samples, language
):
    translated = make_document(read_lines(ko_sample).lines, "translated", "ko")
    source = make_document(read_lines(source_samples[language]).lines, "source", language)
    result, findings = check_translation(translated, source)
    assert len(result.pairs) == 120
    assert {pair.status for pair in result.pairs} == {"match"}
    assert result.unpaired == ()
    assert findings == ()


def test_elements_are_paired_in_order(check):
    result, findings = check(
        ["[PAGE 1]", "## 1 개요", "", "문단이다.", "", "- 항목"],
        ["[PAGE 1]", "## 1 Overview", "", "A paragraph.", "", "- An item"],
    )
    assert [(pair.translated_ref, pair.source_ref, pair.status) for pair in result.pairs] == [
        ("e0001", "e0001", "match"),  # page markers are anchors and count as pairs
        ("e0002", "e0002", "match"),
        ("e0003", "e0003", "match"),
        ("e0004", "e0004", "match"),
    ]
    assert result.unpaired == ()
    assert findings == ()


def test_a_changed_number_in_a_paragraph(check):
    result, findings = check(
        ["[PAGE 1]", "오븐 온도는 190℃로 한다."],
        ["[PAGE 1]", "Set the oven temperature to 180℃."],
    )
    pair = result.pairs[1]
    assert (pair.translated_ref, pair.source_ref) == ("e0002", "e0002")
    assert pair.status == "token_mismatch"
    assert pair.missing_tokens == ("num:180",)
    assert pair.extra_tokens == ("num:190",)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "TOKEN_MISMATCH"
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    assert finding.element_ids == ("e0002",)
    assert finding.counterpart_element_ids == ("e0002",)
    assert finding.cell_ref is None
    assert (finding.line_start, finding.line_end) == (2, 2)
    assert finding.missing_tokens == ("num:180",)
    assert finding.extra_tokens == ("num:190",)


def test_the_title_of_a_heading_is_compared(check):
    _, findings = check(
        ["[PAGE 1]", "## 2 굽기 180℃"],
        ["[PAGE 1]", "## 2 Baking at 190℃"],
    )
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    assert findings[0].missing_tokens == ("num:190",)


def test_the_source_notation_follows_its_language(check):
    lines = ["[PAGE 1]", "1,5 kg"]
    assert check(["[PAGE 1]", "1.5 kg"], lines, "vi")[1] == ()
    assert [finding.code for finding in check(["[PAGE 1]", "1.5 kg"], lines, "en")[1]] == [
        "TOKEN_MISMATCH",
        "NUMBER_FORMAT_AMBIGUOUS",
    ]


def test_an_ambiguous_number_is_reported_on_its_own_side(check):
    _, findings = check(["[PAGE 1]", "", "1.5 kg"], ["[PAGE 1]", "1,5 kg"], "en")
    ambiguous = findings[1]
    assert ambiguous.code == "NUMBER_FORMAT_AMBIGUOUS"
    assert ambiguous.grade == "review_required"
    assert ambiguous.document == "source"
    assert ambiguous.element_ids == ("e0002",)
    assert ambiguous.counterpart_element_ids == ("e0002",)
    assert (ambiguous.line_start, ambiguous.line_end) == (2, 2)  # a line of the source file
    assert (ambiguous.missing_tokens, ambiguous.extra_tokens) == ((), ())

    _, findings = check(["[PAGE 1]", "", "1,5 kg"], ["[PAGE 1]", "1.5 kg"], "en")
    assert [(finding.code, finding.document) for finding in findings] == [
        ("TOKEN_MISMATCH", "translated"),
        ("NUMBER_FORMAT_AMBIGUOUS", "translated"),
    ]
    assert (findings[1].line_start, findings[1].line_end) == (3, 3)


def test_a_different_order_of_kinds_leaves_the_whole_segment_unpaired(check):
    result, findings = check(
        ["[PAGE 1]", "## 1 개요", "", "문단이다.", "", "- 항목", "", "[PAGE 2]", "끝 문단."],
        ["[PAGE 1]", "## 1 Overview", "", "- An item", "", "A paragraph.", "", "[PAGE 2]", "End."],
    )
    assert len(result.unpaired) == 1
    segment = result.unpaired[0]
    assert segment.reason == "SEGMENT_UNALIGNED"
    assert segment.translated_element_ids == ("e0003", "e0004")
    assert segment.source_element_ids == ("e0003", "e0004")
    # the segments before and after it are still paired
    assert [pair.translated_ref for pair in result.pairs] == ["e0001", "e0002", "e0005", "e0006"]

    assert [finding.code for finding in findings] == ["SEGMENT_UNALIGNED"]
    finding = findings[0]
    assert finding.document == "translated"
    assert finding.element_ids == ("e0003", "e0004")
    assert finding.counterpart_element_ids == ("e0003", "e0004")
    assert (finding.line_start, finding.line_end) == (4, 6)


def test_content_missing_from_the_translation(check):
    result, findings = check(
        ["[PAGE 1]", "## 1 개요"],
        ["[PAGE 1]", "## 1 Overview", "", "A paragraph only the source has."],
    )
    assert [finding.code for finding in findings] == ["SEGMENT_UNALIGNED"]
    finding = findings[0]
    assert finding.document == "translated"
    assert finding.element_ids == ()  # nothing on the translated side to point at
    assert finding.counterpart_element_ids == ("e0003",)
    assert (finding.line_start, finding.line_end) == (None, None)
    assert result.unpaired[0].translated_element_ids == ()
    assert result.unpaired[0].source_element_ids == ("e0003",)


def test_images_pair_only_with_the_same_id(check):
    result, findings = check(
        ["[PAGE 1]", "앞 문단.", "", '![img001](<img001.png "화면">)', "", "뒤 문단."],
        ["[PAGE 1]", "Before.", "", '![img002](<img002.png "Screen">)', "", "After."],
    )
    assert [finding.code for finding in findings] == ["SEGMENT_UNALIGNED"]
    assert findings[0].element_ids == ("e0003",)
    assert findings[0].counterpart_element_ids == ("e0003",)
    assert (findings[0].line_start, findings[0].line_end) == (4, 4)
    assert [pair.translated_ref for pair in result.pairs] == ["e0001", "e0002", "e0004"]

    result, findings = check(
        ["[PAGE 1]", '![img001](<img001.png "화면">)'],
        ["[PAGE 1]", '![img001](<img001.png "Screen">)'],
    )
    assert findings == ()
    assert [pair.status for pair in result.pairs] == ["match", "match"]


TABLE_KO = ["[PAGE 1]", "", "|구분|기준|", "|---|---|", "|온도|2~8℃|", "|중량|±1.0%|"]
TABLE_EN = ["[PAGE 1]", "|Item|Limit|", "|---|---|", "|Temperature|2~8℃|", "|Weight|±1.0%|"]


def test_table_cells_are_paired_one_by_one(check):
    result, findings = check(TABLE_KO, TABLE_EN)
    assert findings == ()
    assert [(pair.translated_ref, pair.source_ref) for pair in result.pairs[1:]] == [
        ("e0002:r0c1", "e0002:r0c1"),  # row 0 is the header
        ("e0002:r0c2", "e0002:r0c2"),
        ("e0002:r1c1", "e0002:r1c1"),
        ("e0002:r1c2", "e0002:r1c2"),
        ("e0002:r2c1", "e0002:r2c1"),
        ("e0002:r2c2", "e0002:r2c2"),
    ]


def test_a_changed_cell_is_located_by_cell_and_line(check):
    translated = [*TABLE_KO[:5], "|중량|±2.0%|"]
    result, findings = check(translated, TABLE_EN)
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    finding = findings[0]
    assert finding.element_ids == ("e0002",)
    assert finding.cell_ref == "e0002:r2c2"
    assert (finding.line_start, finding.line_end) == (6, 6)  # the line of that row
    assert finding.missing_tokens == ("num:1.0",)
    assert finding.extra_tokens == ("num:2.0",)
    assert [pair.translated_ref for pair in result.pairs if pair.status != "match"] == [
        "e0002:r2c2"
    ]


def test_a_changed_header_cell_is_on_the_first_line_of_the_table(check):
    translated = ["[PAGE 1]", "", "|구분 1|기준|", *TABLE_KO[3:]]
    _, findings = check(translated, TABLE_EN)
    assert [finding.cell_ref for finding in findings] == ["e0002:r0c1"]
    assert (findings[0].line_start, findings[0].line_end) == (3, 3)


def test_an_ambiguous_number_in_a_source_cell_points_at_the_source_line(check):
    source = [*TABLE_EN[:4], "|Weight|±1,0%|"]
    _, findings = check(TABLE_KO, source, "en")
    assert [(finding.code, finding.document) for finding in findings] == [
        ("TOKEN_MISMATCH", "translated"),
        ("NUMBER_FORMAT_AMBIGUOUS", "source"),
    ]
    assert findings[0].cell_ref == "e0002:r2c2"
    assert (findings[0].line_start, findings[0].line_end) == (6, 6)
    assert findings[1].cell_ref == "e0002:r2c2"
    assert (findings[1].line_start, findings[1].line_end) == (5, 5)


@pytest.mark.parametrize(
    "translated",
    [
        TABLE_KO[:5],  # one row fewer
        [*TABLE_KO, "|습도|60%|"],  # one row more
        ["[PAGE 1]", "", "|구분|기준|비고|", "|---|---|---|", "|온도|2~8℃|-|", "|중량|±1.0%|-|"],
    ],
)
def test_tables_of_a_different_shape_are_not_paired(check, translated):
    result, findings = check(translated, TABLE_EN)
    assert [finding.code for finding in findings] == ["TABLE_SHAPE_MISMATCH"]
    finding = findings[0]
    assert finding.document == "translated"
    assert finding.element_ids == ("e0002",)
    assert finding.counterpart_element_ids == ("e0002",)
    assert finding.cell_ref is None
    assert finding.line_start == 3
    assert [pair.translated_ref for pair in result.pairs] == ["e0001"]  # no cell was compared
    assert [segment.reason for segment in result.unpaired] == ["TABLE_SHAPE_MISMATCH"]


def test_a_missing_heading_leaves_its_surroundings_unpaired(check):
    result, findings = check(
        ["[PAGE 1]", "## 1 개요", "", "문단 1.", "", "문단 2.", "", "[PAGE 2]", "끝 문단."],
        ["[PAGE 1]", "## 1 Overview", "", "One.", "", "## 2 Scope", "", "Two.", "[PAGE 2]", "End."],
    )
    assert [finding.code for finding in findings] == ["SKELETON_MISMATCH"]
    finding = findings[0]
    assert finding.document == "translated"
    assert finding.element_ids == ("e0003", "e0004")
    assert finding.counterpart_element_ids == ("e0003", "e0004", "e0005")
    assert (finding.line_start, finding.line_end) == (4, 6)
    assert [segment.reason for segment in result.unpaired] == ["SKELETON_MISMATCH"]
    # the matching page markers and headings around it still anchor the rest
    assert [(pair.translated_ref, pair.source_ref) for pair in result.pairs] == [
        ("e0001", "e0001"),
        ("e0002", "e0002"),
        ("e0005", "e0006"),
        ("e0006", "e0007"),
    ]


def test_a_different_page_number_is_a_skeleton_mismatch(check):
    result, findings = check(
        ["[PAGE 1]", "문단 1.", "", "[PAGE 2]", "문단 2."],
        ["[PAGE 1]", "One.", "", "[PAGE 3]", "Two."],
    )
    assert [finding.code for finding in findings] == ["SKELETON_MISMATCH"]
    assert findings[0].element_ids == ("e0002", "e0003", "e0004")
    assert findings[0].counterpart_element_ids == ("e0002", "e0003", "e0004")
    assert [pair.translated_ref for pair in result.pairs] == ["e0001"]


def test_a_different_heading_number_is_a_skeleton_mismatch(check):
    _, findings = check(
        ["[PAGE 1]", "## 1 개요", "", "## 2 범위"],
        ["[PAGE 1]", "## 1 Overview", "", "## 3 Scope"],
    )
    assert [finding.code for finding in findings] == ["SKELETON_MISMATCH"]
    assert findings[0].element_ids == ("e0003",)
    assert findings[0].counterpart_element_ids == ("e0003",)


def test_documents_with_nothing_in_common(check):
    result, findings = check(["문단이다."], ["[PAGE 1]", "A paragraph."])
    assert [finding.code for finding in findings] == ["SKELETON_MISMATCH"]
    assert result.pairs == ()
    assert result.unpaired[0].translated_element_ids == ("e0001",)
    assert result.unpaired[0].source_element_ids == ("e0001", "e0002")
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_translation_check.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ModuleNotFoundError: No module named 'app.parsing.translation_check'
1 error
```

- [ ] **Step 3: 구현한다**

`app/parsing/translation_check.py`:

```python
"""Check a Korean translation (rag_ko.md) against its source (rag.md).

This is a check inside one target document, not a comparison of baseline and target.
Elements are paired one-to-one (D-008); where that fails the segment stays unpaired
and nothing is guessed about which element is missing.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Optional, Sequence

from app.models.document import Document, Element, Language, cell_ref
from app.models.findings import (
    Finding,
    FindingCode,
    PairResult,
    TranslationCheck,
    UnpairedSegment,
    new_finding,
)
from app.parsing.tokens import compare_tokens, extract_tokens

_SKELETON_KINDS = ("page_marker", "heading")


def _skeleton_key(element: Element) -> tuple:
    if element.kind == "page_marker":
        return ("page", element.page)
    return ("heading", element.level, element.number or "")


def _ids(elements: Sequence[Element]) -> tuple[str, ...]:
    return tuple(element.element_id for element in elements)


class _Checker:
    def __init__(self, translated_language: Language, source_language: Language) -> None:
        self.translated_language = translated_language
        self.source_language = source_language
        self.pairs: list[PairResult] = []
        self.unpaired: list[UnpairedSegment] = []
        self.findings: list[Finding] = []

    def unpair(
        self,
        code: FindingCode,
        translated: Sequence[Element],
        source: Sequence[Element],
    ) -> None:
        assert code in ("SKELETON_MISMATCH", "SEGMENT_UNALIGNED", "TABLE_SHAPE_MISMATCH")
        self.unpaired.append(
            UnpairedSegment(
                reason=code,
                translated_element_ids=_ids(translated),
                source_element_ids=_ids(source),
            )
        )
        self.findings.append(
            new_finding(
                code,
                "translated",
                element_ids=_ids(translated),
                counterpart_element_ids=_ids(source),
                line_start=translated[0].locator.line_start if translated else None,
                line_end=translated[-1].locator.line_end if translated else None,
            )
        )

    def compare_text(
        self,
        translated: Element,
        source: Element,
        translated_text: str,
        source_text: str,
        *,
        translated_cell: Optional[str] = None,
        source_cell: Optional[str] = None,
        line: Optional[int] = None,
        source_line: Optional[int] = None,
    ) -> None:
        diff = compare_tokens(
            extract_tokens(translated_text, self.translated_language),
            extract_tokens(source_text, self.source_language),
        )
        self.pairs.append(
            PairResult(
                translated_ref=translated_cell or translated.element_id,
                source_ref=source_cell or source.element_id,
                status="match" if diff.is_match else "token_mismatch",
                missing_tokens=diff.missing,
                extra_tokens=diff.extra,
            )
        )
        translated_lines = (
            (line, line)
            if line is not None
            else (translated.locator.line_start, translated.locator.line_end)
        )
        source_lines = (
            (source_line, source_line)
            if source_line is not None
            else (source.locator.line_start, source.locator.line_end)
        )
        if not diff.is_match:
            self.findings.append(
                new_finding(
                    "TOKEN_MISMATCH",
                    "translated",
                    element_ids=(translated.element_id,),
                    counterpart_element_ids=(source.element_id,),
                    cell_ref=translated_cell,
                    line_start=translated_lines[0],
                    line_end=translated_lines[1],
                    missing_tokens=diff.missing,
                    extra_tokens=diff.extra,
                )
            )
        if diff.ambiguous_translated:
            self.findings.append(
                new_finding(
                    "NUMBER_FORMAT_AMBIGUOUS",
                    "translated",
                    element_ids=(translated.element_id,),
                    counterpart_element_ids=(source.element_id,),
                    cell_ref=translated_cell,
                    line_start=translated_lines[0],
                    line_end=translated_lines[1],
                )
            )
        if diff.ambiguous_source:
            self.findings.append(
                new_finding(
                    "NUMBER_FORMAT_AMBIGUOUS",
                    "source",
                    element_ids=(source.element_id,),
                    counterpart_element_ids=(translated.element_id,),
                    cell_ref=source_cell,
                    line_start=source_lines[0],
                    line_end=source_lines[1],
                )
            )

    def pair(self, translated: Element, source: Element) -> None:
        """Both elements have the same kind."""
        if translated.kind == "page_marker":
            self.pairs.append(
                PairResult(
                    translated_ref=translated.element_id,
                    source_ref=source.element_id,
                    status="match",
                )
            )
        elif translated.kind == "heading":
            self.compare_text(translated, source, translated.title, source.title)
        elif translated.kind == "table":
            self.pair_table(translated, source)
        elif translated.kind == "image" and translated.image_id != source.image_id:
            self.unpair("SEGMENT_UNALIGNED", [translated], [source])
        else:
            self.compare_text(translated, source, translated.text, source.text)

    def pair_table(self, translated: Element, source: Element) -> None:
        def shape(table: Element) -> tuple:
            return (len(table.header), tuple(len(row) for row in table.rows))

        if shape(translated) != shape(source):
            self.unpair("TABLE_SHAPE_MISMATCH", [translated], [source])
            return
        headers = zip(translated.header, source.header, strict=True)
        for col, (left, right) in enumerate(headers, start=1):
            self.compare_text(
                translated,
                source,
                left,
                right,
                translated_cell=cell_ref(translated.element_id, 0, col),
                source_cell=cell_ref(source.element_id, 0, col),
                line=translated.locator.line_start,
                source_line=source.locator.line_start,
            )
        for left_row, right_row in zip(translated.rows, source.rows, strict=True):
            for left, right in zip(left_row, right_row, strict=True):
                self.compare_text(
                    translated,
                    source,
                    left.text,
                    right.text,
                    translated_cell=cell_ref(translated.element_id, left.row, left.col),
                    source_cell=cell_ref(source.element_id, right.row, right.col),
                    # line 1 of a table is the header, line 2 the separator
                    line=translated.locator.line_start + 1 + left.row,
                    source_line=source.locator.line_start + 1 + right.row,
                )

    def gap(self, translated: Sequence[Element], source: Sequence[Element]) -> None:
        """Elements between two matched skeleton elements."""
        if not translated and not source:
            return
        if any(element.kind in _SKELETON_KINDS for element in (*translated, *source)):
            self.unpair("SKELETON_MISMATCH", translated, source)
        elif [element.kind for element in translated] == [element.kind for element in source]:
            for left, right in zip(translated, source, strict=True):
                self.pair(left, right)
        else:
            self.unpair("SEGMENT_UNALIGNED", translated, source)


def _anchors(translated: Document, source: Document) -> list[tuple[int, int]]:
    """Index pairs of skeleton elements (page markers, headings) that match."""
    left = [
        (index, _skeleton_key(element))
        for index, element in enumerate(translated.elements)
        if element.kind in _SKELETON_KINDS
    ]
    right = [
        (index, _skeleton_key(element))
        for index, element in enumerate(source.elements)
        if element.kind in _SKELETON_KINDS
    ]
    left_keys = [key for _, key in left]
    right_keys = [key for _, key in right]
    if left_keys == right_keys:
        return [(a, b) for (a, _), (b, _) in zip(left, right, strict=True)]
    matcher = SequenceMatcher(None, left_keys, right_keys, autojunk=False)
    anchors: list[tuple[int, int]] = []
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            anchors.append((left[block.a + offset][0], right[block.b + offset][0]))
    return anchors


def check_translation(
    translated: Document, source: Document
) -> tuple[TranslationCheck, tuple[Finding, ...]]:
    checker = _Checker(translated.language, source.language)
    previous_left = previous_right = -1
    for left_index, right_index in _anchors(translated, source):
        checker.gap(
            translated.elements[previous_left + 1 : left_index],
            source.elements[previous_right + 1 : right_index],
        )
        checker.pair(translated.elements[left_index], source.elements[right_index])
        previous_left, previous_right = left_index, right_index
    checker.gap(
        translated.elements[previous_left + 1 :],
        source.elements[previous_right + 1 :],
    )
    return (
        TranslationCheck(pairs=tuple(checker.pairs), unpaired=tuple(checker.unpaired)),
        tuple(checker.findings),
    )
```

`check_translation(translated, source)`는 `(TranslationCheck, 발견 항목 튜플)`을 돌려준다. 어느 요소가 빠졌는지 추측하지 않는다. 구간 안에서 종류가 한 군데라도 다르면 그 구간의 요소를 모두 짝 없음으로 둔다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_translation_check.py -q`

Expected: 마지막 줄이 `22 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `270 passed`, `All checks passed!`, `24 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/parsing/test_translation_check.py app/parsing/translation_check.py
git commit -m "feat: pair source and translation and compare their tokens" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 15: 변형 테스트

설계 §10의 "번역본 점검" 뒷부분과 완료 기준 5. 새 코드는 없다. 한국어 샘플을 테스트 안에서 코드로 망가뜨리고, 예상한 코드가 예상한 요소에 붙는지 세 언어 모두에서 확인한다.

| 변형 | 기대하는 코드 |
|---|---|
| 숫자 바꾸기, 단위 바꾸기, 음수 부호 지우기, 코드 바꾸기 | `TOKEN_MISMATCH` |
| 표의 행 삭제 | `TABLE_SHAPE_MISMATCH` |
| 문단 삭제 | `SEGMENT_UNALIGNED` |
| 헤딩 삭제, 페이지 번호 바꾸기 | `SKELETON_MISMATCH` |

**Files:**
- Test: `tests/parsing/test_translation_mutations.py`

- [ ] **Step 1: 테스트를 쓴다**

`tests/parsing/test_translation_mutations.py`:

```python
"""Damage the Korean sample on purpose and check that the damage is pinpointed.

Line numbers refer to tests/fixtures/rag_ko/sample_bakery_sop.md:
  line 39  |계량중량|전자저울 계량|배합표 대비 ±1.0% 이내|   -> e0017:r2c3
  line 40  the next row of the same table (e0017, lines 36-42)
  line 44  a paragraph (e0018)
  line 56  the heading '### 3.3 ...' (e0024)
"""

from __future__ import annotations

import pytest

from app.parsing.reader import read_lines
from app.parsing.translation_check import check_translation

LANGUAGES = ["en", "vi", "zh"]


@pytest.fixture
def check_mutated(make_document, ko_sample, source_samples):
    """check_mutated("vi", mutate) -> (TranslationCheck, findings); mutate edits the line list."""

    def _check(language, mutate):
        lines = list(read_lines(ko_sample).lines)
        mutate(lines)
        translated = make_document(lines, "translated", "ko")
        source = make_document(read_lines(source_samples[language]).lines, "source", language)
        return check_translation(translated, source)

    return _check


def _replace(line_number, old, new):
    def mutate(lines):
        assert old in lines[line_number - 1]
        lines[line_number - 1] = lines[line_number - 1].replace(old, new)

    return mutate


def _delete(line_number):
    def mutate(lines):
        del lines[line_number - 1]

    return mutate


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_changed_number_is_pinpointed(check_mutated, language):
    result, findings = check_mutated(language, _replace(39, "±1.0%", "±2.0%"))
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    finding = findings[0]
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    assert finding.element_ids == ("e0017",)
    assert finding.counterpart_element_ids == ("e0017",)
    assert finding.cell_ref == "e0017:r2c3"
    assert (finding.line_start, finding.line_end) == (39, 39)
    # the source token is shown as it is written in the source language
    source_token = "num:1,0" if language == "vi" else "num:1.0"
    assert finding.missing_tokens == (source_token,)
    assert finding.extra_tokens == ("num:2.0",)

    assert len(result.pairs) == 120
    assert [pair.translated_ref for pair in result.pairs if pair.status != "match"] == [
        "e0017:r2c3"
    ]
    assert result.unpaired == ()


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_changed_unit_is_pinpointed(check_mutated, language):
    _, findings = check_mutated(language, _replace(39, "±1.0%", "±1.0℃"))
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    assert findings[0].cell_ref == "e0017:r2c3"
    assert (findings[0].line_start, findings[0].line_end) == (39, 39)
    assert findings[0].missing_tokens == ("unit:%",)
    assert findings[0].extra_tokens == ("unit:°C",)


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_dropped_minus_sign_is_pinpointed(check_mutated, language):
    _, findings = check_mutated(language, _replace(103, "-18℃", "18℃"))
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    assert findings[0].cell_ref == "e0042:r4c2"
    assert (findings[0].line_start, findings[0].line_end) == (103, 103)
    assert findings[0].missing_tokens == ("sym:neg",)
    assert findings[0].extra_tokens == ()


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_changed_code_is_pinpointed(check_mutated, language):
    _, findings = check_mutated(language, _replace(52, "WI-BK-204", "WI-BK-205"))
    assert [finding.code for finding in findings] == ["TOKEN_MISMATCH"]
    assert findings[0].element_ids == ("e0022",)
    assert findings[0].cell_ref is None
    assert (findings[0].line_start, findings[0].line_end) == (52, 52)
    assert findings[0].missing_tokens == ("code:WI-BK-204",)
    assert findings[0].extra_tokens == ("code:WI-BK-205",)


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_deleted_table_row_is_pinpointed(check_mutated, language):
    result, findings = check_mutated(language, _delete(40))
    assert [finding.code for finding in findings] == ["TABLE_SHAPE_MISMATCH"]
    finding = findings[0]
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    assert finding.element_ids == ("e0017",)
    assert finding.counterpart_element_ids == ("e0017",)
    assert (finding.line_start, finding.line_end) == (36, 41)

    assert len(result.unpaired) == 1
    assert result.unpaired[0].reason == "TABLE_SHAPE_MISMATCH"
    # the 18 cells of that table are not compared; everything else still is
    assert len(result.pairs) == 120 - 18
    assert {pair.status for pair in result.pairs} == {"match"}


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_deleted_paragraph_is_narrowed_to_its_segment(check_mutated, language):
    result, findings = check_mutated(language, _delete(44))
    assert [finding.code for finding in findings] == ["SEGMENT_UNALIGNED"]
    finding = findings[0]
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    # everything between the heading 3.2 and the page marker of page 10
    assert finding.element_ids == ("e0016", "e0017", "e0018", "e0019", "e0020", "e0021")
    assert finding.counterpart_element_ids == (
        "e0016",
        "e0017",
        "e0018",
        "e0019",
        "e0020",
        "e0021",
        "e0022",
    )
    assert (finding.line_start, finding.line_end) == (34, 51)

    assert len(result.unpaired) == 1
    assert result.unpaired[0].reason == "SEGMENT_UNALIGNED"
    assert {pair.status for pair in result.pairs} == {"match"}
    # the page marker of page 10 is paired again: one element earlier in the translation
    assert ("e0022", "e0023") in [(pair.translated_ref, pair.source_ref) for pair in result.pairs]


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_deleted_heading_is_a_skeleton_mismatch(check_mutated, language):
    result, findings = check_mutated(language, _delete(56))
    assert [finding.code for finding in findings] == ["SKELETON_MISMATCH"]
    finding = findings[0]
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    # everything between the page markers of page 10 and page 11
    assert finding.element_ids == tuple(f"e{n:04d}" for n in range(24, 35))
    assert finding.counterpart_element_ids == tuple(f"e{n:04d}" for n in range(24, 36))
    assert (finding.line_start, finding.line_end) == (57, 85)

    assert len(result.unpaired) == 1
    assert result.unpaired[0].reason == "SKELETON_MISMATCH"
    assert {pair.status for pair in result.pairs} == {"match"}
    assert ("e0035", "e0036") in [(pair.translated_ref, pair.source_ref) for pair in result.pairs]


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_changed_page_number_is_a_skeleton_mismatch(check_mutated, language):
    _, findings = check_mutated(language, _replace(54, "[PAGE 10]", "[PAGE 12]"))
    assert "SKELETON_MISMATCH" in [finding.code for finding in findings]
    assert {finding.grade for finding in findings} == {"review_required"}
```

- [ ] **Step 2: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_translation_mutations.py -q`

Expected: 마지막 줄이 `24 passed`

이 테스트는 처음부터 통과해야 한다. 실패하면 Task 14의 구현이 계획과 다른 것이다. **샘플 파일과 기대값을 고치지 않는다.** 실패한 테스트 이름과 출력을 사용자에게 알린다.

- [ ] **Step 3: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `294 passed`, `All checks passed!`, `25 files already formatted`

- [ ] **Step 4: 커밋한다**

```bash
git add tests/parsing/test_translation_mutations.py
git commit -m "test: damage the sample translation and check that the damage is pinpointed" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 16: 품질 판정

설계 §7.1과 §7.2. 발견 항목 목록에서 결과 상태를 정하고, 문서별로 막힌 요소를 구한다. 비율로 합격·불합격을 정하지 않는다. "검토 필요" 발견 항목이 하나라도 있으면 `REVIEW_REQUIRED`다.

**Files:**
- Create: `app/parsing/quality.py`
- Test: `tests/parsing/test_quality.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/parsing/test_quality.py`:

```python
"""From findings to a status, and to the elements a finding blocks (D-013)."""

from __future__ import annotations

import pytest

from app.models.findings import new_finding
from app.parsing.quality import blocked_element_ids, decide_status

LINES = ["[PAGE 1]", "## 1 개요", "", "문단 1.", "", "문단 2."]  # e0001 .. e0004


@pytest.fixture
def translated(make_document):
    return make_document(LINES, "translated", "ko")


@pytest.fixture
def source(make_document):
    return make_document(LINES, "source", "en")


def test_no_findings_is_ok():
    assert decide_status([]) == "OK"


def test_info_findings_alone_are_ok():
    findings = [
        new_finding("IMAGE_PRESENT", "source", element_ids=("e0003",)),
        new_finding("HEADING_NUMBER_MISMATCH", "source", element_ids=("e0002",)),
    ]
    assert decide_status(findings) == "OK"


@pytest.mark.parametrize(
    "code",
    [
        "UNCLASSIFIED_LINE",
        "AMBIGUOUS_LIST_OR_NEGATIVE",
        "TABLE_ROW_WIDTH_MISMATCH",
        "NO_PAGE_MARKER",
        "CONTENT_BEFORE_FIRST_PAGE",
        "PAGE_NUMBER_NOT_INCREASING",
        "SOURCE_NOT_PROVIDED",
        "SKELETON_MISMATCH",
        "SEGMENT_UNALIGNED",
        "TABLE_SHAPE_MISMATCH",
        "TOKEN_MISMATCH",
        "NUMBER_FORMAT_AMBIGUOUS",
    ],
)
def test_one_review_finding_is_enough(code):
    findings = [
        new_finding("IMAGE_PRESENT", "source", element_ids=("e0003",)),
        new_finding(code, "source"),
    ]
    assert decide_status(findings) == "REVIEW_REQUIRED"


def test_the_status_is_never_decided_by_a_ratio():
    """One finding among many clean elements still asks for review."""
    findings = [new_finding("IMAGE_PRESENT", "source", element_ids=("e0003",))] * 500
    findings.append(new_finding("TOKEN_MISMATCH", "translated", element_ids=("e0004",)))
    assert decide_status(findings) == "REVIEW_REQUIRED"


def test_nothing_is_blocked_without_findings(translated):
    assert blocked_element_ids(translated, []) == frozenset()


def test_a_finding_blocks_its_elements_on_both_sides(translated, source):
    finding = new_finding(
        "TOKEN_MISMATCH",
        "translated",
        element_ids=("e0003",),
        counterpart_element_ids=("e0004",),
    )
    assert blocked_element_ids(translated, [finding]) == {"e0003"}
    assert blocked_element_ids(source, [finding]) == {"e0004"}


def test_a_segment_finding_blocks_every_element_of_the_segment(translated, source):
    finding = new_finding(
        "SEGMENT_UNALIGNED",
        "translated",
        element_ids=("e0003", "e0004"),
        counterpart_element_ids=("e0002", "e0003", "e0004"),
    )
    assert blocked_element_ids(translated, [finding]) == {"e0003", "e0004"}
    assert blocked_element_ids(source, [finding]) == {"e0002", "e0003", "e0004"}


def test_a_finding_raised_on_the_source_side(translated, source):
    finding = new_finding(
        "NUMBER_FORMAT_AMBIGUOUS",
        "source",
        element_ids=("e0004",),
        counterpart_element_ids=("e0003",),
    )
    assert blocked_element_ids(source, [finding]) == {"e0004"}
    assert blocked_element_ids(translated, [finding]) == {"e0003"}


def test_info_findings_block_nothing(translated, source):
    findings = [
        new_finding("IMAGE_PRESENT", "translated", element_ids=("e0003",)),
        new_finding("HEADING_NUMBER_MISMATCH", "source", element_ids=("e0002",)),
    ]
    assert blocked_element_ids(translated, findings) == frozenset()
    assert blocked_element_ids(source, findings) == frozenset()


@pytest.mark.parametrize("code", ["NO_PAGE_MARKER", "SOURCE_NOT_PROVIDED"])
def test_a_document_scope_finding_blocks_the_whole_document(translated, source, code):
    finding = new_finding(code, "translated")
    assert blocked_element_ids(translated, [finding]) == {"e0001", "e0002", "e0003", "e0004"}
    assert blocked_element_ids(source, [finding]) == frozenset()


def test_findings_add_up(translated):
    findings = [
        new_finding("UNCLASSIFIED_LINE", "translated", element_ids=("e0003",)),
        new_finding("TOKEN_MISMATCH", "translated", element_ids=("e0004",)),
        new_finding("IMAGE_PRESENT", "translated", element_ids=("e0002",)),
    ]
    assert blocked_element_ids(translated, findings) == {"e0003", "e0004"}
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_quality.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ModuleNotFoundError: No module named 'app.parsing.quality'
1 error
```

- [ ] **Step 3: 구현한다**

`app/parsing/quality.py`:

```python
"""Findings -> result status, and which elements a finding blocks (D-013).

A document is never passed or failed by a ratio. Findings block the elements they point at.
"""

from __future__ import annotations

from typing import Iterable

from app.models.document import Document
from app.models.findings import DOCUMENT_SCOPE_CODES, Finding, Status


def decide_status(findings: Iterable[Finding]) -> Status:
    """REVIEW_REQUIRED if any finding has the grade 'review_required', otherwise OK."""
    if any(finding.grade == "review_required" for finding in findings):
        return "REVIEW_REQUIRED"
    return "OK"


def blocked_element_ids(document: Document, findings: Iterable[Finding]) -> frozenset[str]:
    """IDs of the elements of `document` that a later verdict may not rely on for a PASS.

    A document-scope finding blocks every element of its document. Other findings block
    `element_ids` in their own document and `counterpart_element_ids` in the other one.
    Findings with the grade 'info' block nothing.
    """
    blocked: set[str] = set()
    for finding in findings:
        if finding.grade != "review_required":
            continue
        if finding.document == document.variant:
            if finding.code in DOCUMENT_SCOPE_CODES:
                return frozenset(element.element_id for element in document.elements)
            blocked.update(finding.element_ids)
        else:
            blocked.update(finding.counterpart_element_ids)
    return frozenset(blocked)
```

`decide_status()`는 `OK`와 `REVIEW_REQUIRED`만 돌려준다. `FAILED`는 문서를 만들지 못했을 때 Task 17의 `ingest()`가 정한다. `blocked_element_ids()`는 단위 ④가 "걸린 요소에 의존하는 판정은 PASS가 될 수 없다"를 지키는 데 쓴다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_quality.py -q`

Expected: 마지막 줄이 `23 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `317 passed`, `All checks passed!`, `27 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/parsing/test_quality.py app/parsing/quality.py
git commit -m "feat: decide the status from findings and list blocked elements" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 17: 전체 흐름

설계 §7.1, §7.3, §7.4와 완료 기준 6. 파일 읽기 → 파싱 → 줄 누락 검사 → 번역본 점검 → 품질 판정을 한 함수로 묶는다.

- 예상한 입력 문제(없는 파일, UTF-8이 아닌 파일, 빈 파일)는 `FAILED`와 사유로 돌려준다.
- 예상하지 못한 예외는 맨 바깥에서 잡아 `FAILED` / `INTERNAL_ERROR`로 바꾼다. 일부만 처리된 문서를 결과에 싣지 않는다.
- 로그에는 코드, 줄 수, 요소 수, 개수만 쓴다.
- 결과에 `PARSER_VERSION`을 남긴다.

**Files:**
- Create: `app/parsing/ingest.py`
- Test: `tests/parsing/test_ingest.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/parsing/test_ingest.py`:

```python
"""The whole flow, including broken input. Nothing may crash and nothing broken may pass."""

from __future__ import annotations

import hashlib
import logging
from collections import Counter

import pytest

from app.parsing import ingest as ingest_module
from app.parsing.ingest import PARSER_VERSION, ingest

SOURCE_LANGUAGES = ["en", "vi", "zh"]


def _ingest(path, original_language="ko", source_path=None):
    return ingest(
        path,
        doc_id="SOP-SAMPLE",
        version="1",
        original_language=original_language,
        source_path=source_path,
    )


def _codes(result):
    return Counter(finding.code for finding in result.findings)


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


# --- normal input ---------------------------------------------------------------------


def test_a_korean_baseline_document(ko_sample):
    result = _ingest(ko_sample)
    assert result.status == "OK"
    assert result.parser_version == PARSER_VERSION
    assert result.failure is None
    assert result.translation_check is None
    assert _codes(result) == {"IMAGE_PRESENT": 3}

    assert len(result.documents) == 1
    document = result.documents[0]
    assert document.doc_id == "SOP-SAMPLE"
    assert document.version == "1"
    assert document.variant == "source"  # never translated: it is its own source
    assert document.language == "ko"
    assert document.file_name == "sample_bakery_sop.md"
    assert document.sha256 == hashlib.sha256(ko_sample.read_bytes()).hexdigest()
    assert len(document.elements) == 49


@pytest.mark.parametrize("language", SOURCE_LANGUAGES)
def test_a_translated_document_with_its_source(ko_sample, source_samples, language):
    result = _ingest(ko_sample, language, source_samples[language])
    assert result.status == "OK"
    assert _codes(result) == {"IMAGE_PRESENT": 6}

    translated, source = result.documents  # the main file first
    assert (translated.variant, translated.language) == ("translated", "ko")
    assert (source.variant, source.language) == ("source", language)
    assert source.file_name == f"sample_bakery_sop.{language}.md"
    assert source.sha256 == hashlib.sha256(source_samples[language].read_bytes()).hexdigest()
    assert (translated.doc_id, source.doc_id) == ("SOP-SAMPLE", "SOP-SAMPLE")

    assert len(result.translation_check.pairs) == 120
    assert result.translation_check.unpaired == ()


@pytest.mark.parametrize("language", SOURCE_LANGUAGES)
def test_a_translated_document_without_its_source_needs_review(ko_sample, language):
    result = _ingest(ko_sample, language)
    assert result.status == "REVIEW_REQUIRED"
    assert _codes(result) == {"IMAGE_PRESENT": 3, "SOURCE_NOT_PROVIDED": 1}
    finding = [f for f in result.findings if f.code == "SOURCE_NOT_PROVIDED"][0]
    assert finding.grade == "review_required"
    assert finding.document == "translated"
    assert finding.element_ids == ()  # it is about the whole document
    assert result.translation_check is None
    assert [document.variant for document in result.documents] == ["translated"]


def test_a_korean_baseline_document_takes_no_source(ko_sample, source_samples):
    with pytest.raises(ValueError):
        _ingest(ko_sample, "ko", source_samples["en"])


def test_a_changed_number_in_the_translation_needs_review(tmp_path, ko_sample, source_samples):
    text = ko_sample.read_text(encoding="utf-8").replace("±1.0%", "±2.0%")
    result = _ingest(_write(tmp_path, "rag_ko.md", text), "vi", source_samples["vi"])
    assert result.status == "REVIEW_REQUIRED"
    assert _codes(result) == {"IMAGE_PRESENT": 6, "TOKEN_MISMATCH": 1}


def test_bom_and_crlf_are_read_normally(tmp_path, ko_sample):
    text = ko_sample.read_text(encoding="utf-8")
    windows = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
    result = _ingest(_write(tmp_path, "windows.md", windows))
    assert result.status == "OK"
    assert _ingest(ko_sample).documents[0].elements == result.documents[0].elements
    # the hash is taken over the bytes as they are on disk
    assert result.documents[0].sha256 == hashlib.sha256(windows).hexdigest()


# --- broken input ---------------------------------------------------------------------


def _assert_failed(result, reason, document):
    assert result.status == "FAILED"
    assert result.parser_version == PARSER_VERSION
    assert result.failure.reason == reason
    assert result.failure.document == document
    # a failed result carries nothing that could be mistaken for a parsed document
    assert result.documents == ()
    assert result.findings == ()
    assert result.translation_check is None


def test_a_missing_file_fails(tmp_path):
    _assert_failed(_ingest(tmp_path / "missing.md"), "FILE_UNREADABLE", "source")


def test_a_directory_fails(tmp_path):
    _assert_failed(_ingest(tmp_path), "FILE_UNREADABLE", "source")


@pytest.mark.parametrize("data", [b"", b"\n\n  \n", b"\xef\xbb\xbf"])
def test_an_empty_file_fails(tmp_path, data):
    _assert_failed(_ingest(_write(tmp_path, "empty.md", data)), "EMPTY_DOCUMENT", "source")


def test_a_file_that_is_not_utf8_fails(tmp_path):
    path = _write(tmp_path, "cp949.md", "[PAGE 1]\n문단이다.\n".encode("cp949"))
    _assert_failed(_ingest(path), "NOT_UTF8", "source")


def test_a_broken_main_file_of_a_translated_document(tmp_path, source_samples):
    result = _ingest(tmp_path / "missing.md", "en", source_samples["en"])
    _assert_failed(result, "FILE_UNREADABLE", "translated")


@pytest.mark.parametrize(
    "data, reason",
    [(None, "FILE_UNREADABLE"), (b"", "EMPTY_DOCUMENT"), ("문단".encode("cp949"), "NOT_UTF8")],
)
def test_a_broken_source_file_fails_the_whole_result(tmp_path, ko_sample, data, reason):
    source = tmp_path / "rag.md"
    if data is not None:
        source.write_bytes(data)
    # the Korean file is fine, but the result must not look like a normal one
    _assert_failed(_ingest(ko_sample, "vi", source), reason, "source")


def test_a_file_without_page_markers_needs_review(tmp_path):
    result = _ingest(_write(tmp_path, "no_page.md", "## 1 개요\n\n문단이다.\n"))
    assert result.status == "REVIEW_REQUIRED"
    assert _codes(result) == {"NO_PAGE_MARKER": 1}
    assert len(result.documents[0].elements) == 2  # the elements are still there to review


def test_a_table_row_with_a_wrong_number_of_cells_needs_review(tmp_path):
    text = "[PAGE 1]\n|구분|기준|\n|---|---|\n|온도|2~8℃|냉장|\n"
    result = _ingest(_write(tmp_path, "table.md", text))
    assert result.status == "REVIEW_REQUIRED"
    assert _codes(result) == {"TABLE_ROW_WIDTH_MISMATCH": 1}


def test_lines_that_fit_no_rule_need_review(tmp_path):
    text = "[PAGE 1]\n<div>문단</div>\n---\n[PAGE x]\n"
    result = _ingest(_write(tmp_path, "odd.md", text))
    assert result.status == "REVIEW_REQUIRED"
    assert _codes(result) == {"UNCLASSIFIED_LINE": 3}
    assert [element.kind for element in result.documents[0].elements[1:]] == ["unclassified"] * 3


@pytest.mark.parametrize(
    "data",
    [
        b"\x00\x01\x02\x03",
        b"|||||\n|-|\n|",
        b"[PAGE 1]\n" + b"#" * 5000 + b"\n",
        b"[PAGE 99999999999999999999]\n![](<>)\n- \n1)\n",
    ],
)
def test_broken_structure_never_escapes_as_an_exception_or_as_ok(tmp_path, data):
    result = _ingest(_write(tmp_path, "odd.md", data))
    assert result.status in ("FAILED", "REVIEW_REQUIRED")


# --- unexpected errors ----------------------------------------------------------------


def test_an_unexpected_error_fails_closed(monkeypatch, caplog, ko_sample):
    def explode(lines, variant):
        raise RuntimeError("비밀 문장: " + lines[6])

    monkeypatch.setattr(ingest_module, "parse_lines", explode)
    with caplog.at_level(logging.INFO):
        result = _ingest(ko_sample)
    _assert_failed(result, "INTERNAL_ERROR", None)
    assert "RuntimeError" in caplog.text
    assert "비밀 문장" not in caplog.text  # the message may quote the document


def test_a_lost_line_fails_closed(monkeypatch, ko_sample):
    real = ingest_module.parse_lines

    def drop_one(lines, variant):
        elements, findings = real(lines, variant)
        return elements[:-1], findings

    monkeypatch.setattr(ingest_module, "parse_lines", drop_one)
    _assert_failed(_ingest(ko_sample), "INTERNAL_ERROR", None)


def test_an_error_while_checking_the_translation_fails_closed(
    monkeypatch, ko_sample, source_samples
):
    def explode(translated, source):
        raise KeyError("e0001")

    monkeypatch.setattr(ingest_module, "check_translation", explode)
    _assert_failed(_ingest(ko_sample, "en", source_samples["en"]), "INTERNAL_ERROR", None)


# --- logs -----------------------------------------------------------------------------


def test_logs_report_counts_and_codes(caplog, ko_sample, source_samples):
    with caplog.at_level(logging.INFO):
        _ingest(ko_sample, "vi", source_samples["vi"])
    assert "read the translated file: 114 lines, 49 elements" in caplog.text
    assert "read the source file: 114 lines, 49 elements" in caplog.text
    assert "status: OK" in caplog.text
    assert "findings: IMAGE_PRESENT=6" in caplog.text


def test_logs_carry_no_document_text(caplog, tmp_path, ko_sample, source_samples):
    text = ko_sample.read_text(encoding="utf-8").replace("±1.0%", "±2.0%")
    with caplog.at_level(logging.DEBUG):
        result = _ingest(_write(tmp_path, "rag_ko.md", text), "vi", source_samples["vi"])
    assert result.status == "REVIEW_REQUIRED"
    assert "TOKEN_MISMATCH=1" in caplog.text
    for document in result.documents:
        for element in document.elements:
            if element.kind == "page_marker":
                continue
            for line in element.raw.split("\n"):
                assert line not in caplog.text
    for finding in result.findings:
        for token in (*finding.missing_tokens, *finding.extra_tokens):
            assert token not in caplog.text
            assert token.split(":", 1)[1] not in caplog.text


def test_a_read_failure_is_logged_by_its_reason_only(caplog, tmp_path):
    with caplog.at_level(logging.INFO):
        _ingest(_write(tmp_path, "cp949.md", "문단이다.".encode("cp949")))
    assert "cannot read the source file: NOT_UTF8" in caplog.text
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_ingest.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ImportError: cannot import name 'ingest' from 'app.parsing'
1 error
```

- [ ] **Step 3: 구현한다**

`app/parsing/ingest.py`:

```python
"""Whole flow: files -> documents -> findings -> status. Fails closed.

Expected input problems come back as a status, never as an exception. Anything
unexpected is caught at the outermost level and turned into FAILED, so a partly
processed document is never returned as if it were a normal result.

Logs carry codes, element IDs, line numbers and counts only: no document text.
"""

from __future__ import annotations

import logging
import traceback
from collections import Counter
from pathlib import Path
from typing import Optional, Union

from app.models.document import Document, Language, Variant
from app.models.findings import Failure, Finding, IngestResult, new_finding
from app.parsing.line_parser import parse_lines, verify_line_coverage
from app.parsing.quality import decide_status
from app.parsing.reader import read_lines
from app.parsing.translation_check import check_translation

# Raise this whenever a parsing rule or a token rule changes.
PARSER_VERSION = "0.1.0"

logger = logging.getLogger(__name__)


def _load(
    path: Path, *, doc_id: str, version: str, variant: Variant, language: Language
) -> Union[Failure, tuple[Document, tuple[Finding, ...]]]:
    read = read_lines(path)
    if read.error is not None or read.sha256 is None:
        logger.error("cannot read the %s file: %s", variant, read.error)
        return Failure(reason=read.error or "FILE_UNREADABLE", document=variant)
    elements, findings = parse_lines(read.lines, variant)
    verify_line_coverage(read.lines, elements)
    document = Document(
        doc_id=doc_id,
        version=version,
        variant=variant,
        language=language,
        file_name=read.file_name,
        sha256=read.sha256,
        elements=elements,
    )
    logger.info("read the %s file: %d lines, %d elements", variant, len(read.lines), len(elements))
    return document, findings


def _failed(failure: Failure) -> IngestResult:
    return IngestResult(status="FAILED", parser_version=PARSER_VERSION, failure=failure)


def _ingest(
    main_path: Path,
    *,
    doc_id: str,
    version: str,
    original_language: Language,
    source_path: Optional[Path],
) -> IngestResult:
    # A Korean baseline document was never translated, so it is its own source.
    main_variant: Variant = "source" if original_language == "ko" else "translated"
    main = _load(main_path, doc_id=doc_id, version=version, variant=main_variant, language="ko")
    if isinstance(main, Failure):
        return _failed(main)
    documents = [main[0]]
    findings = list(main[1])
    translation_check = None

    if original_language != "ko":
        if source_path is None:
            findings.append(new_finding("SOURCE_NOT_PROVIDED", "translated"))
        else:
            source = _load(
                source_path,
                doc_id=doc_id,
                version=version,
                variant="source",
                language=original_language,
            )
            if isinstance(source, Failure):
                return _failed(source)
            documents.append(source[0])
            findings.extend(source[1])
            translation_check, check_findings = check_translation(main[0], source[0])
            findings.extend(check_findings)

    status = decide_status(findings)
    counts = Counter(finding.code for finding in findings)
    logger.info("status: %s", status)
    logger.info(
        "findings: %s",
        ", ".join(f"{code}={count}" for code, count in sorted(counts.items())) or "none",
    )
    return IngestResult(
        status=status,
        parser_version=PARSER_VERSION,
        documents=tuple(documents),
        findings=tuple(findings),
        translation_check=translation_check,
    )


def ingest(
    main_path: Path,
    *,
    doc_id: str,
    version: str,
    original_language: Language,
    source_path: Optional[Path] = None,
) -> IngestResult:
    """Read one document (and its source, for a translated one) and check it."""
    if original_language == "ko" and source_path is not None:
        raise ValueError("a Korean baseline document takes no source file")
    try:
        return _ingest(
            main_path,
            doc_id=doc_id,
            version=version,
            original_language=original_language,
            source_path=source_path,
        )
    except Exception as error:  # fail closed: nothing may escape as a result
        frames = traceback.extract_tb(error.__traceback__)
        where = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else "unknown"
        # The message of the exception may quote document text, so only its type is logged.
        logger.error("internal error: %s at %s", type(error).__name__, where)
        return _failed(Failure(reason="INTERNAL_ERROR"))
```

`except Exception`을 여기 한 곳에만 둔다. 다른 모듈에서 예외를 삼키지 않는다. 잡은 예외는 메시지가 아니라 종류와 코드 위치만 로그에 쓴다. 메시지가 문서 본문을 인용할 수 있기 때문이다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_ingest.py -q`

Expected: 마지막 줄이 `33 passed`

- [ ] **Step 5: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `350 passed`, `All checks passed!`, `29 files already formatted`

- [ ] **Step 6: 커밋한다**

```bash
git add tests/parsing/test_ingest.py app/parsing/ingest.py
git commit -m "feat: add the fail-closed ingest flow" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 18: 명령줄

설계 §8. `python -m app.parsing`으로 실행하고 결과를 JSON 파일로 쓴다. 종료 코드는 `OK` 0, `REVIEW_REQUIRED` 1, `FAILED`와 사용법 오류 2다.

**Files:**
- Create: `app/parsing/__main__.py`
- Test: `tests/parsing/test_cli.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/parsing/test_cli.py`:

```python
"""Command line: python -m app.parsing (spec section 8)."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from app.models.findings import IngestResult
from app.parsing.__main__ import main
from app.parsing.ingest import ingest

ROOT = Path(__file__).resolve().parents[2]


def _args(main_file, out, language="ko", source=None):
    args = [
        str(main_file),
        "--doc-id",
        "SOP-SAMPLE",
        "--version",
        "1",
        "--original-language",
        language,
        "--out",
        str(out),
    ]
    if source is not None:
        args += ["--source", str(source)]
    return args


def _read(out):
    return IngestResult.model_validate_json(out.read_text(encoding="utf-8"))


def test_ok_exits_with_0(tmp_path, ko_sample):
    out = tmp_path / "result.json"
    assert main(_args(ko_sample, out)) == 0
    assert _read(out).status == "OK"


@pytest.mark.parametrize("language", ["en", "vi", "zh"])
def test_a_translated_document_with_its_source_exits_with_0(
    tmp_path, ko_sample, source_samples, language
):
    out = tmp_path / "result.json"
    assert main(_args(ko_sample, out, language, source_samples[language])) == 0
    result = _read(out)
    assert result.status == "OK"
    assert [document.language for document in result.documents] == ["ko", language]
    assert len(result.translation_check.pairs) == 120


def test_review_required_exits_with_1(tmp_path, ko_sample):
    out = tmp_path / "result.json"
    assert main(_args(ko_sample, out, "vi")) == 1  # a translation without its source
    result = _read(out)
    assert result.status == "REVIEW_REQUIRED"
    assert "SOURCE_NOT_PROVIDED" in [finding.code for finding in result.findings]


def test_failed_exits_with_2_and_still_writes_the_result(tmp_path):
    out = tmp_path / "result.json"
    assert main(_args(tmp_path / "missing.md", out)) == 2
    result = _read(out)
    assert result.status == "FAILED"
    assert result.failure.reason == "FILE_UNREADABLE"
    assert result.documents == ()


def test_the_result_file_reads_back_as_the_same_result(tmp_path, ko_sample, source_samples):
    out = tmp_path / "result.json"
    main(_args(ko_sample, out, "zh", source_samples["zh"]))
    expected = ingest(
        ko_sample,
        doc_id="SOP-SAMPLE",
        version="1",
        original_language="zh",
        source_path=source_samples["zh"],
    )
    assert _read(out) == expected


def test_the_result_file_is_utf8_with_lf(tmp_path, ko_sample):
    out = tmp_path / "result.json"
    main(_args(ko_sample, out))
    data = out.read_bytes()
    assert b"\r\n" not in data
    assert "합께".encode("utf-8") in data  # Korean is written as it is, not as \u escapes


def test_the_output_directory_is_created(tmp_path, ko_sample):
    out = tmp_path / "out" / "sample" / "result.json"
    assert main(_args(ko_sample, out)) == 0
    assert out.is_file()


def test_a_result_file_that_cannot_be_written_exits_with_2(tmp_path, ko_sample):
    assert main(_args(ko_sample, tmp_path)) == 2  # --out is a directory


def test_source_with_a_korean_original_is_a_usage_error(tmp_path, ko_sample, source_samples):
    out = tmp_path / "result.json"
    with pytest.raises(SystemExit) as exit_info:
        main(_args(ko_sample, out, "ko", source_samples["en"]))
    assert exit_info.value.code == 2
    assert not out.exists()


@pytest.mark.parametrize(
    "drop",
    ["--doc-id", "--version", "--original-language", "--out"],
)
def test_a_missing_option_is_a_usage_error(tmp_path, ko_sample, drop):
    args = _args(ko_sample, tmp_path / "result.json")
    index = args.index(drop)
    del args[index : index + 2]
    with pytest.raises(SystemExit) as exit_info:
        main(args)
    assert exit_info.value.code == 2


def test_an_unknown_language_is_a_usage_error(tmp_path, ko_sample):
    with pytest.raises(SystemExit) as exit_info:
        main(_args(ko_sample, tmp_path / "result.json", "ja"))
    assert exit_info.value.code == 2


def test_logs_carry_no_document_text(tmp_path, caplog, ko_sample, source_samples):
    out = tmp_path / "result.json"
    with caplog.at_level(logging.INFO):
        main(_args(ko_sample, out, "en", source_samples["en"]))
    assert "status: OK" in caplog.text
    for path in (ko_sample, source_samples["en"]):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("[PAGE"):
                assert line not in caplog.text


def test_run_as_a_module(tmp_path, ko_sample, source_samples):
    out = tmp_path / "result.json"
    command = [sys.executable, "-m", "app.parsing", *_args(ko_sample, out, "vi")]
    done = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
    assert done.returncode == 1
    assert done.stdout == b""  # the result goes to the file, the log to stderr
    log = done.stderr.decode("ascii")  # codes and counts only: no Korean text can be in it
    assert "status: REVIEW_REQUIRED" in log
    assert "SOURCE_NOT_PROVIDED=1" in log
    assert _read(out).status == "REVIEW_REQUIRED"

    command = [sys.executable, "-m", "app.parsing", *_args(ko_sample, out, "ko")]
    command += ["--source", str(source_samples["en"])]
    done = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
    assert done.returncode == 2
    assert b"--source cannot be used" in done.stderr
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_cli.py -q`

Expected: 실패한다. 출력에 아래 줄이 있다.

```text
E   ModuleNotFoundError: No module named 'app.parsing.__main__'
1 error
```

- [ ] **Step 3: 구현한다**

`app/parsing/__main__.py`:

```python
"""Command line: python -m app.parsing <main file> --doc-id ... --out result.json

Exit codes: 0 = OK, 1 = REVIEW_REQUIRED, 2 = FAILED or a usage error.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

from app.parsing.ingest import ingest

EXIT_CODES = {"OK": 0, "REVIEW_REQUIRED": 1, "FAILED": 2}

logger = logging.getLogger("app.parsing")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.parsing",
        description="Read rag_ko.md (and rag.md) into elements and check the result.",
    )
    parser.add_argument("main_file", type=Path, help="rag_ko.md, or a Korean baseline document")
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--original-language", required=True, choices=["ko", "vi", "en", "zh"])
    parser.add_argument("--source", type=Path, default=None, help="rag.md before translation")
    parser.add_argument("--out", type=Path, required=True, help="result JSON (keep under out/)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.original_language == "ko" and args.source is not None:
        parser.error("--source cannot be used with --original-language ko")  # exits with 2

    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s"
    )
    result = ingest(
        args.main_file,
        doc_id=args.doc_id,
        version=args.version,
        original_language=args.original_language,
        source_path=args.source,
    )
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        # written as bytes so the file is UTF-8 with LF line ends on every platform
        args.out.write_bytes(result.model_dump_json(indent=2).encode("utf-8"))
    except OSError as error:
        logger.error("cannot write the result file: %s", type(error).__name__)
        return 2
    return EXIT_CODES[result.status]


if __name__ == "__main__":
    sys.exit(main())
```

결과 파일은 바이트로 쓴다. 텍스트 모드로 쓰면 Windows에서 줄 끝이 CRLF로 바뀐다. `FAILED`일 때도 결과 파일을 쓴다. 실패 사유가 그 안에 있기 때문이다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `.venv/Scripts/python -m pytest tests/parsing/test_cli.py -q`

Expected: 마지막 줄이 `18 passed`

- [ ] **Step 5: 한국어 기준 문서로 실행해 본다**

Run: `.venv/Scripts/python -m app.parsing tests/fixtures/rag_ko/sample_bakery_sop.md --doc-id SOP-SAMPLE --version 1 --original-language ko --out out/sample_ko.json`

Expected: 종료 코드 0, 출력은 아래와 같다.

```text
INFO app.parsing.ingest: read the source file: 114 lines, 49 elements
INFO app.parsing.ingest: status: OK
INFO app.parsing.ingest: findings: IMAGE_PRESENT=3
```

- [ ] **Step 6: 번역본과 원문으로 실행해 본다**

Run: `.venv/Scripts/python -m app.parsing tests/fixtures/rag_ko/sample_bakery_sop.md --doc-id SOP-SAMPLE --version 1 --original-language vi --source tests/fixtures/rag/sample_bakery_sop.vi.md --out out/sample_vi.json`

Expected: 종료 코드 0, 출력은 아래와 같다.

```text
INFO app.parsing.ingest: read the translated file: 114 lines, 49 elements
INFO app.parsing.ingest: read the source file: 114 lines, 49 elements
INFO app.parsing.ingest: status: OK
INFO app.parsing.ingest: findings: IMAGE_PRESENT=6
```

- [ ] **Step 7: 원문 없이 실행해 본다**

Run: `.venv/Scripts/python -m app.parsing tests/fixtures/rag_ko/sample_bakery_sop.md --doc-id SOP-SAMPLE --version 1 --original-language vi --out out/sample_vi_only.json`

Expected: 종료 코드 1, 출력은 아래와 같다.

```text
INFO app.parsing.ingest: read the translated file: 114 lines, 49 elements
INFO app.parsing.ingest: status: REVIEW_REQUIRED
INFO app.parsing.ingest: findings: IMAGE_PRESENT=3, SOURCE_NOT_PROVIDED=1
```

- [ ] **Step 8: 사용법 오류를 확인한다**

Run: `.venv/Scripts/python -m app.parsing tests/fixtures/rag_ko/sample_bakery_sop.md --doc-id SOP-SAMPLE --version 1 --original-language ko --source tests/fixtures/rag/sample_bakery_sop.vi.md --out out/never.json`

Expected: 종료 코드 2, 출력은 아래와 같다.

```text
usage: python -m app.parsing [-h] --doc-id DOC_ID --version VERSION
                             --original-language {ko,vi,en,zh}
                             [--source SOURCE] --out OUT
                             main_file
python -m app.parsing: error: --source cannot be used with --original-language ko
```

- [ ] **Step 9: 결과 파일이 커밋 대상이 아닌지 확인한다**

Run: `git status --porcelain`

Expected: 종료 코드 0, 출력은 아래와 같다.

```text
?? app/parsing/__main__.py
?? tests/parsing/test_cli.py
```

`out/`이 `.gitignore`에 있으므로 `out/` 아래 파일은 나오지 않는다. 아직 커밋하지 않은 이 Task의 두 파일만 나온다.

- [ ] **Step 10: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `368 passed`, `All checks passed!`, `31 files already formatted`

- [ ] **Step 11: 커밋한다**

```bash
git add tests/parsing/test_cli.py app/parsing/__main__.py
git commit -m "feat: add the command line for the adapter" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

---

### Task 19: 문서 마무리

구현이 끝났으므로 `CLAUDE.md`의 "현재 상태"를 고치고 명령어를 적는다. 사내에서 실제 파일로 확인하는 절차를 문서로 남긴다(설계 §10의 "사내 확인").

**Files:**
- Create: `docs/INHOUSE_CHECK.md`
- Modify: `CLAUDE.md` ("현재 상태"의 첫 문단, "보안" 절 앞에 "명령어" 절 추가)

- [ ] **Step 1: `docs/INHOUSE_CHECK.md`를 만든다**

````markdown
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

종료 코드는 `OK` 0, `REVIEW_REQUIRED` 1, `FAILED` 2다. 결과 JSON은 `out/` 아래에 두고 사내에서만 연다.

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
````

- [ ] **Step 2: `CLAUDE.md`의 "현재 상태" 첫 문단을 바꾼다**

바꿀 부분:

```markdown
설계 단계 저장소다. 아직 코드, 의존성 파일, 빌드·린트·테스트 명령이 없다. 전체 설계는 [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md)에 있으며, 구현을 시작할 때는 이 문서의 §11(권장 파일 구성)과 §9(PoC 단계)를 따른다. 명령어가 생기면 이 파일에 추가한다.
```

바꾼 뒤:

```markdown
단위 ①(기반 + `rag_ko.md` 어댑터)이 구현되어 있다. `rag_ko.md`와 `rag.md`를 요소 목록으로 읽고, 번역본 점검과 품질 점검을 한다. 단위 ②~⑥(LLM 게이트웨이, 체크리스트 추출, 판정, UI, 서식 검사)은 아직 없다. 전체 설계는 [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md)에 있으며, 다음 단위를 구현할 때는 이 문서의 §11(권장 파일 구성)과 §9(PoC 단계)를 따른다.
```

- [ ] **Step 3: `CLAUDE.md`의 `## 보안 (공개 저장소)` 바로 앞에 "명령어" 절을 넣는다**

아래 내용을 넣고, 뒤에 빈 줄 하나를 둔 다음 `## 보안 (공개 저장소)`가 이어지게 한다.

````markdown
## 명령어

Git Bash 기준이다. PowerShell에서는 `.venv\Scripts\python`, Linux와 macOS에서는 `.venv/bin/python`을 쓴다.

```bash
# 설치
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]" -c constraints.txt

# 테스트: 전체, 파일 하나, 테스트 하나
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m pytest tests/parsing/test_tokens.py -q
.venv/Scripts/python -m pytest tests/parsing/test_tokens.py::test_units -q

# 린트와 포맷
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format .

# 문서 한 건 읽기(번역본 + 원문). 한국어 기준 문서는 --original-language ko, --source 없이.
.venv/Scripts/python -m app.parsing tests/fixtures/rag_ko/sample_bakery_sop.md --doc-id SOP-SAMPLE --version 1 --original-language vi --source tests/fixtures/rag/sample_bakery_sop.vi.md --out out/sample.json
```

- 명령줄 종료 코드는 `OK` 0, `REVIEW_REQUIRED` 1, `FAILED`와 사용법 오류 2다.
- 결과 JSON에는 문서 본문이 들어간다. `out/` 아래에만 쓰고 커밋하지 않는다.
- 파싱 규칙이나 토큰 규칙을 바꾸면 `app/parsing/ingest.py`의 `PARSER_VERSION`을 올린다.
- `tests/fixtures/`의 샘플과 테스트의 기준값은 고치지 않는다. 테스트가 실패하면 코드를 고친다.
- 사내 실행 환경은 Python 3.10.11이다(D-003). 3.10 뒤에 생긴 문법과 표준 라이브러리 기능을 쓰지 않는다. ruff의 `target-version = "py310"`이 일부를 잡아 준다.
- 의존성 버전은 `constraints.txt`에 고정한다. 버전을 올릴 때는 Python 3.10 지원과 라이선스를 다시 확인한다(D-009).
- 사내에서 실제 파일로 확인하는 절차는 [docs/INHOUSE_CHECK.md](docs/INHOUSE_CHECK.md)에 있다.
````

- [ ] **Step 4: 전체 검사를 돌린다**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Expected: 차례로 `368 passed`, `All checks passed!`, `31 files already formatted`

- [ ] **Step 5: 설계의 완료 기준을 하나씩 확인한다**

| 완료 기준(설계 §2) | 확인하는 테스트 |
|---|---|
| 1. 샘플이 요소 49개로 읽힌다 | `tests/parsing/test_sample_golden.py` |
| 2. 모든 요소가 페이지, 절 경로, 줄 번호를 갖는다 | `tests/parsing/test_sample_golden.py`, `tests/parsing/test_parser_tables.py` |
| 3. 빈 줄이 아닌 모든 줄이 한 요소에 속한다 | `tests/parsing/test_line_coverage.py` |
| 4. 오탈자가 그대로 남는다 | `tests/parsing/test_sample_golden.py`, `tests/parsing/test_parser_basics.py` |
| 5. 번역본을 바꾸면 그 요소를 짚는다 | `tests/parsing/test_translation_mutations.py` |
| 6. 깨진 입력에서 죽지도, 통과시키지도 않는다 | `tests/parsing/test_ingest.py`, `tests/parsing/test_cli.py` |

Run: `.venv/Scripts/python -m pytest tests/parsing/test_sample_golden.py tests/parsing/test_line_coverage.py tests/parsing/test_translation_mutations.py tests/parsing/test_ingest.py tests/parsing/test_cli.py -q`

Expected: 마지막 줄이 `93 passed`

- [ ] **Step 6: 커밋한다**

```bash
git add docs/INHOUSE_CHECK.md CLAUDE.md
git commit -m "docs: describe commands and the in-house check for unit 1" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin main
```

- [ ] **Step 7: 사용자에게 알린다**

구현이 끝났다고 알리면서 아래를 함께 전한다.

- Python 3.10.11에서의 실행과 실제 파일 확인은 사내에서 `docs/INHOUSE_CHECK.md`대로 해야 한다.
- 설계 §11의 미결 항목은 그대로 남아 있다.
- 다음은 단위 ②(LLM 게이트웨이)의 설계다.
