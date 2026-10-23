# Postgres → MySQL(OCI HeatWave) 데이터 이전 (#63)

조율자가 한 번 따르는 절차다. 운영 DB는 HeatWave 인스턴스(MySQL 26.10, 사설 IP)의 `utf8mb4` / `utf8mb4_0900_as_cs` 데이터베이스이고, 서비스 계정이 그 DB에 모든 권한을 가진다. **이 PR을 병합하면 Jenkins가 곧바로 새 이미지로 배포한다** — 그래서 덤프·적재를 병합 전에 끝낸다.

## 0. 준비

- `.env`에 `DB_HOST`·`DB_PORT`(3306)·`DB_NAME`·`DB_USER`·`DB_PASSWORD`를 더한다. 옛 `POSTGRES_*`는 되돌릴 일이 없어질 때까지 남겨 둔다(새 코드는 읽지 않는다).
- 운영 호스트에서 HeatWave에 닿는지: `docker run --rm --env-file .env <새 이미지> python manage.py check --database default`.

## 1. 쓰기 중지

```bash
cd <Jenkins 워크스페이스>
export COMPOSE_PROJECT_NAME=portfolio COMPOSE_FILE=docker-compose.prod.yml:docker-compose.oracle.yml
docker compose stop worker backup web    # web도 멈춘다: 열람 기록·문의가 덤프 뒤에 쓰이면 잃는다
```

## 2. 옛 이미지(Postgres)에서 덤프

```bash
docker compose run --rm --no-deps -T web python manage.py dumpdata \
  --natural-foreign --indent 0 \
  -e contenttypes -e auth.permission -e sessions -e admin.logentry \
  > portfolio-dump.json
python3 -c "import json,collections;print(collections.Counter(o['model'] for o in json.load(open('portfolio-dump.json'))))"
```

- 빼는 것: `contenttypes`·`auth.permission`(migrate가 새로 만든다), `sessions`(로그인은 다시 하면 된다), `admin.logentry`(contenttype 번호에 묶인 기록). DB 캐시 테이블(`portfolio_cache`: 접근 코드·문의 제한, 열람 중복 제거)은 모델이 아니라 덤프에 없고 비워 둬도 된다.
- 이 저장소의 앱은 `core`(모델 없음)·`content`뿐이라 그 밖에 뺄 것은 없다. `auth.user`(대표 계정)·`auth.group`은 넣는다.
- 미리 확인(0건이어야 한다): `SELECT count(*) FROM content_media WHERE length(object_key) > 255;` — 이 PR이 `Media.object_key`를 255자로 줄였다(키는 uuid hex + 확장자라 40자 안팎).

## 3. 새 이미지로 빈 스키마 → 적재 (병합 전)

PR 브랜치를 운영 호스트에서 빌드해 HeatWave에 먼저 적재해 두면, 병합 뒤 배포의 migrate는 할 일이 없고 빈 DB로 서비스하는 틈이 없다.

```bash
git fetch origin feat-63-mysql && git worktree add /tmp/p63 origin/feat-63-mysql
docker build -t portfolio-web:mysql /tmp/p63
R="docker run --rm --env-file .env -e DJANGO_DEBUG=0 -v $PWD/portfolio-dump.json:/tmp/dump.json:ro portfolio-web:mysql"
$R python manage.py migrate --noinput
$R python manage.py createcachetable
$R python manage.py loaddata /tmp/dump.json
```

## 4. 건수 대조

```bash
$R python manage.py shell -c "
import json, collections
from django.apps import apps
want = collections.Counter(o['model'] for o in json.load(open('/tmp/dump.json')))
got = {m: apps.get_model(m).objects.count() for m in want}
print('MATCH' if dict(want) == got else 'DIFF', sorted(got.items()))"
```

AUTO_INCREMENT는 loaddata가 넣은 가장 큰 id 다음으로 InnoDB가 알아서 맞춘다(시퀀스 재설정 불필요).

## 5. 병합·배포·스모크

병합하면 Jenkins가 `deploy/deploy.sh`를 돈다(DB 접속 대기 → migrate(할 일 없음) → web·worker·backup 교체). 그다음:

- `/api/health` → `{"status": "ok", "db": "ok"}`
- `/`, `/work/<공개 항목 slug>`, `/sitemap.xml`
- 발행된 제안서 주소 → 접근 코드 화면, 코드 입력 후 문서가 그대로 보이는지(블록 문서 JSON)
- admin 로그인(sandcorp-auth) → 제안서·리비전·열람 기록 목록
- `docker compose exec backup python manage.py db_backup --force` → 버킷에 `….sql.gz`가 생기는지

옛 `postgres` 컨테이너와 `pgdata` 볼륨은 compose 파일에서 빠졌지만 지워지지 않고 남는다(배포가 `--remove-orphans`를 쓰지 않는다). 안정되면 `docker stop portfolio-postgres-1 && docker rm portfolio-postgres-1`, 볼륨은 한참 뒤 `docker volume rm portfolio_pgdata`.

## 되돌리기

병합을 되돌리면(revert PR) 옛 이미지가 다시 Postgres를 본다. 그 사이 MySQL에 쓰인 것(열람 기록·문의·새 제안서)은 Postgres에 없다 — 필요하면 2~4를 반대 방향(MySQL에서 dumpdata → Postgres에 loaddata)으로 한다.

## 동작 차이(알고 있을 것)

- JSON 열(블록 문서·프로필): 값은 같지만 **객체 키 순서**를 MySQL이 정규화한다(길이 → 사전 순). 배열 순서는 그대로다. 앱은 키 순서에 기대지 않는다.
- 대소문자: DB 콜레이션이 `_as_cs`라 slug·`Client.code`·username 비교가 Postgres처럼 대소문자를 구분한다(`tests/test_mysql.py`).
- 첫 열람 유일: 부분 유일 제약 대신 식 기반 유일 인덱스 `event_first_view_once` = `(CASE WHEN first THEN revision_id END)`.

## 로컬 리허설 결과 (2026-10-23)

옛 코드(d1102dd, Postgres 17)의 빈 DB에 migrate → 예시 문서(`fixtures/documents/example-proposal.json`)로 미디어 16·포트폴리오 항목 3(하나는 본문 = 블록 문서)·고객 2·제안서 3·발행 3번(리비전 3, PDF 작업 3)·열람 기록 3(첫 열람 1)·문의 2·대표 계정 1·프로필 1을 만들고 위 2의 명령으로 덤프 → 새 코드로 로컬 MySQL 26.10 빈 DB에 3의 명령.

| 단계 | 결과 |
|---|---|
| migrate (빈 MySQL, 28개) | 오류 없음, 9.6초 |
| loaddata | `Installed 37 object(s)`, 0.9초 |
| 건수 대조 | 10개 모델 모두 일치 |
| 필드 대조(다시 직렬화해 원본 JSON과 비교) | 다른 칸 0 — JSON·datetime·bool·빈 문자열·한글 그대로 |
| 블록 문서 읽기 | 제안서 3·리비전 3·항목 본문을 서비스(`get_proposal`·`get_revision`)로 읽음, 탭 2개씩 |
| AUTO_INCREMENT | 새 문의 id 3(기존 최대 2), media 17·revision 4·event 4 |
| 유일 인덱스 | `event_first_view_once` = `(case when (first = 0x01) then revision_id else NULL end)` |
