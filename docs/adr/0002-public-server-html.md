# 0002. 공개 페이지 본문은 Django 템플릿으로도 그리고, React가 그 위에 다시 그린다

- 상태: 채택 (2026-10-25, #109)
- 같은 결정: AI-Trend-News(Foresight)의 「서버 템플릿 + `#page-data` + React」

## 맥락

공개 네 종(홈, `/work/<slug>`, `/blog`, `/blog/<slug>`)의 HTML은 `<head>` 메타와 `#page-data` JSON만 있고 `#root`가 비어 있었다. JS를 돌리지 않는 검색 로봇·미리보기에는 h1도 본문도 링크도 없었다. 기준은 운영 이미지·배포 구성(Jenkins, `docker-compose.prod.yml`)을 크게 바꾸지 않을 것, 두 벌의 마크업이 어긋나지 않게 할 것이었다.

후보:

1. **React 서버 렌더(`renderToString`) + `hydrateRoot`.** 마크업이 한 벌이라 어긋날 일이 없다. 대신 요청마다 JS를 돌려야 한다 — 운영 `web`(python:3.13-slim, gunicorn)에 Node 런타임을 넣거나(이미지 +수십~100MB, gunicorn 워커 옆에 Node 프로세스·IPC), compose에 SSR 사이드카를 더하거나(서비스·헬스체크·배포 순서가 하나 늘고, 사이드카가 죽으면 페이지가 죽거나 빈 껍데기로 떨어지는 경로를 따로 짜야 한다), Python 안에 V8(mini-racer 등)을 넣어야 한다(arm64 휠·워커당 메모리). 하이드레이션 불일치(시각·`Intl` 날짜, `useId`, 브라우저 전용 코드)도 새로 관리해야 한다.
2. **빌드 때 미리 렌더.** 내용이 DB에서 오므로 맞지 않는다.
3. **Django 템플릿으로 의미 있는 HTML을 그리고 React가 `createRoot`로 덮어쓴다.** Foresight와 같은 방식. 이미지·compose·Jenkins가 그대로이고, 하이드레이션을 하지 않으니 하이드레이션 경고가 생길 수 없다. 대가는 마크업 두 벌.

## 결정

3을 고른다.

- `core/public_html.py`가 같은 `#page-data` 데이터로 본문을 그린다. 페이지 틀은 `core/templates/core/public/`(home·work·blog_index·blog_post, 머리띠·내비 `_top.html`, 바닥 `_footer.html`), 블록 문서는 블록 종류마다 작은 함수(`block_html`). 마크다운은 markdown-it-py(GFM 표·취소선, 원시 HTML 태그는 버림 — 앱의 `skipHtml`과 같게).
- `render_shell(body=…)`이 그 HTML을 `<div id="root">`에 넣는다. 제안서·미리보기·인쇄·admin은 `body`를 주지 않아 지금처럼 빈 `#root`다. 메트릭 스니펫 규칙은 바뀌지 않는다.
- `frontend/src/main.tsx`는 그대로 `createRoot(root).render(…)`다. React가 첫 커밋에서 `#root`의 서버 HTML을 지우고 자기 화면을 그리므로 JS가 켜진 화면은 전과 같다(전후 스크린샷 바이트 동일로 확인).
- 서버 HTML은 앱과 같은 클래스 이름을 쓴다. 그래서 JS 없이도 같은 스타일시트로 거의 같은 모양이고, JS가 늦게 오는 동안 보이는 첫 화면도 앱과 크게 다르지 않다. 서버 HTML이 하지 않는 것: 문의 폼(JS가 필요), 탭 버튼(여러 탭은 차례로 펼치고 탭 제목을 h2로), 갤러리 뷰어(이미지는 원본을 새 탭으로 여는 링크, #149), 오디오·영상 플레이어(제목·설명 글만).

## 결과

- 어긋남 방지: 시험이 지킨다. `backend/tests/test_public_html.py`가 네 종의 h1·본문·링크와, 서버 쪽이 되풀이하는 고정 문구(히어로 문장 `HERO_LEAD`, `GITHUB_URL`, 내비 라벨)가 앱의 `.tsx` 소스에도 그대로 있는지 확인한다. `frontend/src/main.test.tsx`는 서버 HTML이 든 `#root` 위에 앱이 경고 없이 그리는지 본다. 화면 문구·구조를 바꾸는 티켓은 `core/templates/core/public/`도 함께 고친다.
- 마크업이 두 벌이므로 앱만 바꾸면 서버 HTML이 낡을 수 있다. 낡아도 화면(JS 켬)은 앱이 그리므로 영향은 검색·JS 없는 독자에 한정된다.
- 운영 이미지·compose·Jenkins는 바뀌지 않는다. 백엔드 의존성에 markdown-it-py(순수 Python)가 하나 늘었다.
- 나중에 SSR이 꼭 필요해지면(예: 상호작용 많은 공개 화면) 1을 다시 본다. 그때 비용은 위 「맥락」의 1과 같다.
