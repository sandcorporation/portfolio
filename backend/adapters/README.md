# adapters — 외부 연동

외부 시스템은 좁은 인터페이스(`typing.Protocol`) 뒤에 둔다. 실제 구현과 가짜 구현을 나란히 둔다.

| 어댑터 | 실제 구현 | 가짜(시험용) |
| --- | --- | --- |
| 객체 저장소 | `storage.py` — OCI Object Storage S3 호환 API(boto3): presigned PUT/GET, 업로드, 존재 확인, 삭제 | `fake_storage.py` — 메모리에 객체와 호출 기록(`calls`)을 남김 |
| 알림 | Discord 웹훅(실패해도 요청은 실패시키지 않음) | 보낸 알림 목록을 남김 |
| PDF 렌더러 | browserless(`127.0.0.1:3000`)에 인쇄 URL 전달 | 요청한 인쇄 URL을 남김 |

시험은 `tests/conftest.py`의 픽스처로 가짜를 끼우고, 가짜에 남은 기록을 확인한다.

객체 저장소: 서비스는 `get_storage()`(설정 `STORAGE_*`)로 받고, 시험은 `fake_storage` 픽스처가 `services.media.get_storage`를 갈아 끼운다. 설정이 비면 `StorageNotConfigured`가 나고 사이트는 그대로 뜬다(미디어만 막힘).
OCI는 path-style 주소·SigV4·`request_checksum_calculation=when_required`가 필요하다(`S3ObjectStorage`에 고정).
