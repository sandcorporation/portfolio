# adapters — 외부 연동

외부 시스템은 좁은 인터페이스(`typing.Protocol`) 뒤에 둔다. 실제 구현과 가짜 구현을 나란히 둔다.

| 어댑터 | 실제 구현 | 가짜(시험용) |
| --- | --- | --- |
| 객체 저장소 | `storage.py` — OCI Object Storage S3 호환 API(boto3): presigned PUT/GET, 업로드, 존재 확인, 삭제 | `fake_storage.py` — 메모리에 객체와 호출 기록(`calls`)을 남김 |
| sandcorp-auth JWKS | `sandcorp_authkit.tokens.http_jwks_fetcher`(패키지) | `sandcorp_authkit.testing.FakeJwks`(패키지): Ed25519 키로 토큰 서명, JWKS 제공·조회 횟수(`fetches`)·실패(`failing`)·회전(`rotate`), `FixedClock` |
| sandcorp-auth 토큰 엔드포인트 | `sandcorp_authkit.login.exchange_code`(패키지, `client_secret_basic`) | `sandcorp_authkit.testing.FakeTokenEndpoint`(패키지): `approve(url)`(인가 승인 → 콜백 쿼리)·`transport` 자리(클라이언트 비밀·일회용 코드·redirect_uri·PKCE 확인, 받은 요청은 `requests`) |
| 알림 | `notify.py` — `Notifier.send(Notification)`; Discord 웹훅(활동 `DISCORD_WEBHOOK_URL`, 경보 `DISCORD_ALERTS_WEBHOOK_URL` — `Notification.severity`가 "alert"면 경보 웹훅, 비면 활동 웹훅으로 폴백; 5초, 실패는 로그만 남기고 `False`를 돌려줌). URL이 비면 `NoNotifier` | `fake_notify.py` — `FakeNotifier`: 보낸 알림 `sent`, `failing`으로 Discord 장애 흉내 |
| PDF 렌더러 | `renderer.py` — `PdfRenderer.render(url) -> bytes`; 프로젝트 전용 browserless(compose `renderer`, `PDF_RENDERER_URL`)의 REST `/pdf`에 인쇄 URL을 넘기고 `printReady`를 기다려 A4 PDF를 받음. `PDF_RENDERER_TOKEN`이 비면 `UnconfiguredRenderer`(늘 `RenderFailed`) | `fake_renderer.py` — `FakeRenderer`: 받은 URL `urls`, `failing`으로 장애 흉내 |
| Foresight 최근 기사 | `foresight.py` — `ForesightGateway.recent(limit)`; 뉴스 공개 JSON `GET {FORESIGHT_API_URL}?limit=N`(3초, AI-Trend-News #73 모양 `{"items":[...]}`; `category{name,slug}`는 이름만 씀). `FORESIGHT_API_URL`이 비면 `DisabledForesight`(늘 빈 목록) | `fake_foresight.py` — `FakeForesight`: `articles`·받은 limit `calls`·`failing` |

시험은 `tests/conftest.py`의 픽스처로 가짜를 끼우고, 가짜에 남은 기록을 확인한다.

객체 저장소: 서비스는 `get_storage()`(설정 `STORAGE_*`)로 받고, 시험은 `fake_storage` 픽스처가 `services.media.get_storage`를 갈아 끼운다. 설정이 비면 `StorageNotConfigured`가 나고 사이트는 그대로 뜬다(미디어만 막힘).
`read_head(bucket, key, length)`는 객체 앞부분만 범위 GET으로 읽는다(이미지 크기 헤더용, #123; 가짜는 `read_head_failing`으로 장애를 흉내). OCI는 path-style 주소·SigV4·`request_checksum_calculation=when_required`가 필요하다(`S3ObjectStorage`에 고정).

sandcorp-auth: 토큰 검증·bearer·운영자 로그인 코드는 `sandcorp-authkit` 패키지(sandcorp-auth `clients/python`)에 있고, 이 저장소의 어댑터는 `oauth/auth.py` 한 파일이다(settings → 함수 인자). 키·시각은 `oauth.auth.jwks_cache()`(프로세스당 하나, 10분 캐시)와 `oauth.auth.clock`으로 받는다. 시험은 `auth_server` 픽스처(`tests/site_auth.py`의 `SiteAuth`)가 둘과 `token_transport()`를 패키지의 `FakeJwks`·`FixedClock`·`FakeTokenEndpoint`로 갈아 끼우고 `AUTH_OWNER_SUB`를 `"owner"`로 둔다.
admin 로그인(뷰는 `oauth/admin_login.py`, 프로토콜은 패키지 `sandcorp_authkit.login`, 문서 7절): `<ADMIN_PATH>oauth/login/` → sandcorp-auth `/authorize` → `<ADMIN_PATH>oauth/callback/`에서 코드 교환·`login` 스코프 검증 → Django 세션(사용자 `username`=`sub`). 시험은 `auth_server` 픽스처가 `AUTH_CLIENT_ID`/`AUTH_CLIENT_SECRET`도 채운다.

알림: 서비스는 `get_notifier()`(`DISCORD_WEBHOOK_URL`·`DISCORD_ALERTS_WEBHOOK_URL`)로 받고, 시험은 `notifier` 픽스처가 `services.inquiries.get_notifier`를 갈아 끼운다. `Notification(title, text, fields)`는 이벤트 종류를 모른다 — 새 이벤트(예: #18 열람 알림)는 그 서비스가 `Notification`을 만들어 `get_notifier().send(...)`를 부르면 된다(어댑터 수정 불필요; 서비스 쪽 시험은 같은 방식으로 `get_notifier`를 갈아 끼운다). 보내기는 예외를 내지 않고, 호출하는 쪽도 알림 때문에 요청을 실패시키지 않는다. `allowed_mentions`를 비워 방문자 텍스트가 @everyone을 못 부른다.

PDF 렌더러: 서비스(`services/pdf.py`)는 `get_renderer()`로 받고, 시험은 `renderer` 픽스처가 `services.pdf.get_renderer`를 갈아 끼운다. 실패는 모두 `RenderFailed`.

Foresight: 화면 쪽은 `fetch_recent(limit=5)`만 부른다. 예외를 내지 않는다 — 성공한 답은 `django_cache`에 10분(`foresight:recent:<limit>`)과 「마지막 성공 값」 24시간(`foresight:last-good:<limit>`)으로 두고, 뉴스 사이트가 실패하면 마지막 성공 값(없으면 빈 목록)을 돌려주며 로그 한 줄을 남긴다(그 대체 값도 10분 캐시해 죽은 사이트를 매 요청 부르지 않는다). 게이트웨이는 `set_gateway`/`get_gateway`로 바꾸고, 시험은 `tests/conftest.py`의 autouse `foresight` 픽스처가 늘 `FakeForesight`를 끼운다(시험이 실제 사이트에 닿지 않음).

Foresight 통계(#91): `fetch_stats()`는 `ForesightGateway.stats()`(`FORESIGHT_STATS_URL`, AI-Trend-News #77 모양)를 같은 규칙으로 읽어 `ForesightStats | None`을 돌려준다(캐시 `foresight:stats` 10분, `foresight:stats-last-good` 24시간; 실패하고 마지막 값도 없으면 None을 10분 캐시). 시험은 `FakeForesight.stats_value`·`stats_calls`.
