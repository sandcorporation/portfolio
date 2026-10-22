# services — 도메인 서비스 계층

제안서·리비전·접근 코드·포트폴리오·문의 같은 도메인 규칙은 이 아래 모듈에 둔다.
ninja API(`core/api.py`와 이후 앱의 api)와 MCP 도구는 **같은 서비스 함수**를 부른다.
엔드포인트·도구는 입력 검증과 응답 모양만 맡고, 규칙은 여기서만 정한다.

- 외부 의존(객체 저장소·Discord·PDF 렌더러)은 함수 인자나 `adapters/`의 등록 지점을 통해 받는다.
- 블록 문서의 스키마·검증은 `documents/`(순수 Pydantic, Django 무관)에 있고, 서비스와 모델이 `validate_document`를 부른다.
- 예: `home.py`는 사이트 프로필에서 홈 셸에 심을 데이터(`HomeData`)를 만든다.
- 예: `portfolio.py`는 포트폴리오 항목을 읽는다. 공개 조회(`public_cards`·`public_detail`·`public_slugs`)와 숨긴 항목까지 보는 전체 조회(`all_items`·`get_item`)를 나눠 두었다. 제안서 `case-ref`와 MCP 도구는 전체 조회를 쓴다.
- 예: `media.py`는 미디어(Object Storage의 파일)를 다룬다. `start_upload`(presigned PUT) → `complete_upload`, 서버가 바이트를 가진 경우의 `upload`, `list_media`, `public_url`, `delete_media`, 서빙할 때 갤러리 URL을 채우는 `resolve_document`. 완료되지 않은 미디어는 블록·대표 이미지에서 참조할 수 없다(`content.models.stored_document`가 저장 때 검사).
- 예: `blocks.py`는 블록 타입 목록(`block_types`), 타입별 JSON Schema와 예시(`block_schema`), 문서 전체 스키마(`document_schema`)를 낸다. MCP `block_schema` 도구가 쓴다. 새 블록 타입은 `EXAMPLES`에 예시를 더해야 시험이 통과한다.

MCP 도구(`mcpserver/tools.py`)는 `@tool(이름, 제목, 설명, 입력 모델)`로 등록하는 얇은 껍데기다. `/mcp`(Streamable HTTP, JSON 응답만, 스코프 `admin`)와 ninja 관리 API(`auth=BearerAuth("admin")`)는 같은 sandcorp-auth 토큰 검증(`oauth/bearer.py`)을 쓴다.
