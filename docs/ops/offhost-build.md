# 이미지를 oracle 밖에서 굽기 (portfolio #165)

oracle(aarch64, 4코어)은 운영 서비스 열 개 남짓이 CPU를 나눠 쓴다. 배포할 때마다 거기서 이미지를 빌드하면(전체 40~80초) 운영 서비스가 느려진다.
그래서 **이미지는 다른 노드에서 굽고 ghcr에 올리며, oracle은 받아서 교체만 한다.** 패턴의 원본은 news(AI-Trend-News `docs/ops/offhost-build.md`)이고 이 저장소는 그것을 본뜬 것이다.

## 흐름

```
main push ─▶ 이미지 빌드 ─────────────────────▶ 배포(oracle)
             macos (M4 Pro, arm64 네이티브)       docker pull ghcr.io/sandcorporation/sandcorp-portfolio:<sha>
             └ 3분 안에 실행기를 못 잡으면        DB 확인 → migrate → web·worker 교체 → 헬스 확인
               home(built-in, QEMU로 arm64)         (빌드 없음)
```

- **노드를 못 잡았을 때만** home으로 넘어간다. macos에서 빌드가 실패하면 실패로 끝낸다(다시 home으로 굽지 않는다).
- 빌드 노드는 콘솔(`== 빌드 노드: macos (...)`)과 빌드 설명(`<sha12> · 빌드 macos · oracle pull`)·디스코드 알림에 남는다.
- 이미지: `ghcr.io/sandcorporation/portfolio:<커밋 sha 40자>`, 레이블 `org.opencontainers.image.source`·`revision`. 빌드 캐시는 `portfolio-buildcache:arm64`(레지스트리, `mode=max`).
- 자격: ghcr 쓰기 `ghcr-push-token`(Secret text, codemit과 공유), 비공개 의존성용 SSH `github-farrar142`. oracle은 호스트 docker 설정에 있는 ghcr **읽기** 로그인을 쓴다(sandcorp-flow와 같다).

## 파라미터

| 이름 | 기본 | 뜻 |
|---|---|---|
| `BUILDER` | `auto` | `auto` / `macos` / `home` — 시험용으로 빌드 노드를 강제 |
| `MAC_WAIT_SECONDS` | `180` | auto에서 macos 실행기를 기다리는 시간. 넘으면 home |
| `ROLLBACK_SHA` | 빈 값 | 채우면 빌드 없이 그 커밋의 이미지로 되돌린다 |

## 이전 sha로 되돌리기

Jenkins `sandcorp-portfolio`를 「Build with Parameters」로 `ROLLBACK_SHA=<되돌릴 커밋 sha 40자>`를 넣고 돌린다. 빌드 단계는 건너뛰고 oracle이 그 sha 이미지를 pull해 같은 migrate·교체·헬스 절차를 밟는다.
- ghcr에 그 sha 이미지가 있어야 한다(정리 잡 `ghcr-prune`이 오래된 것을 지운다).
- migrate는 앞으로만 간다. 되돌리는 코드가 새 스키마를 못 읽으면 DB를 따로 되돌려야 한다(파괴적 스키마 변경은 두 번에 나눠 배포하는 규칙 그대로).

## portfolio 사정

- 이미지 하나(`portfolio-web`)를 web·worker가 같이 쓴다. 둘 다 `${PORTFOLIO_IMAGE:-portfolio-web:latest}`다. 변수가 없으면(`make prod-local`) 예전처럼 로컬에서 빌드한다. renderer(browserless)는 그대로다.
- 비공개 의존성 sandcorp-authkit 때문에 빌드 노드에서 `GIT_SSH_KEY`(자격 `github-farrar142`)를 BuildKit `--ssh default`로 넘긴다. oracle의 `deploy.sh`는 pull만 하므로 ssh-agent를 띄우지 않는다.
- 배포 단계는 oracle의 같은 잡 워크스페이스(`/var/jenkins_home/workspace/portfolio`, 운영 `.env`가 있는 곳)를 그대로 쓴다.
- oracle에서 빌드할 때 필요했던 `docker-compose.oracle.yml`의 `build.network: host`는 이제 쓰이지 않지만(로컬 빌드 때만) 둔다.

## 주의점

- Jenkins 스크립트 승인이 필요 없는 표준 단계만 쓴다. 노드 대기 시간 제한은 `parallel(failFast)` + `sleep` 감시다.
- macos 실행기는 1개이고 다른 열차와 나눠 쓴다. 대기가 3분을 넘으면 home으로 간다. home는 QEMU라 캐시가 없으면 느리다(레지스트리 캐시 `mode=max`를 두 노드가 공유).
- 병합 뒤 첫 빌드가 돌아야 `BUILDER` 등 파라미터가 잡에 등록된다.
- 빌드 노드의 `buildx`에 `docker-container` 빌더가 필요하다(스크립트가 `portfolio-images`를 만든다).
