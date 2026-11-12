# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 현재 상태

단위 ①(기반 + `rag_ko.md` 어댑터)과 단위 ②(LLM 게이트웨이)가 구현되어 있다. 단위 ①은 `rag_ko.md`와 `rag.md`를 요소 목록으로 읽고, 번역본 점검과 품질 점검을 한다. 단위 ②는 사내 OpenAI 호환 LLM을 호출하는 통로이며, 실제 사내 연동은 아직 확인하지 않았다. 단위 ③~⑥(체크리스트 추출, 판정, UI, 서식 검사)은 아직 없다. 전체 설계는 [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md)에 있으며, 다음 단위를 구현할 때는 이 문서의 §11(권장 파일 구성)과 §9(PoC 단계)를 따른다.

목표: DOCX/PDF 문서의 양식·필수 항목 검증(Use Case A)과 한국 기준 SOP ↔ 일본 SOP 비교(Use Case B).

단위별 설계(D-001의 6개 단위)는 `docs/superpowers/specs/`에 있다. 단위 ①은 [2026-11-11-foundation-rag-adapter-design.md](docs/superpowers/specs/2026-11-11-foundation-rag-adapter-design.md), 단위 ②는 [2026-11-12-llm-gateway-design.md](docs/superpowers/specs/2026-11-12-llm-gateway-design.md)다. 단위별 구현 계획은 `docs/superpowers/plans/`에 있다. 단위 ①은 [2026-11-11-foundation-rag-adapter.md](docs/superpowers/plans/2026-11-11-foundation-rag-adapter.md), 단위 ②는 [2026-11-12-llm-gateway.md](docs/superpowers/plans/2026-11-12-llm-gateway.md)다.

설계 문서 이후 확정된 결정은 [docs/DECISIONS.md](docs/DECISIONS.md)에 있으며, 설계 문서와 다르면 그쪽이 우선한다. 새 결정이 나오면 거기에 추가한다.

설계 문서는 검증 전 초안(v0.1)이다. 스택과 오픈소스 후보(§5)는 아직 실험하지 않았고, §12에 미결 의사결정이 남아 있다(기준의 우선순위, N/A 인정 조건과 승인자, MISSING 확정을 위한 재검토 범위 등). 구현 중 이런 정책이 필요해지면 임의로 정하지 말고 사용자에게 묻는다.

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

# 사내 LLM 연결 확인(사내에서만 의미가 있다). 종료 코드는 두 호출이 모두 OK이면 0, 아니면 2.
.venv/Scripts/python -m app.llm check --env-file .env
```

- 명령줄 종료 코드는 `OK` 0, `REVIEW_REQUIRED` 1, `FAILED`와 사용법 오류 2다. 결과 파일을 쓰지 못했거나 예상하지 못한 오류가 나도 2다. 0과 1은 결과 파일을 쓴 뒤에만 나온다.
- 결과 JSON에는 문서 본문이 들어간다. `out/` 아래에만 쓰고 커밋하지 않는다.
- 파싱 규칙이나 토큰 규칙을 바꾸면 `app/parsing/ingest.py`의 `PARSER_VERSION`을 올린다.
- 게이트웨이의 규칙(지시 메시지, 재시도, 실패 분류)을 바꾸면 `app/llm/base.py`의 `GATEWAY_VERSION`을 올린다.
- `tests/fixtures/`의 샘플과 테스트의 기준값은 고치지 않는다. 테스트가 실패하면 코드를 고친다.
- 사내 실행 환경은 Python 3.10.11이다(D-003). 3.10 뒤에 생긴 문법과 표준 라이브러리 기능을 쓰지 않는다. ruff의 `target-version = "py310"`이 일부를 잡아 준다.
- 의존성 버전은 `constraints.txt`에 고정한다. 버전을 올릴 때는 Python 3.10 지원과 라이선스를 다시 확인한다(D-009).
- 사내에서 LLM 연결을 확인하는 절차는 [docs/INHOUSE_LLM_CHECK.md](docs/INHOUSE_LLM_CHECK.md)에 있다.
- 사내에서 실제 파일로 확인하는 절차는 [docs/INHOUSE_CHECK.md](docs/INHOUSE_CHECK.md)에, 저장소를 받은 뒤의 전체 순서는 [docs/INHOUSE_GUIDE.md](docs/INHOUSE_GUIDE.md)에 있다.

## 보안 (공개 저장소)

이 저장소는 Public이다. 사내 문서·SOP 원문, 사내 API 주소, credential ticket, 사용자 ID, 승인번호를 코드·커밋·로그·테스트 픽스처·보고서에 넣지 않는다. 테스트 데이터는 공개/가상 데이터만 `tests/fixtures/`에 둔다. 비밀값은 환경변수로만 읽고 `config/example.env`에는 자리표시자만 둔다.

로그에는 발견 항목 코드, 요소 ID, 줄 번호, 개수만 남긴다. 예외는 타입만 기록하고 메시지는 남기지 않는다(메시지에 경로나 문서 본문이 들어갈 수 있다).

## 현재 코드 구조 (단위 ①)

흐름은 `app/parsing/ingest.py`의 `ingest()` 하나다. `reader.read_lines`(UTF-8, BOM 무시, sha256) → `line_parser.parse_lines`(줄 → 평평한 요소 목록 + 발견 항목) → `verify_line_coverage`(모든 줄이 어떤 요소에 들어갔는지 확인) → `Document` 순으로 진행된다. 번역본이면 원문(`rag.md`)도 같은 방식으로 읽은 뒤 `translation_check.check_translation`이 두 문서의 요소를 1:1로 짝짓고(D-008) 숫자·단위·코드 토큰을 비교한다(`tokens.py`). 마지막으로 `quality.decide_status`가 상태를 정한다.

- 한국어 기준 문서(`original_language="ko"`)는 원문 없이 읽으며, 자기 자신이 `variant="source"`다. 번역본은 `"translated"`, 원문은 `"source"`다.
- 입력 문제(읽기 실패, UTF-8 아님, 빈 문서)는 예외가 아니라 `Failure` → `FAILED`로 돌려준다. 그 밖의 예외는 바깥에서 잡아 `INTERNAL_ERROR`로 바꾼다. 호출자 실수(잘못된 언어, 한국어 문서에 원문 지정)만 `ValueError`로 올린다.
- 발견 항목(`Finding`)은 `Document` 안에 넣지 않고 `element_id`로 요소를 가리킨다. 등급은 코드가 정한다(`findings.py`의 `INFO_CODES`, D-013). 새 코드를 만들면 `FindingCode` Literal에 추가하고, 문서 전체를 막는 코드라면 `DOCUMENT_SCOPE_CODES`에도 넣는다.
- 상태는 비율로 정하지 않는다. "검토 필요" 항목이 하나라도 있으면 `REVIEW_REQUIRED`다. 이후 판정 단계는 `quality.blocked_element_ids`로 받은 요소를 PASS 근거로 쓰지 않는다.
- 모델은 모두 `FrozenModel`(Pydantic, `frozen=True`, `extra="forbid"`)이고, 위치 정보는 `Locator`(페이지, 절 경로, 줄 범위)에 담는다. 명령줄 결과 JSON은 `findings.IngestResult`를 그대로 덤프한 것이다. 입력 `rag_ko.md`의 형식은 [docs/RAG_KO_FORMAT.md](docs/RAG_KO_FORMAT.md)에 있다. [docs/PARSER_OUTPUT.md](docs/PARSER_OUTPUT.md)는 상류 파서 JSON에 대한 참고 문서이며, 이 저장소는 그 JSON을 읽지 않는다.

## 현재 코드 구조 (단위 ②)

LLM을 부르는 코드는 `app/llm/`의 게이트웨이만 쓴다. `openai` SDK는 `app/llm/gateway.py` 안에서만 가져온다(D-015).

```python
gateway = LLMGateway.from_env()
result = gateway.complete(messages, prompt_id="...", prompt_version="1")
result = gateway.complete_structured(messages, Schema, prompt_id="...", prompt_version="1")
```

- 공통 흐름은 `base.py`의 `BaseLLM`에 있다. 하위 클래스는 요청 한 번을 보내는 `_request`만 구현한다. `gateway.py`의 `LLMGateway`(SDK 호출)와 `fake.py`의 `FakeLLM`(정해 둔 응답)이 그 둘이다. LLM에 의존하는 코드의 테스트는 `FakeLLM`을 쓴다(D-002).
- 호출은 예외를 올리지 않고 `TextResult` 또는 `StructuredResult`를 돌려준다(D-016). `status`가 `FAILED`이면 응답 내용이 없고 `failure`에 사유 코드가 있다. 호출자는 `FAILED`를 UNKNOWN으로 이어야 한다. 호출자 실수(메시지 없음, 빈 프롬프트 ID)만 `ValueError`로 올린다.
- 설정이 없거나 틀려도 게이트웨이는 만들어지고, 모든 호출이 `CONFIG_MISSING`이나 `CONFIG_INVALID`로 실패한다. 기본 주소는 없다.
- 재시도는 게이트웨이가 직접 한다(SDK의 재시도는 끈다). 시도마다 `Prompt-Msg-Id`와 `Completion-Msg-Id`가 새 UUID여야 하기 때문이다.
- 구조화 호출은 `structured.py`가 지시 메시지를 붙이고 응답을 JSON으로 읽어 스키마로 엄격하게 검증한다. 스키마 통과는 형식만 보증한다.
- 결과의 `record`(`CallRecord`)에 모델, 프롬프트 ID와 버전, 게이트웨이 버전, 시도별 UUID가 들어 있다. 판정을 저장할 때 함께 저장한다.
- `gateway.py`는 `httpx2`, `httpcore2`, `openai` 로거를 끈다. 이 로거들은 요청 주소와 본문을 남긴다. 다시 켜지 않는다.
- 테스트는 `tests/llm/conftest.py`의 `make_gateway`로 SDK에 `httpx2.MockTransport`를 끼워 네트워크 없이 실제 SDK 경로를 지난다.

## 아키텍처 (계획)

파이프라인: Document Intelligence(파싱) → Structured Document Model + Provenance → Requirement Builder → Coverage Auditor → 사람 승인 → Requirement Registry → Compliance Validator(근거 검색 + Rule Engine + LLM Semantic Judge + Evidence Recheck) → 5상태 판정 → 보고서. Format Validator는 내용 검증과 별도 경로로 구조화 모델을 받아 보고서로 간다. "형식 불합격"과 "내용 불충분"은 서로 다른 결과로 관리한다.

Compliance Validator의 단계 순서(§3.4): Applicability 확인 → 근거 후보 탐색 → 한·일 용어 정렬 → Rule 검증 → LLM 의미 검증 → 불일치·누락 의심 시 재검색 → 판정·사유·권고 작성 → Critical/UNKNOWN 사람 검토.

계획된 모듈(`app/` 하위): `parsing/`, `requirements/`, `validation/`, `llm/`, `models/`(Pydantic), `reporting/`, `storage/`, `api/`(FastAPI), `ui/`(Streamlit). 파싱 / 요구사항 생성 / 검증 / UI / LLM 게이트웨이는 서로 독립 모듈로 유지한다.

PoC v0.1 스택: Python 3.10, 입력은 외부 변환 파이프라인이 만든 `rag_ko.md`(원본 → 파서 JSON → LLM 재구성 Markdown → 한국어 번역. 형식은 [docs/RAG_KO_FORMAT.md](docs/RAG_KO_FORMAT.md)). 이 저장소에는 그 파일을 구조화 모델로 읽는 어댑터만 두고 파서는 만들지 않는다. 사내 OpenAI 호환 LLM(OpenAI SDK 또는 LangChain ChatOpenAI), Python 함수형 파이프라인(LangGraph는 이후), Streamlit, FastAPI. Vector DB와 자율 Multi-Agent는 PoC에서 도입하지 않는다. 근거 검색은 초기에 직접 대조로 하고, 문서 1쌍으로 파싱·추출·매핑·판정을 검증한 뒤 RAG를 도입한다.

평가는 `tests/evaluation/`(아직 없음)의 판정 골든셋과 §10의 KPI로 한다. 단일 '정확도'로 판단하지 않으며, Critical 항목의 False Pass(실제 FAIL/MISSING을 PASS로 처리)를 가장 보수적으로 본다.

## 반드시 지킬 설계 불변조건

- **Fail closed:** 파싱 실패, LLM/API/네트워크 예외, 출처 누락, 저품질 파싱은 절대 PASS가 아니다. UNKNOWN + 사람 검토로 처리한다. 예외를 COMPLIANT/PASS로 떨어뜨리는 외부 코드 패턴(예: ARCCS)은 가져오지 않는다.
- **판정 상태는 5개:** PASS / FAIL / MISSING / UNKNOWN / N/A. 검색 결과가 없다는 이유만으로 MISSING을 확정하지 않는다(문서 범위 재검토 필요). N/A는 사전 승인된 예외 사유가 있어야 한다.
- **적용성 먼저:** 충족 여부를 판정하기 전에 공정·설비·국가·버전·조건부 예외로 Applicability를 평가한다.
- **문서 최종 통과 조건:** 승인된 기준 전체 검사 완료, Critical FAIL 없음, UNKNOWN 없음, 미승인 예외 없음, Parsing Quality Gate 통과. 하나라도 빠지면 합격이 아니다.
- **Provenance 유지:** 모든 요소와 근거는 문서 ID/버전/페이지/절/표 셀/bbox를 갖는다. REQUIREMENT → EVIDENCE → VERDICT → REVIEWER → REPORT 연결을 끊지 않는다.
- **Coverage Audit:** 원본의 모든 요소(`source_element_id`)는 REQUIREMENT_CREATED / NON_NORMATIVE / DUPLICATE_LINKED / REVIEW_REQUIRED / PARSING_FAILED 중 하나로 분류된다. 중요한 요소가 매핑되지 않으면 기준을 승인할 수 없다. LLM 재검토와 요소 단위 기계적 검사를 함께 쓴다.
- **결정적 검사 우선:** 숫자·단위·범위·부등호·필수 메타데이터·순서는 LLM이 아닌 코드(Pydantic 등)로 검사한다. LLM 응답이 JSON이어도 스키마 검증과 근거 대조를 별도로 한다.
- **기준은 사람 승인 후 버전 고정:** AI가 만든 Requirement는 승인 전에는 공식 기준이 아니다. 기준 버전이 바뀌면 이전 판정과 새 판정을 따로 보관한다. 검증 실행마다 기준 버전과 모델·프롬프트 버전을 기록한다.
- **폐쇄망:** 내부망에서 동작해야 한다. LLM 호출은 사내 게이트웨이로만 보내고, 외부 서비스 호출을 코드에 넣지 않는다.
- **권고는 작업 지시가 아니다:** LLM이 제안한 공정 조건 변경은 수정 권고로만 출력하고, 기술 담당자 검토 없이 확정된 지시처럼 다루지 않는다.
- 원문 인용과 번역/해석은 분리 저장한다. 한·일 비교는 번역 일치가 아니라 기술적 의미로 판단한다.
- DOCX 서식(폰트·크기·여백·스타일)은 파서 출력(구조·텍스트)만으로 보증하지 않는다. OOXML 스타일이나 렌더링 결과를 따로 검사한다.

## 외부 코드 재사용

SYSTEM_DESIGN.md §5의 저장소들은 검토 후보일 뿐 도입이 확정된 의존성이 아니다. ARCCS는 라이선스가 확인되기 전에는 코드를 복사하지 않고 설계 참고로만 쓴다. 다른 후보도 가져오기 전에 라이선스와 하위 의존성을 다시 확인한다.

## 사내 LLM 연동

OpenAI 호환 API를 쓰는 공통 adapter는 `app/llm/`에 구현되어 있다. 설정은 환경변수 `DS_API_BASE_URL`, `DS_CREDENTIAL`, `DS_SYSTEM_NAME`, `DS_USER_ID`, `DS_LLM_MODEL`, `DS_OPENAI_API_KEY`에서 읽는다. 헤더 `x-dep-ticket`, `Send-System-Name`, `User-Id`, `User-Type`(값 `AD_ID`)을 붙이고, `Prompt-Msg-Id`와 `Completion-Msg-Id`는 **호출마다 새 UUID**를 발급한다. `DS_OPENAI_API_KEY`는 선택이고, 시간 제한은 `DS_LLM_TIMEOUT_SECONDS`(선택, 기본 60초)로 바꾼다. 처음의 골격 코드는 SYSTEM_DESIGN.md §6에 있다.
