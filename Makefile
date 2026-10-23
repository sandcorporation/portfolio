# 한 줄 명령 모음. 자세한 것은 CLAUDE.md 「명령」 절.
.PHONY: gen gen-check db test test-backend test-frontend lint typecheck check dev-backend dev-frontend prod-local prod-local-down

db:  ## 로컬 시험·개발용 MySQL 26.10 (127.0.0.1:15442, 프로젝트 portfolio-dev, utf8mb4_0900_as_cs)
	docker compose up -d --wait db

test: test-backend test-frontend

test-backend: db
	cd backend && uv run pytest

test-frontend:
	cd frontend && pnpm test

lint:
	cd backend && uv run ruff format --check . && uv run ruff check .
	cd frontend && pnpm lint

typecheck:
	cd backend && uv run mypy .
	cd frontend && pnpm typecheck

gen:  ## 블록 스키마(Pydantic) → schema/document.schema.json → frontend/src/blocks/types.gen.ts
	cd backend && uv run python -m documents.schema_export
	cd frontend && pnpm gen:types

gen-check:  ## 생성물이 Pydantic 모델과 같은지(다르면 make gen 후 커밋)
	cd backend && uv run python -m documents.schema_export --check
	cd frontend && pnpm gen:types --check

check: gen-check lint typecheck test

dev-backend: db  ## http://localhost:8000 (프론트는 dev-frontend로 따로 띄운다)
	cd backend && DB_PORT=15442 DJANGO_DEBUG=1 VITE_DEV_SERVER_URL=http://localhost:5173 uv run python manage.py migrate --noinput
	cd backend && DB_PORT=15442 DJANGO_DEBUG=1 VITE_DEV_SERVER_URL=http://localhost:5173 uv run python manage.py runserver 8000

dev-frontend:
	cd frontend && pnpm dev

# 운영 compose를 로컬에서 띄워 본다(.env 필요: cp .env.example .env 후 값 채우기, ALLOWED_HOSTS에 localhost 포함).
# DB는 운영의 HeatWave 대신 docker-compose.local.yml의 MySQL 컨테이너다(.env의 DB_*를 덮는다).
PROD_LOCAL = docker compose -p portfolio-local -f docker-compose.prod.yml -f docker-compose.local.yml

prod-local:
	$(PROD_LOCAL) up -d --build --wait

prod-local-down:
	$(PROD_LOCAL) down -v
