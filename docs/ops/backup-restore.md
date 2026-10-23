# DB 백업과 복원 (#19)

## 어떻게 도는가

- 운영 compose의 `backup` 서비스(웹과 같은 이미지, MariaDB의 `mysqldump`/`mysql` 클라이언트 포함)가 `python manage.py db_backup`을 돈다. 5분마다 「가장 최근 04:00 KST 이후 백업이 있는가」를 버킷 목록으로 보고, 없으면 하나 만든다. 컨테이너가 재시작돼도 하루 두 번 돌지 않고, 쉬었다 켜지면 빠진 몫을 바로 채운다.
- 객체: 비공개 버킷(`STORAGE_PRIVATE_BUCKET`)의 `backups/YYYY/MM/DD/portfolio-<UTC시각>.sql.gz` (`mysqldump --single-transaction`을 gzip, DROP TABLE·CREATE DATABASE 없음). 날짜는 UTC다.
- Postgres 시절(#63 이전) 백업은 `….dump`(`pg_dump -Fc`)다. 일정 판단과 30일 정리에는 그대로 들어가지만 `db_restore`는 거절한다(MySQL에 넣을 수 없다). 옛 Postgres로 되돌려야 할 일이 있으면 `pg_restore`를 직접 쓴다.
- 업로드 뒤 30일(UTC 기준)보다 오래된 `backups/` 객체를 지운다. `backups/` 밖은 건드리지 않는다.
- 실패(덤프·업로드·정리)하면 운영 경보 웹훅(`DISCORD_ALERTS_WEBHOOK_URL`, 비면 `DISCORD_WEBHOOK_URL`)으로 「DB 백업 실패」를 보낸다(같은 04:00 몫에서는 한 번만, 1시간마다 재시도). 두 웹훅이 모두 비어 있으면 로그만 남는다: `docker compose logs backup`.
- 스토리지 설정(`STORAGE_*`)이 비면 백업이 돌지 못하고 로그에 남는다.

## 지금 백업하기

```bash
docker compose exec backup python manage.py db_backup --force   # 최근 백업이 있어도 지금
docker compose exec backup python manage.py db_restore --list   # 객체 목록
```

## 복원 (빈 DB에)

덤프에 `DROP TABLE`이 없으므로 `db_restore`는 **빈** DB에만 들어간다(이미 테이블이 있으면 첫 `CREATE TABLE`에서 멈춘다). 운영 DB를 덮어쓰지 않는다. 빈 DB는 HeatWave 관리 계정으로 만든다(서비스 계정은 자기 DB에만 권한이 있다).

```bash
cd <Jenkins 워크스페이스>        # .env 와 compose 파일이 있는 곳
export COMPOSE_PROJECT_NAME=portfolio COMPOSE_FILE=docker-compose.prod.yml:docker-compose.oracle.yml

# 0) HeatWave 관리 계정으로 빈 DB를 만들고 서비스 계정에 권한을 준다
#    CREATE DATABASE portfolio_restore CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs;
#    GRANT ALL ON portfolio_restore.* TO '<DB_USER>'@'%';

# 1) 가장 최근 백업을 넣는다 (--key 로 특정 객체 지정 가능)
docker compose run --rm --no-deps backup python manage.py db_restore --dbname portfolio_restore

# 2) migrate 상태 확인 — 모두 [X] 여야 하고, 미적용이 있으면 migrate 로 따라잡는다
docker compose run --rm --no-deps -e DB_NAME=portfolio_restore web python manage.py showmigrations | grep -c '\[ \]'
docker compose run --rm --no-deps -e DB_NAME=portfolio_restore web python manage.py migrate --noinput

# 3) 데이터·헬스 확인: 임시 웹을 복원본에 붙여 본다
docker compose run -d --no-deps --name restore-check -e DB_NAME=portfolio_restore -p 127.0.0.1:18192:8000 web
curl -H 'Host: <DJANGO_ALLOWED_HOSTS 첫 값>' http://127.0.0.1:18192/api/health    # {"status": "ok", "db": "ok"}
docker rm -f restore-check
```

### 서버를 잃어 새로 세울 때

1. DB는 HeatWave에 그대로 있으므로 새 호스트에서 배포(Jenkins)로 스택만 올리면 된다(`.env`의 `DB_*`를 옮긴다).
2. DB까지 잃었으면 새 HeatWave 인스턴스(또는 새 빈 DB)에 위 0)~1)을 하고 확인한 뒤, `.env`의 `DB_NAME`·`DB_HOST`를 그쪽으로 바꿔 web·worker·backup을 다시 올린다.
3. 미디어 파일은 버킷에 그대로 있으니 DB만 되살리면 된다.

## 운영자에게 제안

- 오브젝트 스토리지 **수명 주기 규칙**으로 `backups/` 접두어 60일 삭제를 안전망으로 걸 수 있다(작업의 30일 정리가 먼저 지우므로 겹치지 않는다). 운영 버킷 `portfolio-prod-private`에는 60일 규칙이 걸려 있다.
- HeatWave 자체 자동 백업(인스턴스 스냅숏)은 이 덤프와 별개다. 덤프는 인스턴스를 잃어도 버킷에 남는 사본이다.
- 첫 배포 뒤 한 번 `db_backup --force`로 객체가 생기는지, 분기마다 위 복원을 한 번 해 보기를 권한다.
