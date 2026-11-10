# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 현재 상태

설계 단계 저장소다. 아직 코드, 의존성 파일, 빌드·린트·테스트 명령이 없다. 전체 설계는 [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md)에 있으며, 구현을 시작할 때는 이 문서의 §11(권장 파일 구성)과 §9(PoC 단계)를 따른다. 명령어가 생기면 이 파일에 추가한다.

목표: DOCX/PDF 문서의 양식·필수 항목 검증(Use Case A)과 한국 기준 SOP ↔ 일본 SOP 비교(Use Case B).

단위별 설계(D-001의 6개 단위)는 `docs/superpowers/specs/`에 있다. 단위 ①은 [2026-11-11-foundation-rag-adapter-design.md](docs/superpowers/specs/2026-11-11-foundation-rag-adapter-design.md)다. 단위별 구현 계획은 `docs/superpowers/plans/`에 있다. 단위 ①은 [2026-11-11-foundation-rag-adapter.md](docs/superpowers/plans/2026-11-11-foundation-rag-adapter.md)다.

설계 문서 이후 확정된 결정은 [docs/DECISIONS.md](docs/DECISIONS.md)에 있으며, 설계 문서와 다르면 그쪽이 우선한다. 새 결정이 나오면 거기에 추가한다.

설계 문서는 검증 전 초안(v0.1)이다. 스택과 오픈소스 후보(§5)는 아직 실험하지 않았고, §12에 미결 의사결정이 남아 있다(기준의 우선순위, N/A 인정 조건과 승인자, MISSING 확정을 위한 재검토 범위 등). 구현 중 이런 정책이 필요해지면 임의로 정하지 말고 사용자에게 묻는다.

## 보안 (공개 저장소)

이 저장소는 Public이다. 사내 문서·SOP 원문, 사내 API 주소, credential ticket, 사용자 ID, 승인번호를 코드·커밋·로그·테스트 픽스처·보고서에 넣지 않는다. 테스트 데이터는 공개/가상 데이터만 `tests/fixtures/`에 둔다. 비밀값은 환경변수로만 읽고 `config/example.env`에는 자리표시자만 둔다.

## 아키텍처 (계획)

파이프라인: Document Intelligence(파싱) → Structured Document Model + Provenance → Requirement Builder → Coverage Auditor → 사람 승인 → Requirement Registry → Compliance Validator(근거 검색 + Rule Engine + LLM Semantic Judge + Evidence Recheck) → 5상태 판정 → 보고서. Format Validator는 내용 검증과 별도 경로로 구조화 모델을 받아 보고서로 간다. "형식 불합격"과 "내용 불충분"은 서로 다른 결과로 관리한다.

Compliance Validator의 단계 순서(§3.4): Applicability 확인 → 근거 후보 탐색 → 한·일 용어 정렬 → Rule 검증 → LLM 의미 검증 → 불일치·누락 의심 시 재검색 → 판정·사유·권고 작성 → Critical/UNKNOWN 사람 검토.

계획된 모듈(`app/` 하위): `parsing/`, `requirements/`, `validation/`, `llm/`, `models/`(Pydantic), `reporting/`, `storage/`, `api/`(FastAPI), `ui/`(Streamlit). 파싱 / 요구사항 생성 / 검증 / UI / LLM 게이트웨이는 서로 독립 모듈로 유지한다.

PoC v0.1 스택: Python 3.10, 입력은 외부 변환 파이프라인이 만든 `rag_ko.md`(원본 → 파서 JSON → LLM 재구성 Markdown → 한국어 번역. 형식은 [docs/RAG_KO_FORMAT.md](docs/RAG_KO_FORMAT.md)). 이 저장소에는 그 파일을 구조화 모델로 읽는 어댑터만 두고 파서는 만들지 않는다. 사내 OpenAI 호환 LLM(OpenAI SDK 또는 LangChain ChatOpenAI), Python 함수형 파이프라인(LangGraph는 이후), Streamlit, FastAPI. Vector DB와 자율 Multi-Agent는 PoC에서 도입하지 않는다. 근거 검색은 초기에 직접 대조로 하고, 문서 1쌍으로 파싱·추출·매핑·판정을 검증한 뒤 RAG를 도입한다.

평가는 `tests/evaluation/`의 판정 골든셋과 §10의 KPI로 한다. 단일 '정확도'로 판단하지 않으며, Critical 항목의 False Pass(실제 FAIL/MISSING을 PASS로 처리)를 가장 보수적으로 본다.

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

OpenAI 호환 API를 쓰는 공통 adapter를 `app/llm/`에 둔다. 설정은 환경변수 `DS_API_BASE_URL`, `DS_CREDENTIAL`, `DS_SYSTEM_NAME`, `DS_USER_ID`, `DS_LLM_MODEL`, `DS_OPENAI_API_KEY`에서 읽는다. 헤더 `x-dep-ticket`, `Send-System-Name`, `User-Id`, `User-Type`(값 `AD_ID`)을 붙이고, `Prompt-Msg-Id`와 `Completion-Msg-Id`는 **호출마다 새 UUID**를 발급한다. 골격 코드는 SYSTEM_DESIGN.md §6에 있다.
