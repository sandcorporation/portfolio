## Agent skills

### Issue tracker

Issues live in GitHub Issues for sandcorporation/portfolio (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## 작업 흐름

- 이슈마다 워크트리 `~/workspace/portfolio-wt/<브랜치>`에서 작업하고 `origin/main`으로 PR을 연다.
- PR CI는 없다. 시험·린트·타입 검사는 로컬에서 돌린다. 통과하면 작업자가 바로 squash 병합한다(main 직접 push 금지).
- main에 병합하면 Jenkins(`sub` 호스트, `oracle` 에이전트)가 빌드·배포한다. 배포 잡과 서버 설정(env 파일, NPMplus, DNS, OCI)은 조율자가 다룬다. 작업자는 원격 호스트에 쓰지 않는다.
- 스펙은 #1, 티켓은 그 하위 이슈다.

## 명령

저장소 루트에서 `make <대상>`. 백엔드는 `backend/`(uv, Python 3.13), 프론트는 `frontend/`(pnpm).

- 시험: `make test` (= `make test-backend` + `make test-frontend`). 백엔드 시험은 Postgres를 쓴다 — `make db`가 `portfolio-dev` 프로젝트로 `127.0.0.1:15442`에 띄운다(`make test-backend`가 알아서 부른다).
- 린트: `make lint` (ruff format --check, ruff check, eslint). 고치기: `cd backend && uv run ruff format . && uv run ruff check --fix .`
- 타입: `make typecheck` (mypy strict + django-stubs, `tsc --noEmit`).
- 생성: `make gen` — 백엔드 블록 스키마(Pydantic)에서 JSON Schema와 `frontend/src/blocks/types.gen.ts`를 다시 만든다. `make gen-check`는 차이가 없는지 본다(`make check`에 포함).
- 전부: `make check`.
- 새 블록 추가 절차: `frontend/src/blocks/README.md`.
- 작업자는 이 「명령」 절을 명령이 바뀌는 티켓에서 함께 고친다.
- 로컬 실행: `make dev-frontend`(Vite, :5173)와 `make dev-backend`(Django, :8000)를 따로 띄우고 http://localhost:8000 을 연다. Django가 HTML 셸을 내리고 Vite dev 서버의 스크립트를 붙인다.
- PDF 워커(#40): 운영 compose의 `worker`가 `python manage.py pdf_worker`를 돌린다(작업 하나씩, `--once`는 하나만 처리하고 끝냄). 렌더러는 같은 compose의 `renderer`(browserless, 호스트 포트 없음)이고 `.env`의 `PDF_RENDERER_TOKEN`이 비면 PDF만 「실패」로 남는다. 로컬 개발 서버에서는 워커를 띄우지 않으면 PDF가 「대기」에 머문다.
- DB 백업(#19): 운영 compose의 `backup`이 `python manage.py db_backup`을 돈다(04:00 KST 하루 한 번, 30일 보관, 실패 시 Discord). 즉시 백업 `db_backup --force`, 복원 `db_restore --dbname <빈 DB>`. 절차는 `docs/ops/backup-restore.md`.
- 운영 compose 로컬 확인: `.env.example`을 `.env`로 복사해 값을 채우고(`DJANGO_ALLOWED_HOSTS`에 `localhost`) `COMPOSE_PROJECT_NAME=portfolio-local COMPOSE_FILE=docker-compose.prod.yml bash deploy/deploy.sh` → http://127.0.0.1:18091 . 끝나면 `make prod-local-down`.
