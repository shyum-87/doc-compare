# AI Document Compliance & SOP Comparison — 시스템 설계 초안

> 상태: Brainstorming / Architecture Draft v0.1  
> 정리일: 2026-10-29  
> 대상: 문서 양식·필수항목 검증 및 한국↔일본 작업 SOP 비교  
> 주의: 본 문서는 구현 방향을 정리한 설계안이며, 실제 엔진 성능·오픈소스 호환성·운영 적합성이 검증되었다는 뜻은 아니다.

## 1. 프로젝트 개요

### 1.1 목표

DOCX/PDF 등의 비정형 문서를 분석하고, **검증 가능한 기준(Atomic Requirement)** 을 생성·승인한 다음, 대상 문서가 그 기준을 충족하는지 원본 근거와 함께 판정하는 범용 AI 문서 검증 시스템을 구축한다.

**Use Case A — 고객 문서 검증**
- 사내 문서 템플릿/서식에 맞는지 확인한다.
- 필수 목차, 승인란, 버전, 문서번호, 체크리스트 항목의 누락을 식별한다.
- 불일치 위치와 수정 권고를 출력한다.

**Use Case B — 국가별 SOP 비교**
- 한국의 기준 SOP(DOCX/PDF)에서 검증 항목을 추출한다.
- 일본 SOP(DOCX/PDF)에서 대응하는 작업 절차·조건·증거를 찾는다.
- 한국 기준에 대비해 누락, 기술 조건 불일치, 불충분한 설명, 적용 제외 사유를 구분한다.
- 한국어/일본어 표현의 차이를 고려하며, 무조건 번역 일치 여부로 판단하지 않는다.

### 1.2 핵심 결론

**RAG는 '관련 근거 검색'에 사용하고, 문서 전체 검증의 완전성은 별도의 Coverage Audit과 Rule Engine으로 관리한다.**

임베딩/RAG만으로는 모든 문장·표·이미지·각주를 검증했다는 보장이 없다. 따라서 원본 구조 및 요소별 처리 이력, 승인된 요구사항 목록, 근거-요구사항 매핑, 미확인 항목 차단이 필요하다.

## 2. 아키텍처 원칙

1. **Parse first:** 텍스트 기반 DOCX/PDF는 Native Parsing을 먼저 수행하고, 스캔/이미지에 OCR·VLM을 선택 적용한다.
2. **Preserve provenance:** 원본 문서 ID/버전/페이지/절 번호/표 셀/Bounding Box를 유지한다.
3. **Atomic requirements:** 복합 문장을 검사 가능한 최소 요구사항으로 분해한다.
4. **Human-approved baseline:** AI가 추출한 한국 기준 요구사항은 담당자 승인 후 공식 검증 기준으로 사용한다.
5. **Fail closed:** 분석 실패, API 오류, 출처 누락, 저품질 파싱을 PASS로 취급하지 않는다.
6. **Applicability matters:** 설비·공정·국가·버전·현지 규정에 따라 적용 여부를 먼저 평가한다.
7. **Deterministic where possible:** 숫자, 단위, 범위, 필수 메타데이터, 파일 형식은 코드로 검사한다.
8. **Traceability:** REQUIREMENT → EVIDENCE → VERDICT → REVIEWER → REPORT의 연결을 보존한다.
9. **Closed network:** 외부 서비스 호출·기밀 자료 외부 유출 없이 내부망 환경에서 동작하도록 설계한다.
10. **Separating concerns:** Parsing / Requirement Building / Validation / UI / LLM Gateway를 독립 모듈로 구성한다.

## 3. 전체 시스템 구조

~~~mermaid
flowchart TD
    A["고객/한국/일본 DOCX·PDF"] --> B["Document Intelligence Engine"]
    B --> C["Structured Document Model + Provenance"]
    C --> D["Requirement Builder (한국 기준/사내 양식)"]
    D --> E["Coverage Auditor (추출 누락 검토)"]
    E --> F["담당자 승인 → Requirement Registry"]
    C --> G["Target Document Evidence Index"]
    F --> H["Compliance Validator"]
    G --> H
    H --> I["Rule Engine + LLM Semantic Judge"]
    I --> J["Evidence Recheck / Contradiction Audit"]
    J --> K["PASS / FAIL / MISSING / UNKNOWN / N/A"]
    K --> L["근거 기반 검증 보고서 + Human Review"]
    C --> M["Format Validator"]
    M --> L
~~~

### 3.1 Engine 01: Document Intelligence

**입력:** DOCX, 검색 가능한 PDF, 스캔 PDF, 혼합형 문서.

**처리 단계:**
1. 파일 형식·페이지·암호화 여부·언어 등 식별
2. DOCX/PDF 네이티브 파싱 및 문서의 읽기 순서 복원
3. 문단, 제목, 목차, 번호 매기기, 표, 이미지, 주석, 헤더/푸터 분리
4. 스캔·저품질 영역 OCR 수행
5. 이미지 속 작업 조건/화살표/조작 단계 등 필요 구역에 VLM 수행
6. 문서 객체와 위치 정보를 연결해 중간 JSON 생성
7. Parsing Quality Gate: 미처리 페이지·손상된 표·낮은 인식 신뢰도 확인

**중간 표현 예시 필드:**
- Document: id, filename, hash, version, language, country, process, equipment
- Section: id, number, title, parent_id, order
- Element: id, type(paragraph/table/image/note), text, reading_order, extraction_method
- Provenance: page, section, bbox, table/row/column, original_text
- ParsingStatus: processed, needs_review, failed, reason

**주의:** DOCX 세부 양식(폰트/글자 크기/여백/스타일/승인란)은 Native OOXML 스타일 또는 렌더링 결과를 별도로 검사해야 한다. Docling 구조 파싱만으로 정확한 서식 준수를 보증하지 않는다.

### 3.2 Engine 02: Requirement Builder

**목적:** 체크리스트가 없는 한국 SOP로부터 검증 가능한 표준 기준을 생성한다.

1. Section별 문단/표/이미지의 규범적인 진술을 식별한다.
2. 작업 수행, 확인 단계, 숫자 범위, 순서, 금지/주의, 예외 조건을 분리한다.
3. 각 진술을 Atomic Requirement로 구조화한다.
4. 중복/동의어를 통합하되 서로 다른 조건은 유지한다.
5. Coverage Auditor가 **원본의 모든 규범적 요소**에 대해 요구사항 매핑 또는 제외 사유가 있는지 재검토한다.
6. 적용 범위와 중요도(Critical/Major/Minor)를 검토한다.
7. 엔지니어가 기준을 승인하면 Requirement Registry에 버전 고정하여 저장한다.

**Coverage Audit 설계**
- 각 원본 요소에 source_element_id를 부여한다.
- 분류: REQUIREMENT_CREATED / NON_NORMATIVE / DUPLICATE_LINKED / REVIEW_REQUIRED / PARSING_FAILED.
- 중요한 요소인데 어느 항목에도 매핑되지 않은 경우 승인할 수 없도록 한다.
- Extractor와 Auditor가 서로 같은 실수를 반복할 수 있으므로, LLM 재검토 + 요소 단위 기계적 커버리지 검사 두 방식을 병행한다.

**원자적 분해 예시(가상의 조건)**

원본: "작업 전에 N₂ Purge를 실시하고 시간을 60초 이상으로 설정한 후 완료 여부를 확인한다."

- R-001: 작업 시작 전 N₂ Purge 수행 필수
- R-002: N₂ Purge 시간 60초 이상
- R-003: 완료 확인 절차 필수

수치는 설명을 위한 예시이며 실제 반도체 설비의 표준 조건이 아니다.

### 3.3 Requirement Registry 데이터 예시

~~~json
{
  "requirement_id": "KR-SOP-0042",
  "baseline_version": "v1",
  "category": "Process Condition",
  "subject": "N2 Purge",
  "property": "duration",
  "operator": ">=",
  "expected_value": 60,
  "unit": "sec",
  "mandatory": true,
  "severity": "Critical",
  "applicability": {
    "equipment": ["Equipment-A"],
    "process": ["Process-01"],
    "country": ["KR", "JP"]
  },
  "source": {
    "document_id": "KR-SOP-V3",
    "page": 4,
    "section": "4.2",
    "element_id": "table_04_cell_12"
  },
  "approval_status": "pending",
  "reviewer": null
}
~~~

추가 권장 필드: requirement_type, expected_evidence_type, exceptions, glossary_terms, extraction_model, prompt_version, created_at, effective_date, source_hash, approval_history.

### 3.4 Engine 03: Compliance Validator

**입력:** 승인된 Requirement Registry, 대상(일본/고객) SOP 구조화 모델, 검색 인덱스.

**검증 단계:**
1. Applicability 확인(공정, 설비, 국가, 버전, 조건부 예외)
2. 해당 Requirement와 연결된 Evidence 후보 탐색(Hybrid RAG / section-first retrieval)
3. 한국어/일본어 용어와 기술적 의미 정렬(원문 유지, 용어사전·다국어 embedding)
4. Rule 검증(수치·단위·부등호·필수 필드·순서 등)
5. LLM 의미 검증(설명 충족, 예외/주의조건, 작업 목적, 이미지 설명)
6. 불일치/누락 의심 시 재검색(주변 문단·표·원문 전체 범위)
7. 증거에 연결된 판정·사유·수정 제안 작성
8. Critical 항목 및 UNKNOWN 항목 Human Review

**Requirement–Evidence Mapping**
- requirement_id → evidence_document_id → source_element_id(다중 매핑 허용)
- 원문 인용/페이지/절/표 좌표 + 번역 또는 해석을 분리 저장
- 판정 이유와 수정 권고를 별도 저장
- 일본 문서에서 검색 결과가 없다는 사실만으로 MISSING 확정 금지

### 3.5 판정 상태 및 합격 규칙

| 상태 | 정의 | 자동 승인 |
|---|---|---|
| PASS | 적용 가능한 기준의 충족 근거가 충분히 확인됨 | 정책에 따라 가능 |
| FAIL | 적용 가능한 기준과 명시적 기술 조건 충돌 | 불가 |
| MISSING | 검색뿐 아니라 해당 문서 범위 검토 후 필수 항목 누락 판단 | 기본적으로 검토 필요 |
| UNKNOWN | 파싱/검색/LLM/API 오류 또는 근거 부족으로 판정 불가 | 불가 |
| N/A | 사전 승인된 비적용·예외조건에 해당 | 사유 및 승인 필요 |

**최종 통과 조건:** 승인된 기준 전체 검사 완료, Critical FAIL 없음, 판정 보류(UNKNOWN) 없음, 미승인 예외 없음, 문서 Parsing Quality Gate 통과. 정책상 인간 승인 필요 문서는 별도 Sign-off 후 최종 합격 처리한다.

### 3.6 문서 양식 검증(Use Case A)

내용 검증과 별도 Format Validator를 둔다.

- 필수 목차, 제목 계층, 파일 명명규칙, 문서번호, 개정 이력, 승인·검토란
- DOCX 스타일(폰트, 크기, 여백, 표 형식), PDF 페이지 규격
- 필요 시 기준 DOCX에서 템플릿 프로파일 추출(YAML/JSON)
- 항목별 근거, 실제 값, 요구 값, 위치, 수정 제안 제공
- "형식 불합격"과 "내용 불충분"을 별도의 결과로 관리

## 4. Agent 및 워크플로우 역할

| 단계 | 구현 방식 | 주요 역할 |
|---|---|---|
| Parser | Deterministic service + OCR/VLM | 구조 추출 및 누락 감지 |
| Requirement Extractor | LLM | 규범적 문장·Atomic Requirement 생성 |
| Coverage Auditor | LLM + 룰 | 원본 요소 대비 추출 누락 검사 |
| Baseline Approval | Human-in-the-loop | 요구사항 적합성·예외·중요도 승인 |
| Evidence Retriever | Hybrid Search | 대상 근거 후보 탐색 |
| Rule Validator | Python/Pydantic | 수치·단위·필드 검사 |
| Semantic Validator | LLM | 한·일 의미/조건 비교 |
| Evidence Recheck | Workflow + LLM | FALSE MISSING/충돌 재검토 |
| Reporter | Deterministic + LLM | 판정 집계 및 수정 제안 문장화 |

**추천:** 무제한 자율 Multi-Agent보다, 고정된 Workflow 위에서 LLM이 필요한 단계에만 Agent를 사용하는 하이브리드 방식. LangGraph는 분기·상태·중단/재개 및 승인 흐름 구현 후보.

## 5. 오픈소스/GitHub 재사용 후보

> 아래는 브레인스토밍 단계에서 발견한 **검토 후보**이다. 존재 여부와 일부 저장소 라이선스 정보는 확인했지만, 사내망 설치, 모델 호환성, 동작 품질, 정확한 코드 재사용 범위는 아직 실험하지 않았다. 실제 도입 시 라이선스·의존성·취약점·유지보수 이력을 재점검한다.

| 프로젝트 | 주소 | 관심 영역 | 적용 방향 |
|---|---|---|---|
| Docling | https://github.com/docling-project/docling | DOCX/PDF 파싱·테이블·구조화 | 파서 우선 후보(MIT 확인) |
| ARCCS | https://github.com/geofila/ARCCS | 규정에서 기준 추출 및 준수 검증 | 설계·알고리즘 참고; 명확한 라이선스 확인 전 코드 복사 금지 |
| agentic-compliance-api | https://github.com/singhvks/agentic-compliance-api | FastAPI + RAG + Compliance | API/검증 흐름 코드 재사용 검토(Apache-2.0 확인) |
| docx-tex-validator | https://github.com/gb119/docx-tex-validator | DOCX 규격·구조 검증 | 문서 양식 엔진 참고 |
| docx-format | https://github.com/sakzero/docx-format | DOCX 템플릿 프로파일·서식 | 기준 문서 포맷 규칙 추출 참고 |
| doc-audit | https://github.com/danielaskdd/doc-audit | 문서 점검·감사 리포트 | 결과/UI 참고; 상용 의존성 별도 조사 |
| reqtrace | https://github.com/timholm/reqtrace | 요구사항 추적·연결 | Traceability 데이터 모델 참고 |

**추가 기술 후보:** PaddleOCR/PP-StructureV3(스캔·레이아웃), 사내 이미지 인식 모델(VLM), BGE-M3 또는 multilingual-e5-large(다국어 검색), pgvector/OpenSearch(Hybrid Retrieval), Pydantic/JSON Schema(출력 구조), Ragas/DeepEval(평가).

**재사용 원칙:** ARCCS는 구조가 유사하더라도 검증 실패를 자동 COMPLIANT로 처리하는 패턴이 있으면 사용하지 않는다. 모든 LLM/네트워크/파싱 예외는 UNKNOWN과 담당자 검토 대상으로 처리한다.

## 6. 사내 LLM API 연동 설계(공개용 안전 요약)

- 사내 DS API HUB가 제공하는 **OpenAI 호환 API**를 이용한다.
- OpenAI Python SDK 및 LangChain ChatOpenAI를 연결할 수 있도록 공통 Adapter를 만든다.
- 모델 ID, Base URL, Credential, 사용자 ID, 승인된 시스템 이름은 **환경변수 또는 사내 Secret Store**에서 읽는다.
- 인증/식별 헤더: x-dep-ticket, Send-System-Name, User-Id, User-Type.
- 요청 추적 헤더: Prompt-Msg-Id, Completion-Msg-Id. **각 호출마다 별도의 UUID**를 발급한다.
- 이미지 요청은 승인된 모델의 image_url + Base64 Data URL 방식을 검토한다.
- 이미지 입력 성능·지원 형식·페이지/토큰 크기 제한은 API 테스트 후 확정한다.
- 코드/공개 저장소/로그/보고서에 실제 Endpoint, Ticket, 사용자 ID, SOP 원본을 기록하지 않는다.
- 과거 대화에 노출된 실제 Credential은 재발급·교체 후 사용한다.

**안전한 SDK 연동 골격(값은 환경변수):**

~~~python
import os
import uuid
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DS_OPENAI_API_KEY", "placeholder"),
    base_url=os.environ["DS_API_BASE_URL"],
    default_headers={
        "x-dep-ticket": os.environ["DS_CREDENTIAL"],
        "Send-System-Name": os.environ["DS_SYSTEM_NAME"],
        "User-Id": os.environ["DS_USER_ID"],
        "User-Type": "AD_ID",
    },
)

def call_llm(messages):
    response = client.chat.completions.create(
        model=os.environ["DS_LLM_MODEL"],
        messages=messages,
        extra_headers={
            "Prompt-Msg-Id": str(uuid.uuid4()),
            "Completion-Msg-Id": str(uuid.uuid4()),
        },
    )
    return response.choices[0].message.content
~~~

**주의:** JSON 형식의 응답이라고 해서 내용이 정확하다는 보장은 없다. 필드/스키마 검증, 근거 대조, 비적용 판단 및 안전 게이트를 별도로 구현해야 한다.

## 7. 기술 스택 제안

| 계층 | v0.1 추천 | 확장 방향 |
|---|---|---|
| UI | Streamlit | React 별도 프론트엔드 가능 |
| Backend | FastAPI | 작업 Queue/Batch |
| Parser | Docling | PaddleOCR, VLM 보조 |
| LLM adapter | OpenAI SDK 또는 LangChain ChatOpenAI | 모델 Router 및 Retry |
| Orchestrator | 우선 Python 함수형 Pipeline | LangGraph 승인/분기 도입 |
| Registry/Metadata | MSSQL 또는 PostgreSQL | 버전/감사 추적 |
| Retrieval | 초기 직접 대조 | OpenSearch / pgvector Hybrid RAG |
| File store | 사내 승인된 파일 저장소 | 객체저장소/버전관리 |
| Report | JSON + Excel/HTML | PDF, DOCX 주석, 원문 비교 뷰 |

### 7.1 권장 데이터 엔터티

- documents: 문서 ID, 유형, 국가, 언어, SHA-256, 버전, 승인 상태
- document_elements: 요소 ID, 부모 절, 유형, 텍스트, 위치, 파싱 상태
- requirements: 기준 ID, 원문 출처, 검증식, 중요도, 적용범위, 버전
- requirement_coverage: source_element_id, requirement_id, 매핑 상태, 제외 사유
- requirement_approvals: 승인자, 시각, 기준 버전, 변경 이력
- validation_runs: 대상 문서, 기준 버전, 모델/프롬프트 버전, 상태
- evidence_links: 기준 ID, 대상 요소 ID, 원문 근거, 검색 이력
- validation_results: 판정, 근거, 불일치, 권고, review_required
- review_actions: 담당자 수정/확정/기각 이력

문서 수정 또는 기준 버전 변경 시 기존 판정과 신규 판정을 구분해 보관한다.

## 8. 예시 검증 리포트(UI 요구사항)

**문서 쌍:** KR_SOP_V3 ↔ JP_SOP_V2 (가상 예시)

| ID | 체크 항목 | 기준 | 일본 문서 근거 | 결과 | 조치 |
|---|---|---|---|---|---|
| R-001 | Purge 실시 | 필수 | JP 4.2절 | PASS | 없음 |
| R-002 | Purge 시간 | ≥ 60초 | JP 6p: 45초 | FAIL | 설비별 적용 조건 검토 후 수정 |
| R-003 | 완료 확인 | 필수 | 전체 재검토 후 근거 미발견 | MISSING | 담당자 확인 |
| R-004 | 적용 설비 | Equipment-A | 모델 정보 불명확 | UNKNOWN | 설비 식별 필요 |

**필수 화면 기능**
- 두 원본 문서 나란히 보기 및 해당 페이지/표 하이라이트
- 검증 기준 목록·중요도·승인 상태 확인
- 상태별 필터(PASS/FAIL/MISSING/UNKNOWN/N/A)
- 원문 인용/번역/AI 판단 이유/수정 권고 분리 표시
- Reviewer 승인/기각/재검증, 다운로드 리포트, 추적 이력

## 9. PoC 범위와 실행 순서

### Phase 0 — 데이터·정답 준비
- 내부 보안정책에 따라 사용 가능한 한국·일본 SOP 5~10쌍 확보.
- 설비/공정/버전 차이가 명확히 기록된 데이터 선택.
- 엔지니어가 정답 체크리스트 및 불일치 사례를 수작업으로 라벨링.
- 의도적인 결함 삽입 테스트: 수치 변경, 단계 누락, 주의문 삭제, 표 값 변경, 스캔 이미지 조건 추가.

### Phase 1 — Document Parser
- DOCX/PDF → Structured JSON 변환.
- 문단·표·이미지/각주·페이지 출처 누락률 측정.
- 파싱 실패 시 자동 PASS 불가 처리.

### Phase 2 — Requirement Builder
- 한국 SOP 1건 → Atomic Requirement 초안 생성.
- Coverage Audit → 승인 가능한 체크리스트 제작.
- 중복률·Critical 항목 추출 재현율 측정.

### Phase 3 — 한·일 비교 MVP
- 일본 SOP 1건 업로드, Requirement별 근거 매핑.
- Rule + LLM 판정 및 FAIL/MISSING/UNKNOWN 재검토.
- JSON + 화면 + Excel 보고서 생성.

### Phase 4 — 검색·양식·운영 확장
- 길이가 긴 문서에 Hybrid RAG + Reranker 도입.
- 사내 서식/체크리스트 규칙 엔진 추가.
- 다국어 용어사전, 버전 비교, 감사 이력, 운영 권한 통제.

### 초기 MVP 완료 조건
1. 한국/일본 DOCX·PDF 1쌍을 입력할 수 있다.
2. 구조화된 한국 SOP에서 원본 출처가 연결된 Requirement 초안을 만든다.
3. 사용자가 Requirement를 승인/수정할 수 있다.
4. 일본 SOP에서 각 항목의 근거를 표시하고 5상태로 판정한다.
5. 실패·저신뢰 결과를 자동 PASS 처리하지 않는다.
6. 항목별 페이지/절 근거, 이유, 수정 권고를 보고서로 제공한다.

## 10. 검증 성능 및 품질 지표

| KPI | 의미 |
|---|---|
| Parsing Coverage | 전체 페이지·문단·표·이미지 중 처리 완료 비율 |
| Requirement Extraction Recall | 사람 정답 기준 대비 필수 요구사항 추출 재현율 |
| Coverage Audit Effectiveness | 최초 추출 단계의 누락을 감사 단계가 발견한 비율 |
| Evidence Retrieval Recall@k | 정답 근거가 검색 후보 내 존재하는 비율 |
| Critical Defect Recall | 중대 불일치·누락을 놓치지 않은 비율 |
| False Pass Rate | 실제 FAIL/MISSING인데 PASS로 처리한 비율 |
| Evidence Accuracy | 인용된 페이지·표·내용이 실제 근거와 일치하는 비율 |
| Reviewer Effort | 엔지니어 수작업 검증 소요시간 감소 |

숫자 하나의 '정확도'만으로 출시 판단을 내리지 않는다. 목표 수치는 초기 데이터셋에서 기준선을 측정한 뒤 정한다. 특히 중대 항목의 False Pass에 보수적인 운영 기준을 둔다.

## 11. 권장 프로젝트 파일 구성(향후 구현)

~~~text
doc-compare/
├── README.md
├── docs/
│   └── SYSTEM_DESIGN.md
├── app/
│   ├── api/                 # FastAPI
│   ├── ui/                  # Streamlit
│   ├── parsing/             # DOCX/PDF/OCR/VLM
│   ├── requirements/        # extractor, coverage auditor, registry
│   ├── validation/          # retrieval, rule judge, semantic judge, recheck
│   ├── llm/                 # DS OpenAI-compatible adapter
│   ├── models/              # Pydantic schemas
│   ├── reporting/           # JSON/Excel/HTML report
│   └── storage/             # DB/file abstractions
├── tests/
│   ├── fixtures/            # 공개/가상 테스트 데이터만
│   └── evaluation/          # 판정 골든셋 및 KPI
├── config/
│   └── example.env          # 실제 비밀값 미포함
└── .gitignore
~~~

## 12. 남은 핵심 의사결정 / 리스크

- **기준의 권위:** 한국 SOP가 반드시 정답인지, 사내 상위 표준·현지 규정 우선순위는 무엇인지?
- **적용범위:** 공정/설비 모델이 다른 경우 N/A 인정 조건과 승인자는 누구인지?
- **누락 정의:** 전체 범위를 어디까지 재검토해야 MISSING을 확정할 수 있는지?
- **다국어 품질:** 일본어 전문용어·약어·장비 UI 이미지까지 판별 가능한지?
- **원문 무결성:** PDF OCR 결과가 불확실할 때 재스캔/사람 검토 경로를 어떻게 둘지?
- **보안:** 사내 문서를 외부 GitHub/외부 API/공개 이슈에 절대 업로드하지 않도록 통제.
- **라이선스:** 특히 ARCCS 사용허가 확인, 오픈소스 하위 의존성 및 상용 SDK 점검.
- **운영:** 승인된 기준 버전, 재검증 기록, 오류·비용·지연·동시성 관리.
- **안전:** LLM이 제안한 공정 조건 변경은 승인된 기술 담당자 검토 없이 작업 지시로 전환하지 않는다.

## 13. 최종 권장 추진 방향

**PoC v0.1:** Docling + 사내 OpenAI 호환 LLM + Python Requirement Builder + Rule/LLM Validator + Streamlit.

- 처음부터 Vector DB와 다수의 자율 Agent를 모두 도입하지 않는다.
- 문서 1쌍으로 파싱·기준 추출·근거 매핑·판정 정확도를 검증한 후 RAG를 도입한다.
- Requirement Registry는 단순 체크리스트를 넘어 공정–설비–작업–조건–검증기준의 관계 자산으로 발전시킨다.
- 이후 여러 국가 SOP 비교, 고객 문서 검토, 문서 개정 영향도 분석, 온톨로지/Knowledge Graph 연계로 확장한다.

---

### 문서 보안 메모
이 저장소는 공개(Public) 상태에서 작성되었다. 따라서 사내 API 주소, 실물 credential ticket, 사용자 ID, 기밀 SOP 원문, 승인번호 등은 의도적으로 넣지 않았다. 코드 예시는 실행용 완성품이 아닌 안전한 인터페이스 샘플이다.
