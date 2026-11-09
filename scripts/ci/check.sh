#!/usr/bin/env bash
# 배포 전 검사: `make check`와 같은 것(gen-check·lint·typecheck·시험·운영 프론트 빌드)을 도커 안에서 돌린다.
# Jenkins `sandcorp-portfolio`(jenkins-shared 라이브러리 sandcorpDeploy의 「검사」)가 빌드 노드에서 이미지를 굽기 전에 부르고,
# 실패하면 이미지를 굽지도 배포하지도 않는다. PR 검사는 GitHub Actions(.github/workflows/pr-check.yml)가 같은 단계를 돌린다. 노드에 uv·pnpm이 없어도 되고, 로컬에서도 그대로 돈다.
#
#   bash scripts/ci/check.sh
#
# 시험 DB는 이 실행만의 MySQL 컨테이너(mysql:26.10.0, 같은 콜레이션)를 이 실행만의 네트워크에 띄운다 — 호스트 포트를
# 열지 않아 다른 작업(make db의 15442 등)과 겹치지 않는다. 끝나면 컨테이너·네트워크·검사 이미지 태그를 지운다.
# 비공개 의존성(sandcorp-authkit)은 BuildKit ssh로 받는다: GIT_SSH_KEY(Jenkins)가 있으면 임시 ssh-agent, 없으면 내 agent.
set -euo pipefail
cd "$(dirname "$0")/../.."

run_id="portfolio-check-$(date +%s)-$$"
image="portfolio-check:$run_id"
net="$run_id"
db="$run_id-db"

cleanup() {
  docker rm -f "$db" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
  docker image rm "$image" >/dev/null 2>&1 || true
  if [ -n "${SSH_AGENT_PID:-}" ]; then ssh-agent -k >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

if [ -n "${GIT_SSH_KEY:-}" ]; then
  eval "$(ssh-agent -s)" >/dev/null
  ssh-add "$GIT_SSH_KEY" 2>/dev/null
fi

echo "== 검사 이미지"
DOCKER_BUILDKIT=1 docker build --ssh default -f scripts/ci/check.Dockerfile -t "$image" .

echo "== 시험 DB (mysql:26.10.0, 네트워크 $net)"
docker network create "$net" >/dev/null
docker run -d --name "$db" --network "$net" --network-alias db \
  -e MYSQL_DATABASE=portfolio -e MYSQL_USER=portfolio -e MYSQL_PASSWORD=portfolio -e MYSQL_ROOT_PASSWORD=portfolio-root \
  mysql:26.10.0 \
  --character-set-server=utf8mb4 --collation-server=utf8mb4_0900_as_cs \
  --skip-log-bin --innodb-flush-log-at-trx-commit=2 --innodb-doublewrite=OFF >/dev/null
ready=0
for _ in $(seq 1 90); do
  # root 로 붙는 것만으로는 초기화 중일 수 있다 — 앱 사용자로 portfolio DB 에 붙어야 준비된 것이다.
  if docker exec "$db" mysql -uportfolio -pportfolio -h127.0.0.1 -e 'SELECT 1' portfolio >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [ "$ready" != 1 ]; then
  echo "시험 DB가 뜨지 않았다" >&2
  docker logs --tail 40 "$db" >&2 || true
  exit 1
fi
# pytest-django 가 시험 DB(test_portfolio)를 만들고 지운다(docker-compose.yml 의 grant-test-db 와 같다).
docker exec "$db" mysql -uroot -pportfolio-root -e 'GRANT ALL PRIVILEGES ON `test\_portfolio`.* TO '"'portfolio'@'%'"';' 2>/dev/null

echo "== make check (gen-check · lint · typecheck · test · build-frontend)"
# make test-backend 는 make db(docker compose)를 부르므로 컨테이너 안에서는 pytest 를 바로 부른다.
docker run --rm --network "$net" -e DB_HOST=db -e DB_PORT=3306 \
  -e PORTFOLIO_TEST_CPU_LIMIT="${PORTFOLIO_TEST_CPU_LIMIT:-1.0}" "$image" \
  sh -c 'make gen-check lint typecheck test-frontend build-frontend && cd backend && uv run pytest -q'
echo "== 검사 통과"
