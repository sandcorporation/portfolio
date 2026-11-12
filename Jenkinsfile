// 운영 = production 브랜치 머리(#5). 이 잡은 production만 배포한다(잡 브랜치 지정자 */production).
//
//   main push → GitHub Actions release.yml: 검사(pr-check)와 이미지(image.yml, ubuntu-24.04-arm)를 나란히 → 둘 다 초록이면 production fast-forward
//   production push → 여기: 굽지도 검사하지도 않는다. ghcr.io/sandcorporation/portfolio:<sha>가 있는지 짧게 보고
//                     oracle에서 pull → DB 확인 → migrate → web 교체 → renderer·worker → 헬스 확인(실패하면 자동 롤백)
//
// 파이프라인은 Jenkins 공용 라이브러리 sandcorp(sandcorporation/jenkins-shared)의 sandcorpDeploy에 있다(README 「승격 브랜치에서 배포」).
// 여기에는 이 저장소가 넘기는 값만 둔다. 이 저장소 사정은 docs/ops/offhost-build.md. 파라미터:
//   ROLLBACK_SHA      비상 되돌리기: Actions가 GHCR에 게시한 sha 이미지로 배포. production은 그대로 — 정석은 main에 revert PR.
@Library('sandcorp') _

sandcorpDeploy(
  name: 'Sandcorp',
  image: 'ghcr.io/sandcorporation/portfolio',
  imageVar: 'PORTFOLIO_IMAGE',
  sourceUrl: 'https://github.com/sandcorporation/portfolio',
  deployFrom: 'production',
  imageWaitHint: 'https://github.com/sandcorporation/portfolio/actions/workflows/release.yml',
  composeProject: 'portfolio',
  composeFiles: ['docker-compose.prod.yml', 'docker-compose.oracle.yml'],
  preServices: ['mysql'],               // 로컬 확인용 compose에만 있다. 운영 DB(HeatWave)는 compose 밖
  dbCheck: 'python manage.py check --database default',
  migrate: ['python manage.py migrate --noinput', 'python manage.py createcachetable'],
  keepServices: ['renderer'],
  extraServices: ['worker'],
  healthCmd: '''python -c "import os, urllib.request as u; host = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost').split(',')[0].strip(); print(u.urlopen(u.Request('http://127.0.0.1:8000/api/health', headers={'Host': host}), timeout=5).read().decode())"''',
)
