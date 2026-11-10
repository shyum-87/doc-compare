# 외부 사례 조사

[SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) §5의 후보 중 기준 추출·준수 검증과 관련된 저장소 4곳을 2026-11-10에 읽고 정리했다. 코드를 가져오지 않았고, 설계 참고로만 쓴다.

읽은 범위가 저장소마다 다르다. 아래에 "읽지 않음"으로 적은 부분은 확인하지 않은 것이다. README의 성능 수치는 검증하지 않았으므로 옮기지 않았다.

## 저장소별 요약

| 저장소 | 라이선스 | 문서를 다루는 단위 | 기준 추출 | 대상 문서 검사 | 오류 처리 |
|---|---|---|---|---|---|
| [ARCCS](https://github.com/geofila/ARCCS) | 라이선스 파일 없음 | 헤딩으로 나눈 절(`title`, `content`). 페이지·ID 없음 | 절마다 LLM 1회 호출. 필드 완성도 점수로 걸러냄 | 검색 없음. 기준마다 대상 문서 전체를 넣어 "모순이 있는가"를 물음 | 예외가 나면 COMPLIANT를 돌려줌 |
| [agentic-compliance-api](https://github.com/singhvks/agentic-compliance-api) | Apache-2.0 | 토큰 단위 청크. 페이지 번호 + 텍스트 | 없음. 규칙은 사람이 쓴 JSON | 임베딩 검색(FAISS) + 키워드 필터 → LLM 판정 → 2차 판정(신뢰도만 매김) | 판정 단계에서 예외가 나면 위반 없음으로 처리됨 |
| [doc-audit](https://github.com/danielaskdd/doc-audit) | MIT | 가장 낮은 헤딩 단위 블록. Word 문단 ID 범위(`uuid`~`uuid_end`). 표는 블록 안에 포함 | 자연어 → 규칙 JSON. 사용자가 규칙 목록을 승인한 뒤 실행 | 검색 없음. 블록마다 적용 규칙과 함께 LLM 1회 호출 | 실패한 블록은 결과에 기록되지 않음. 응답에 `violations` 키가 없으면 위반 없음으로 봄 |
| [reqtrace](https://github.com/timholm/reqtrace) | MIT | 청크(필드 미확인) | "shall" 문장 추출 프롬프트 | 미확인 | 미확인 |

읽은 파일: ARCCS는 README, `RPEM.py`, `CCM.py`. agentic-compliance-api는 README, `analyzer.py`, `judge.py`. doc-audit는 README와 `run_audit.py` 앞 절반. reqtrace는 README뿐이다.

## 이 프로젝트에 주는 의미

### 따라 하지 않을 것

- **실패를 통과로 처리하는 코드.** 읽은 세 곳 모두에 있다. ARCCS는 예외 시 COMPLIANT를 돌려주고, agentic-compliance-api는 위반 없음이 되고, doc-audit는 실패한 블록이 결과에서 빠진다. 이 프로젝트는 모두 UNKNOWN + 사람 검토로 보낸다.
- **추출 실패가 "기준 없음"으로 바뀌는 것.** ARCCS는 절 추출이 실패하면 빈 목록을 돌려주므로, 그 절의 기준이 조용히 사라진다. Coverage Audit을 요소 단위로 기계적으로 해야 하는 이유다.
- **입력 일부를 버리는 분할.** ARCCS는 첫 헤딩 앞의 본문을 버리고, 헤딩이 없는 문서는 절이 0개가 된다(코드상 그렇게 읽히며 실행해 확인하지는 않았다). 이 프로젝트의 파서는 어떤 줄도 버리지 않는다.
- **지어낸 인용.** agentic-compliance-api는 LLM이 인용 위치를 빠뜨리면 첫 청크의 페이지와 앞 50자를 대신 넣는다. 이 프로젝트는 LLM이 낸 인용문이 실제 요소 안에 있는지 코드로 대조한다.

### 참고할 것

- **절(가장 낮은 헤딩)을 작업 단위로 삼고 표를 절 안에 둔다(doc-audit).** `rag_ko.md`의 조항 번호 구조와 맞는다.
- **근거를 요소 ID 범위로 가리킨다(doc-audit).** `rag_ko.md`에는 Word 문단 ID가 없으므로 파서가 요소 ID를 부여한다.
- **기준 목록을 사람이 승인한 뒤 검사한다(doc-audit).** 설계의 "사람 승인 후 버전 고정"과 같다.
- **검색 없이 직접 대조로 시작한다(ARCCS, doc-audit).** PoC에서 Vector DB를 쓰지 않는 계획과 같다.
- **코드가 판정을 덮어쓴다(ARCCS).** 모순 여부, 정보 유무, 신뢰도 같은 필드를 LLM에게 받고 최종 상태는 코드가 정한다.

### 어디에도 없는 것

- 숫자·단위·범위의 결정적 검사
- 번역 전후 대조
- 추출이 원본 전체를 덮었는지 확인하는 Coverage Audit
- Applicability 평가, N/A 상태

이 부분은 참고할 구현이 없으므로 직접 설계한다.

## 읽지 않은 후보

검색에서 제목만 확인했다. 단위 ③·④를 설계할 때 읽는다.

- PROPARAG ([arXiv 2605.07515](https://arxiv.org/abs/2605.07515)): 통제 항목 단위로 근거 검색 → 충족 평가 → 누락 식별을 나눈 파이프라인
- De Jure ([arXiv 2604.02276](https://arxiv.org/abs/2604.02276)): 규정을 JSON 규칙 단위로 추출하고 LLM 판정으로 반복 개선
- Reg2Req ([Zenodo 19209666](https://zenodo.org/records/19209666)): 규정에서 요구사항을 도출하는 파이프라인
- §5의 docx-tex-validator, docx-format: 서식 검증 후보. 단위 ⑥에서 읽는다.
