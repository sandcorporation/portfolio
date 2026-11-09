# 이미지는 GitHub Actions가 굽고, production 브랜치가 운영 버전 (portfolio #5) · 공용 라이브러리 (jenkins-shared)

oracle(aarch64, 4코어)은 운영 서비스 열 개 남짓이 CPU를 나눠 쓴다. 그래서 **이미지는 oracle 밖에서 굽고 ghcr에 올리며, oracle은 받아서 교체만 한다.**
2026-11-09부터(대표 지시, sandcorp-metrics에서 검증) 굽기와 검사는 GitHub Actions가, 배포만 Jenkins가 한다. **`production` 브랜치 머리가 운영 버전이다.**

배포 파이프라인은 Jenkins 공용 라이브러리 `sandcorp`(저장소 sandcorporation/jenkins-shared, `vars/sandcorpDeploy.groovy`, README 「승격 브랜치에서 배포」)에 있다.
이 저장소의 `Jenkinsfile`은 `@Library('sandcorp') _`와 `sandcorpDeploy(... deployFrom: 'production')` 호출 하나다.

## 흐름

```
PR ─▶ PR 검사(pr-check.yml) ─▶ main 병합
        └▶ release.yml (on push main)
             check    pr-check.yml(workflow_call) — PR과 같은 검사         ┐ 나란히 돈다
             image    image.yml(workflow_call) — ubuntu-24.04-arm 네이티브,  ┘ (산출물 주고받지 않음)
                      ghcr.io/sandcorporation/portfolio:<sha>
             promote  needs check·image — 둘 다 초록일 때만 scripts/ci/promote.sh ff <sha> (production fast-forward만)
                  └▶ production push(웹훅) ─▶ Jenkins sandcorp-portfolio(잡 브랜치 */production)
                       굽지도 검사하지도 않는다. ghcr에 <sha> 이미지가 있는지 짧게 보고
                       oracle: docker pull → DB 확인 → migrate → web 교체 → healthy → renderer·worker → 헬스 확인
                       헬스 실패 → 직전 성공 이미지로 자동 롤백
```

- check와 image는 나란히 돈다(promptlab #13에서 병합→배포가 50초 줄어 펼침). check가 깨지면 승격이 없어 운영은 그대로지만, 그 sha 이미지는 ghcr에 오를 수 있다 — `ROLLBACK_SHA`로 그런 sha를 고르지 않는다.
- **production은 앞으로만 간다.** ruleset이 강제 push·삭제를 막는다. 사람이 직접 push하지 않는다(승격은 release.yml의 GITHUB_TOKEN만).
- 승격은 저장소 전체에서 한 번에 하나(`concurrency: production-branch`). 옛 실행이 늦게 끝나 production이 이미 더 새 판이면 건너뛴다(실패 아님).
- GITHUB_TOKEN의 push는 다른 워크플로를 깨우지 않는다 — production push로 Actions가 다시 돌지 않고, 저장소 웹훅(Jenkins)만 깨운다.
- main push만으로는 배포하지 않는다. 검사·이미지가 실패하면 production이 그대로라 운영도 그대로다.
- 이미지: `ghcr.io/sandcorporation/portfolio:<커밋 sha 40자>`, 레이블 `org.opencontainers.image.source`·`revision`, provenance 없음(옛 Jenkins 빌드와 같아 oracle compose는 그대로). 빌드 캐시는 같은 패키지의 `:buildcache`(레지스트리, `mode=max`).
- 빌드 인자 `AUTHKIT_VIA_HTTPS=1`: sandcorp-authkit(공개 저장소 sandcorp-auth)을 키 없이 https로 받는다. 비밀이 아니다(로그·이미지 공개). 비면(비상 길·`make prod-local`) 예전처럼 `--ssh default`.
- 보안(공개 저장소): `pull_request_target` 없음, GitHub 호스팅 실행기만, 액션 SHA 고정, GITHUB_TOKEN 말고 secrets 없음. 권한은 check `contents: read`, image `packages: write`, promote `contents: write`만.
- 승격 스크립트 시험 `scripts/ci/promote_test.sh`(로컬 bare 저장소, 네트워크 없음)는 PR 검사에서 돈다.

## 비상 길: Jenkins가 oracle 밖에서 굽는다 (`BUILD_ON=jenkins`)

Actions가 못 구울 때 Jenkins 「Build with Parameters」에서 `BUILD_ON=jenkins`. 지금 production 머리를 macos(3분 안에 못 잡으면 home, QEMU)에서 `scripts/ci/check.sh`(= `make check`를 도커 안에서)로 검사한 뒤 굽고 배포한다.
- 빌드 노드는 콘솔(`== 빌드 노드: macos (...)`)과 빌드 설명·디스코드 알림에 남는다. 빌드 캐시는 `portfolio-buildcache:arm64`.
- 자격: ghcr 쓰기 `ghcr-push-token`, 비공개 의존성용 SSH `github-farrar142`(`buildSsh: true`), 디스코드 `discord-deploy-webhook`. oracle은 호스트 docker 설정에 있는 ghcr **읽기** 로그인을 쓴다.

## 파라미터

| 이름 | 기본 | 뜻 |
|---|---|---|
| `BUILD_ON` | `actions` | `actions` = Actions가 구워 승격한 production 머리의 이미지를 받아 배포 / `jenkins` = 비상 길로 굽는다 |
| `BUILDER` | `auto` | 비상 길에서 `auto` / `macos` / `home` — 빌드 노드를 강제 |
| `MAC_WAIT_SECONDS` | `180` | auto에서 macos 실행기를 기다리는 시간. 넘으면 home |
| `ROLLBACK_SHA` | 빈 값 | 비상 되돌리기: 채우면 빌드 없이 그 커밋의 이미지로 배포한다(production은 그대로) |

## 자동 롤백

web을 새 이미지로 바꾼 뒤 healthy가 안 되거나 헬스 확인이 실패하면, 직전 성공 빌드의 sha 이미지로 web·worker를 다시 바꾸고 헬스를 다시 본다. migrate는 되돌리지 않는다. 빌드는 `FAILURE`, 디스코드에는 「↩️ 자동 롤백 — <새 sha> 헬스 실패, <옛 sha>로 되돌림」. pull·DB 확인·migrate에서 멈추면 web은 아직 옛 이미지라 되돌릴 것이 없다.
같은 sha는 push가 다시 깨워도 배포하지 않는다(깨진 커밋이 브랜치 push마다 배포·롤백을 되풀이하지 않게). 다시 해 보려면 「Build Now」.

## 이전 sha로 되돌리기

production은 앞으로만 간다(강제 push 금지). production을 옛 sha로 옮기는 워크플로는 두지 않는다(조직 ruleset이 GitHub Actions를 bypass로 받지 않는다). 그래서 되돌리기도 「앞으로 가는 커밋」으로 한다.

**정석: main에 revert PR.** `git revert <나쁜 커밋>` → PR → PR 검사 초록 → 병합. release.yml이 검사 → 이미지 → 승격을 그대로 밟고 Jenkins가 그 sha를 배포한다. 운영과 main이 어긋나지 않는다.

**급할 때(검사·이미지를 기다릴 수 없을 때): Jenkins `ROLLBACK_SHA`.** `sandcorp-portfolio` 「Build with Parameters」 → `ROLLBACK_SHA=<되돌릴 커밋 sha 40자>`. 굽기·검사 없이 ghcr에 그 sha 이미지가 있는지 보고 같은 migrate·교체·헬스 절차를 밟는다.
- production은 그대로라 다음 승격(main 병합)이 다시 앞으로 간다 — 곧바로 revert PR을 넣어 main을 맞춘다.
- ghcr에 그 sha 이미지가 있어야 한다(정리 잡 `ghcr-prune`이 오래된 것을 지운다).

공통: migrate는 앞으로만 간다. 되돌리는 코드가 새 스키마를 못 읽으면 DB를 따로 되돌려야 한다(파괴적 스키마 변경은 두 번에 나눠 배포하는 규칙 그대로).

## portfolio 사정

- 이미지 하나를 web·worker가 같이 쓴다. 둘 다 `${PORTFOLIO_IMAGE:-portfolio-web:latest}`다. 변수가 없으면(`make prod-local`, 로컬 `deploy/deploy.sh`) 예전처럼 로컬에서 빌드한다. renderer(browserless)는 고정 태그라 `up -d`만 한다.
- `deploy/deploy.sh`는 이제 로컬 운영 compose 확인용이다. Jenkins는 라이브러리의 `resources/sandcorp/deploy.sh`를 같은 순서·같은 값(Jenkinsfile)으로 돌린다.
- sandcorp-authkit은 ssh git 소스로 적혀 있다. Actions는 `AUTHKIT_VIA_HTTPS=1`로 https로 받고, 비상 길은 `GIT_SSH_KEY`를 BuildKit `--ssh default`로 넘긴다(`buildSsh: true`, 검사 이미지도 같다).
- 배포 단계는 oracle의 같은 잡 워크스페이스(운영 `.env`가 있는 곳)를 그대로 쓴다.
- 검사의 시험 DB는 그 실행만의 MySQL 컨테이너·네트워크(호스트 포트 없음)라 같은 노드의 다른 작업과 겹치지 않는다.

## 주의점

- (비상 길) macos 실행기는 1개이고 다른 열차와 나눠 쓴다. 대기가 3분을 넘으면 home으로 간다. home은 QEMU라 캐시가 없으면 느리다. 검사 이미지는 노드의 네이티브 아키텍처로 굽는다.
- 병합 뒤 첫 빌드가 돌아야 파라미터가 잡에 등록된다.
