# services — 도메인 서비스 계층

제안서·리비전·접근 코드·포트폴리오·문의 같은 도메인 규칙은 이 아래 모듈에 둔다.
ninja API(`core/api.py`와 이후 앱의 api)와 MCP 도구는 **같은 서비스 함수**를 부른다.
엔드포인트·도구는 입력 검증과 응답 모양만 맡고, 규칙은 여기서만 정한다.

- 외부 의존(객체 저장소·Discord·PDF 렌더러)은 함수 인자나 `adapters/`의 등록 지점을 통해 받는다.
- 블록 문서의 스키마·검증은 `documents/`(순수 Pydantic, Django 무관)에 있고, 서비스와 모델이 `validate_document`를 부른다.
- 예: `home.py`는 사이트 프로필에서 홈 셸에 심을 데이터(`HomeData`)를 만든다.
- 예: `portfolio.py`는 포트폴리오 항목을 읽는다. 공개 조회(`public_cards`·`public_detail`·`public_slugs`)와 숨긴 항목까지 보는 전체 조회(`all_items`·`get_item`)를 나눠 두었다. 제안서 `case-ref`와 MCP 도구는 전체 조회를 쓴다.
- 예: `media.py`는 미디어(Object Storage의 파일)를 다룬다. `start_upload`(presigned PUT) → `complete_upload`, 서버가 바이트를 가진 경우의 `upload`, `list_media`, `public_url`, `delete_media`, 서빙할 때 갤러리 URL을 채우는 `resolve_document`. 완료되지 않은 미디어는 블록·대표 이미지에서 참조할 수 없다(`content.models.stored_document`가 저장 때 검사).
- 예: `portfolio.py`의 쓰기 함수(`create_item`·`update_item`·`set_visibility`·`reorder`·`list_summaries`·`read_item`)와 `profile.py`(`get_profile`·`update_profile`)는 입력을 Pydantic 모델(`NewItem`·`ItemPatch`·`ProfilePatch`; 주어진 필드만 바뀜)로 받고 Pydantic 모델을 돌려준다. 거부는 `errors.py`의 `Rejected`(블록 경로 목록, 저장 안 됨)·`NotFound`·`Conflict`. MCP 도구(`mcpserver/tools.py`)는 이를 `isError` 결과로, 관리자 API(`core/admin_api.py`, `/api/admin/...`)는 404·409·422로 바꾼다.
- 예: `proposals.py`는 고객·제안서(초안)를 다룬다. 고객 `list_clients`·`create_client`·`update_client`, 제안서 `list_proposals`·`get_proposal`·`create_proposal`(두 탭 「견적 제안」「회사소개·수행사례」로 시작, 무작위 slug)·`duplicate_proposal`·`update_proposal`(메타), 문서 `replace_document`·`replace_block`·`insert_block`·`delete_block`·`add_tab`·`delete_tab`·`rename_tab`·`reorder_tabs`(블록은 `block_id`, 탭은 `tab_id`로 가리키고 다른 곳은 건드리지 않음; 초안만 고칠 수 있음, 오류 경로는 `document.tabs[..]`), 미리보기 `issue_preview_url`(서명·`PROPOSAL_PREVIEW_MAX_AGE` 30분)·`proposal_for_preview`, 화면 데이터 `page_data`(미리보기와 #12 고객 화면이 함께 씀).
- 예: `blocks.py`는 블록 타입 목록(`block_types`), 타입별 JSON Schema와 예시(`block_schema`), 문서 전체 스키마(`document_schema`)를 낸다. MCP `block_schema` 도구가 쓴다. 새 블록 타입은 `EXAMPLES`에 예시를 더해야 시험이 통과한다.
- 예: `inquiries.py`는 문의를 다룬다. `submit(NewInquiry, trusted=, ip=)`(저장 → Discord 알림; 알림 실패는 접수를 막지 않음. `trusted`는 엔드포인트가 공유 시크릿으로 정함 — 믿는 호출자만 `site`를 정하고 honeypot·IP 제한(`INQUIRY_RATE_LIMIT`/시간, `django_cache`)을 건너뜀; honeypot에 걸리면 `Received(None)`), `list_inquiries(unhandled_only=, limit=)`·`mark_handled(id)`(멱등; #24 MCP 도구용). 제한 초과는 `errors.RateLimited`(HTTP 429).

MCP 도구(`mcpserver/tools.py`)는 `@tool(이름, 제목, 설명, 입력 모델)`로 등록하는 얇은 껍데기다. `/mcp`(Streamable HTTP, JSON 응답만, 스코프 `admin`)와 ninja 관리 API(`auth=BearerAuth("admin")`)는 같은 sandcorp-auth 토큰 검증(`oauth/bearer.py`)을 쓴다.
