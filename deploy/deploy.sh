#!/usr/bin/env bash
# Called by Jenkins on the oracle agent from the job workspace, which holds ./.env (not in the repo).
#   1) get the image: PORTFOLIO_IMAGE set (Jenkins: ghcr.io/sandcorporation/portfolio:<sha>, built off-host, #165)
#      -> docker pull only, never build on oracle; unset (make prod-local) -> build locally
#   2) wait until the database (OCI MySQL HeatWave, DB_* in .env) answers
#   3) migrate in a one-off container  4) replace web  5) wait for the health check (it
#   round-trips to the database)
# Migrations run while the old web still serves, so destructive schema changes take two deploys.
set -euo pipefail

if [ ! -f .env ]; then
  echo "워크스페이스에 .env가 없다. .env.example을 보고 만들어 두어야 한다." >&2
  exit 1
fi

# sandcorp-authkit is a private git dependency (ssh; needed only when building here). With GIT_SSH_KEY (Jenkins) the key goes into
# a throwaway ssh-agent that BuildKit forwards (`--ssh default`); without it (local) the developer's
# own agent is used. The key never enters an image layer and its path/content is not printed.
if [ -z "${PORTFOLIO_IMAGE:-}" ] && [ -n "${GIT_SSH_KEY:-}" ]; then
  eval "$(ssh-agent -s)" >/dev/null
  trap 'ssh-agent -k >/dev/null 2>&1 || true' EXIT
  ssh-add -q "$GIT_SSH_KEY"
fi

compose() { docker compose "$@"; }

wait_healthy() {
  local svc=$1
  for i in $(seq 1 60); do
    local id status
    id=$(compose ps -q "$svc")
    status=$(docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null || echo starting)
    if [ "$status" = "healthy" ]; then
      echo "$svc healthy (${i}회째)"
      return 0
    fi
    sleep 2
  done
  echo "$svc가 healthy가 되지 않았다" >&2
  compose logs --tail 80 "$svc" >&2
  return 1
}

if [ -n "${PORTFOLIO_IMAGE:-}" ]; then
  # ghcr 읽기 로그인은 oracle 호스트의 docker 설정에 있다(sandcorp-flow·news와 같다). 빌드하지 않는다.
  echo "== 이미지 pull ($PORTFOLIO_IMAGE)"
  docker pull "$PORTFOLIO_IMAGE"
  BUILD_FLAG=--no-build
else
  echo "== 이미지 빌드"
  compose build --ssh default web
  BUILD_FLAG=
fi

echo "== DB 접속 확인 (.env의 DB_*)"
# 로컬 확인(docker-compose.local.yml을 얹은 경우)에만 있는 mysql 서비스. 운영 DB는 compose 밖이다.
if compose config --services | grep -qx mysql; then
  compose up -d --wait mysql
fi
db_ok=0
for i in $(seq 1 10); do
  if compose run --rm --no-deps web python manage.py check --database default >/dev/null 2>&1; then
    echo "DB 접속됨 (${i}회째)"
    db_ok=1
    break
  fi
  sleep 3
done
if [ "$db_ok" != 1 ]; then
  echo "DB에 닿지 않는다. 마지막 시도 출력:" >&2
  compose run --rm --no-deps web python manage.py check --database default >&2 || true
  exit 1
fi

echo "== migrate"
compose run --rm --no-deps web python manage.py migrate --noinput
# DB 캐시 테이블(접근 코드·문의 요청 제한, 열람 중복 제거가 쓴다).
compose run --rm --no-deps web python manage.py createcachetable

echo "== web 교체"
# --force-recreate: 새로 빌드한 이미지라도 compose가 "Running"으로 두고 넘어가는 경우가 있었다.
compose up -d --no-deps $BUILD_FLAG --force-recreate web
wait_healthy web

echo "== PDF 렌더러·워커"
# 렌더러는 고정 태그라 설정이 같으면 그대로 둔다. 워커는 새 이미지로 바꾼다(진행 중 PDF는 끝내고 멈춤).
compose up -d --no-deps renderer
compose up -d --no-deps --remove-orphans $BUILD_FLAG --force-recreate worker

echo "== 헬스 확인"
compose exec -T web python -c "
import os, urllib.request as u
host = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost').split(',')[0].strip()
print(u.urlopen(u.Request('http://127.0.0.1:8000/api/health', headers={'Host': host}), timeout=5).read().decode())
"
compose ps
if [ -n "${PORTFOLIO_IMAGE:-}" ]; then
  # pull 한 옛 sha 이미지는 dangling 이 아니라 prune 에 안 걸린다 — 최신 3개만 남긴다(롤백은 다시 pull).
  docker image ls --format '{{.Repository}}:{{.Tag}}' "${PORTFOLIO_IMAGE%:*}" | tail -n +4 | xargs -r docker rmi >/dev/null 2>&1 || true
fi
docker image prune -f --filter label=com.docker.compose.project=portfolio >/dev/null || true
