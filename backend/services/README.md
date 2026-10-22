# services — 도메인 서비스 계층

제안서·리비전·접근 코드·포트폴리오·문의 같은 도메인 규칙은 이 아래 모듈에 둔다.
ninja API(`core/api.py`와 이후 앱의 api)와 MCP 도구는 **같은 서비스 함수**를 부른다.
엔드포인트·도구는 입력 검증과 응답 모양만 맡고, 규칙은 여기서만 정한다.

- 외부 의존(객체 저장소·Discord·PDF 렌더러)은 함수 인자나 `adapters/`의 등록 지점을 통해 받는다.
- 블록 문서의 스키마·검증은 `documents/`(순수 Pydantic, Django 무관)에 있고, 서비스와 모델이 `validate_document`를 부른다.
- 예: `home.py`는 사이트 프로필에서 홈 셸에 심을 데이터(`HomeData`)를 만든다.
