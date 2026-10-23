# GitHub 프로필 README 동기화 (#59)

sandcorp.co.kr이 원본이다. 두 README는 손으로 쓰지 않고 사이트가 전체를 생성하며, Jenkins 잡이 받아 커밋한다.

| README | 엔드포인트 | 저장소 · 파일 |
|---|---|---|
| 개인 | `GET /github/readme/personal.md` | `farrar142/farrar142` · `README.md` |
| 회사 | `GET /github/readme/org.md` | `sandcorporation/.github` · `profile/README.md` |

엔드포인트는 공개(인증 없음), `text/markdown`, `Cache-Control: public, max-age=300`, `ETag`. 사이트 링크에는 `?utm_source=github&utm_medium=readme&utm_campaign=<personal|org>`가 붙는다.

## 내용은 어디서 나오나

대표가 MCP(`update_profile`, `create_portfolio`/`update_portfolio`)나 admin에서 고친다. 코드는 틀(섹션 제목·이모지·꼬리)만 갖는다.

- `tagline`, `ceo_intro` 첫 markdown 블록 제목(이름, 「대표」 뺌), `company_intro`의 markdown·table 블록
- `SiteProfile.github`: `personal_intro`(마크다운), `stack_badges`(이름 목록), `public_projects`(`{name, url, description, scope: personal|org|both}`), `contact_note`
- 「운영 중인 서비스」 표: `is_public`이고 `service_url`이 있는 포트폴리오 항목을 `sort_order`순으로. 이름은 `title`의 ` — ` 앞, 소개는 뒤(없으면 `summary`), 키워드는 `tags` 앞 4개
- 기술 스택 배지: 코드의 표(`services/github_readme.py`의 `BADGES`)에 있는 이름은 색·로고가 붙고, 없는 이름은 로고 없는 회색 배지

## 스크립트

`scripts/sync-github-readme.sh` — 두 엔드포인트를 모두 받은 뒤(하나라도 200이 아니거나 본문이 200바이트 미만이면 아무 저장소도 건드리지 않고 실패), 저장소마다 얕게 clone → 파일 교체 → 바뀐 경우에만 `chore: sync README from sandcorp.co.kr` 커밋·push.

| env | 뜻 |
|---|---|
| `README_SYNC_SSH_KEY_PERSONAL` | `farrar142/farrar142` 쓰기 deploy key의 개인키 파일 경로 |
| `README_SYNC_SSH_KEY_ORG` | `sandcorporation/.github` 쓰기 deploy key의 개인키 파일 경로 |
| `README_SYNC_BASE_URL` | 기본 `https://sandcorp.co.kr` |
| `README_SYNC_REPO_PERSONAL`, `README_SYNC_REPO_ORG` | 기본은 위 두 저장소의 SSH 주소(시험용 덮어쓰기) |

저장소마다 deploy key가 다르므로 스크립트가 저장소마다 `GIT_SSH_COMMAND`를 바꾼다.

## Jenkins 잡 만들기 (조율자)

1. 각 저장소 Settings → Deploy keys에 쓰기 권한 키를 등록한다(저장소마다 다른 키).
2. Jenkins 자격 증명(SSH Username with private key 또는 Secret file)에 두 키를 올린다. id 예: `readme-sync-personal`, `readme-sync-org`.
3. 파이프라인/프리스타일 잡 `github-readme-sync`(에이전트 `oracle`, 이 저장소 `main` 체크아웃). 자격 증명을 파일 경로 변수로 묶는다: `README_SYNC_SSH_KEY_PERSONAL`, `README_SYNC_SSH_KEY_ORG`.
4. 빌드 단계: `bash scripts/sync-github-readme.sh`
5. 주기: `H 4 * * *`(하루 한 번) + 수동 실행. 사이트 데이터를 고친 뒤 바로 반영하려면 수동으로 돌린다. 엔드포인트 캐시가 5분이니 고친 직후엔 5분 뒤에.

실패하면 잡이 빨갛게 끝나고 아무것도 커밋되지 않는다. 시험은 `backend/tests/test_sync_script.py`(로컬 bare 저장소 2개).
