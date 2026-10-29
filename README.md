# doc-compare

AI 기반 **문서 형식·필수 항목 검증** 및 **한국–일본 SOP 비교** 프로젝트.

## 설계 문서

- [시스템 설계·브레인스토밍 종합 (docs/SYSTEM_DESIGN.md)](docs/SYSTEM_DESIGN.md)

## 지향하는 MVP

1. 기준 SOP(DOCX/PDF)에서 문단·표·이미지·원본 출처를 추출한다.
2. Atomic Requirement를 자동 생성하고 Coverage Audit을 거쳐 사람이 승인한다.
3. 대상 SOP에서 근거를 찾고 Rule + LLM으로 충족 여부를 판정한다.
4. PASS / FAIL / MISSING / UNKNOWN / N/A 및 수정 권고를 근거와 함께 보고한다.

> 현재 단계: 아키텍처 설계 / PoC 준비. 실제 구현 및 성능 검증은 진행 전이다.

> 보안: 공개 GitHub 저장소에는 사내 문서, 내부 API 주소, 인증정보를 업로드하지 않는다.
