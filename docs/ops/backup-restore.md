# DB 백업과 복원 (#19)

## 어떻게 도는가

- 운영 compose의 `backup` 서비스(웹과 같은 이미지, `pg_dump` 17 포함)가 `python manage.py db_backup`을 돈다. 5분마다 「가장 최근 04:00 KST 이후 백업이 있는가」를 버킷 목록으로 보고, 없으면 하나 만든다. 컨테이너가 재시작돼도 하루 두 번 돌지 않고, 쉬었다 켜지면 빠진 몫을 바로 채운다.
- 객체: 비공개 버킷(`STORAGE_PRIVATE_BUCKET`)의 `backups/YYYY/MM/DD/portfolio-<UTC시각>.dump` (`pg_dump -Fc`, 이미 압축됨). 날짜는 UTC다.
- 업로드 뒤 30일(UTC 기준)보다 오래된 `backups/` 객체를 지운다. `backups/` 밖은 건드리지 않는다.
- 실패(덤프·업로드·정리)하면 운영 경보 웹훅(`DISCORD_ALERTS_WEBHOOK_URL`, 비면 `DISCORD_WEBHOOK_URL`)으로 「DB 백업 실패」를 보낸다(같은 04:00 몫에서는 한 번만, 1시간마다 재시도). 두 웹훅이 모두 비어 있으면 로그만 남는다: `docker compose logs backup`.
- 스토리지 설정(`STORAGE_*`)이 비면 백업이 돌지 못하고 로그에 남는다.

## 지금 백업하기

```bash
docker compose exec backup python manage.py db_backup --force   # 최근 백업이 있어도 지금
docker compose exec backup python manage.py db_restore --list   # 객체 목록
```

## 복원 (빈 DB에)

`db_restore`는 `--clean` 없이 복원하므로 **빈** DB에만 들어간다(이미 테이블이 있으면 첫 충돌에서 멈춘다). 운영 DB를 덮어쓰지 않는다.

```bash
cd <Jenkins 워크스페이스>        # .env 와 compose 파일이 있는 곳
export COMPOSE_PROJECT_NAME=portfolio COMPOSE_FILE=docker-compose.prod.yml:docker-compose.oracle.yml

# 1) 빈 DB를 만들고 가장 최근 백업을 넣는다 (--key 로 특정 객체 지정 가능)
docker compose exec -T postgres createdb -U portfolio portfolio_restore
docker compose run --rm --no-deps backup python manage.py db_restore --dbname portfolio_restore

# 2) migrate 상태 확인 — 모두 [X] 여야 하고, 미적용이 있으면 migrate 로 따라잡는다
docker compose run --rm --no-deps -e POSTGRES_DB=portfolio_restore web python manage.py showmigrations | grep -c '\[ \]'
docker compose run --rm --no-deps -e POSTGRES_DB=portfolio_restore web python manage.py migrate --noinput

# 3) 데이터·헬스 확인: 임시 웹을 복원본에 붙여 본다
docker compose run -d --no-deps --name restore-check -e POSTGRES_DB=portfolio_restore -p 127.0.0.1:18192:8000 web
curl -H 'Host: <DJANGO_ALLOWED_HOSTS 첫 값>' http://127.0.0.1:18192/api/health    # {"status": "ok", "db": "ok"}
docker rm -f restore-check
```

### 서버를 잃어 새로 세울 때

1. 새 호스트에서 배포(Jenkins)로 스택을 올린다. 새 Postgres는 비어 있다(웹이 migrate까지 마친 상태).
2. 위 1)을 `POSTGRES_DB`(운영 이름, 기본 `portfolio`) 대신 **새 빈 DB**에 하고 확인한 뒤, `.env`의 `POSTGRES_DB`를 그 이름으로 바꿔 web·worker·backup을 다시 올린다. 또는 운영 DB를 `dropdb`/`createdb`로 비우고 `--dbname portfolio`로 넣는다(이때 web·worker·backup은 `docker compose stop`).
3. 미디어 파일은 버킷에 그대로 있으니 DB만 되살리면 된다.

## 운영자에게 제안

- 오브젝트 스토리지 **수명 주기 규칙**으로 `backups/` 접두어 60일 삭제를 안전망으로 걸 수 있다(작업의 30일 정리가 먼저 지우므로 겹치지 않는다).
- 첫 배포 뒤 한 번 `db_backup --force`로 객체가 생기는지, 분기마다 위 복원을 한 번 해 보기를 권한다.
