# 파서 출력 계약

> 이 시스템은 이 JSON을 직접 읽지 않는다. 입력은 여기서 한 번 더 변환된 `rag_ko.md`다(D-006, [RAG_KO_FORMAT.md](RAG_KO_FORMAT.md)). 이 문서는 상류 단계의 참고 자료로 남긴다.

외부 파서([DECISIONS.md](DECISIONS.md) D-004)가 내놓는 1차 JSON의 구조다. 설명을 듣고 옮긴 것이며 실제 출력 파일로 검증하지는 않았다. 어댑터를 구현할 때 실제 출력과 대조하고, 다르면 이 문서를 고친다.

## 최상위 필드

| 필드 | 내용 |
|---|---|
| `source_file` | 원본 파일 |
| `output_dir` | 파서 작업 폴더 |
| `content` | 읽기 순서가 보존된 요소 배열 |
| `images_meta` | 이미지 ID → 절대 경로. 예: `{"img014": "<절대 경로>"}` |
| `tables_meta` | 표 ID → 행 리스트. 추출에 실패하면 `{"fallback": true, "text": ...}` |

## `content` 요소

`type`은 `paragraph`, `heading`, `image`, `table` 네 가지다.

| 요소 | 필드 |
|---|---|
| paragraph, heading | `type`, `level`, `style`, `text`. 있을 때만 `list_prefix`, `list_level` |
| image | `type`, `key`(이미지 절대 경로) |
| table | `type`, `key`(표 ID. 내용은 `tables_meta`에 있다) |

- **page marker:** `type`은 `paragraph`이고 `style == "page_marker"`다. 본문이 아니라 위치 정보다. `text`는 `[PAGE{n}]` 형태로 페이지 번호를 문자열 안에 담는다. 여는 마커라서, 페이지가 바뀌는 순간 마커가 먼저 오고 그 페이지의 요소가 뒤따른다.
- **서식 접미사:** 볼드 같은 서식은 `style` 값 뒤에 덧붙는다(예: `표준` + 볼드 접미사).
- **선택 필드:** `list_prefix`, `list_level`은 없을 수 있으므로 `.get()`으로 읽는다.

## `key`는 위치마다 뜻이 다르다

| 위치 | `key`의 값 |
|---|---|
| `content`의 image 요소 | 이미지 절대 경로 |
| `content`의 table 요소 | 표 ID (`tables_meta`의 키) |
| 표 셀 `mixed`의 `contents` 안 image | 이미지 참조 (값의 형태 미확인) |

`content`의 image와 `images_meta`는 키가 아니라 **값**(절대 경로)으로 연결된다. 이미지 ID가 필요하면 `images_meta`를 경로로 역조회한다.

## 표

`tables_meta[key]`는 정상이면 `list`(행 리스트), 실패하면 `dict`(fallback)다. `isinstance`로 구분한다.

셀 `rows[r][c]`의 형태는 네 가지다.

| 셀 값 | 의미 |
|---|---|
| 문자열 | 일반 셀 |
| `{"type": "mixed", "text": ..., "images": ..., "contents": ...}` | 텍스트와 이미지가 섞인 셀. 이미지가 하나라도 있으면 문자열 대신 이 형태가 된다 |
| `{"merged_from": [행, 열], "text": ...}` | 병합으로 확장된 셀. `merged_from`은 원본 셀의 위치다 |
| `null` | 셀 접근 실패 |

## 파일 형식별 차이

- Word, Excel: 텍스트만 나온다.
- PDF: 페이지 스크린샷으로 나온다.
- PPT: 슬라이드 PNG로 나온다.
- 이미지에 대한 VLM 설명이 들어가는 필드는 JSON에 없다.

## 어댑터가 지켜야 할 것

- bbox가 없다. 출처는 페이지(page marker) + 절 경로(heading, 목록 번호) + `content` 순번으로 만들고, 표는 표 ID + 행 + 열을 더한다.
- 요소 ID가 없다. 어댑터가 `content` 순번과 셀 좌표로 부여한다.
- 표 fallback과 `null` 셀은 파싱 실패 신호다. 해당 요소를 검토 필요로 표시하고 PASS 근거로 쓰지 않는다.
- 절대 경로에는 사내 폴더명이나 사용자 ID가 들어 있을 수 있다. 모델·로그·보고서에는 `output_dir` 기준 상대 경로만 남긴다.

## 미확인

- `[PAGE{n}]`의 정확한 표기(공백 유무 등).
- paragraph의 `level` 값이 뜻하는 것.
- `merged_from`의 행·열이 0부터인지 1부터인지.
- `mixed` 셀 `contents` 안 image의 `key` 값 형태, `images`가 단일 경로인지 리스트인지.
- 2차 Markdown의 구조와, VLM이 읽은 이미지·PDF 내용이 그 안에 어떻게 들어가는지.
