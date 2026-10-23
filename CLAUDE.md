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

- 시험: `make test` (= `make test-backend` + `make test-frontend`). 백엔드 시험은 MySQL을 쓴다 — `make db`가 `mysql:26.10.0`(utf8mb4_0900_as_cs, 운영 OCI HeatWave와 같은 판·콜레이션)을 `portfolio-dev` 프로젝트로 `127.0.0.1:15442`에 띄운다(`make test-backend`가 알아서 부른다). 시험 설정은 포트 15442를 본다(운영 기본 3306). 백엔드 시험 전체는 30초 안에 끝나야 한다. MySQL에서만 보이는 성질(대소문자 구분, 첫 열람 유일, PDF 워커 둘의 SKIP LOCKED)은 `tests/test_mysql.py`.
- 린트: `make lint` (ruff format --check, ruff check, eslint). 고치기: `cd backend && uv run ruff format . && uv run ruff check --fix .`
- 타입: `make typecheck` (mypy strict + django-stubs, `tsc --noEmit`).
- 생성: `make gen` — 백엔드 블록 스키마(Pydantic)에서 JSON Schema와 `frontend/src/blocks/types.gen.ts`를 다시 만든다. `make gen-check`는 차이가 없는지 본다(`make check`에 포함).
- 전부: `make check`.
- 새 블록 추가 절차: `frontend/src/blocks/README.md`.
- GitHub 프로필 README(#59): `GET /github/readme/personal.md`·`org.md`(공개, markdown, ETag, 5분 캐시)를 `services/github_readme.py`가 사이트 데이터(`SiteProfile.github`·`PortfolioItem.service_url`·프로필 블록 문서)에서 만든다 — 문구를 코드에 두지 않고 틀(제목·이모지·꼬리)만 둔다. 블록 종류를 더하면 `render_block`에 변환을 더한다(모르는 블록은 건너뜀). 동기화는 `scripts/sync-github-readme.sh`(Jenkins, `docs/ops/github-readme-sync.md`).
- 제안서 작성 지침(#69): MCP `proposal_guide`(읽기 전용, 입력 없음)가 `{guide, skeleton}`을 준다 — 지침 본문은 `backend/mcpserver/proposal_guide.md`(일반 문법만, 예시 fixture의 고객 값 금지), 탭별 권장 블록 순서는 `tools_proposals.py::PROPOSAL_SKELETON`. INSTRUCTIONS·`whoami`·작성 도구 설명이 먼저 읽으라고 안내한다. 지침에 백틱으로 적은 이름은 도구·블록 종류·블록 필드여야 한다(`tests/test_mcp.py`가 확인).
- 작업자는 이 「명령」 절을 명령이 바뀌는 티켓에서 함께 고친다.
- 로컬 실행: `make dev-frontend`(Vite, :5173)와 `make dev-backend`(Django, :8000)를 따로 띄우고 http://localhost:8000 을 연다. Django가 HTML 셸을 내리고 Vite dev 서버의 스크립트를 붙인다.
- PDF 워커(#40): 운영 compose의 `worker`가 `python manage.py pdf_worker`를 돌린다(작업 하나씩, `--once`는 하나만 처리하고 끝냄). 렌더러는 같은 compose의 `renderer`(browserless, 호스트 포트 없음)이고 `.env`의 `PDF_RENDERER_TOKEN`이 비면 PDF만 「실패」로 남는다. 로컬 개발 서버에서는 워커를 띄우지 않으면 PDF가 「대기」에 머문다.
- DB(#63): 운영 DB는 compose 밖의 OCI MySQL HeatWave(사설 IP)이고 web·worker·backup이 `.env`의 `DB_HOST`·`DB_PORT`·`DB_NAME`·`DB_USER`·`DB_PASSWORD`로 붙는다. 드라이버는 mysqlclient(이미지 빌드 단계에서 컴파일). 트랜잭션 격리는 Django 기본 READ COMMITTED를 바꾸지 않는다. 결정은 `docs/adr/0001-mysql-heatwave.md`, Postgres에서 옮기는 절차는 `docs/ops/db-migration.md`.
- DB 백업(#19): 운영 compose의 `backup`이 `python manage.py db_backup`을 돈다(04:00 KST 하루 한 번, `mysqldump` gzip → `backups/…/portfolio-<UTC>.sql.gz`, 30일 보관, 실패 시 Discord). 즉시 백업 `db_backup --force`, 복원 `db_restore --dbname <빈 DB>`(덤프에 DROP TABLE이 없어 빈 DB에만 들어간다, Postgres 시절 `.dump`는 거절). 절차는 `docs/ops/backup-restore.md`.
- 운영 compose 로컬 확인: `.env.example`을 `.env`로 복사해 값을 채우고(`DJANGO_ALLOWED_HOSTS`에 `localhost`) `COMPOSE_PROJECT_NAME=portfolio-local COMPOSE_FILE=docker-compose.prod.yml:docker-compose.local.yml bash deploy/deploy.sh` → http://127.0.0.1:18091 (DB는 `docker-compose.local.yml`의 로컬 MySQL이 `.env`의 `DB_*`를 덮는다; `make prod-local`은 migrate 없이 띄우기만). 끝나면 `make prod-local-down`.
- 접근 코드(#67): 발행(첫 발행만)·재발급 때 `access_code`를 직접 정할 수 있다(비우면 자동 8자). 규칙은 `services/publishing.py::validate_access_code` — 4~32자(앞뒤 공백 제거·NFC 정규화 뒤), 글자(한글 가능)·숫자·하이픈·밑줄·공백만, 같은 문자 반복·연속(1234/abcd)·흔한 값(`COMMON_ACCESS_CODES`)·제안서 slug·고객 코드는 `InvalidAccessCode`(Rejected 계열, 메시지에 코드 미포함). `code_matches`는 입력 그대로(공백만 제거)를 해시 비교하고, 자동 코드는 대소문자·공백·하이픈을 느슨하게 받는다. 이미 코드가 있는 제안서를 발행하며 코드를 주면 Conflict. MCP `publish`·`reissue_access_code`의 선택 입력, admin 액션 「발행 (접근 코드 직접 정하기)」·「접근 코드 재발급 (직접 정하기…)」(중간 입력 화면 `proposal_choose_codes.html`). 평문은 어디에도 남기지 않는다. 용어집 파일은 이 저장소에 없다.
