# blocks — 블록 렌더러

「문서 JSON → 화면」만 책임지는 모듈. 공개 페이지·포트폴리오·제안서·미리보기·인쇄가 모두 `DocumentView`를 쓴다.

## 구조

- 원본은 **백엔드 Pydantic 모델** `backend/documents/blocks.py` 하나다. 문서는 `tabs[]`, 탭은 `{id, title, blocks[]}`, 블록은 `type`으로 판별하는 유니언이다.
- `make gen`이 그 모델에서 `schema/document.schema.json`(JSON Schema)을 뽑고, 다시 거기서 `types.gen.ts`를 만든다(json-schema-to-typescript, `frontend/scripts/gen-types.mjs`). 생성물은 커밋한다. `make check`의 `gen-check`가 다시 생성했을 때 차이가 있으면 실패한다.
- 검증은 `backend/documents/validation.py`의 `validate_document`. 실패하면 `InvalidDocument.errors`에 `(path, reason)` 목록이 담긴다. 경로는 `tabs[0].blocks[3].rows[2]` 모양이다. 필드 하나로 표현할 수 없는 검사(행의 칸 수, 강조 열 범위)는 블록 클래스의 `problems()`가 맡는다.
- `registry.ts`가 블록 타입마다 렌더러와 목차 줄(`toc`)을 하나씩 묶는다. 매핑 타입이라 스키마에 있는 타입이 여기 빠지면 `tsc`가 실패한다.
- 표 셀 병합: `table` 블록(과 audio-compare의 `metrics`)의 셀은 문자열이거나 `{text, colspan?, rowspan?, align?}`. 행은 **그 행에서 시작하는 셀만** 적고, 위 행의 rowspan이 차지한 칸은 비워 둔다. 격자 검증은 `blocks.py`의 `grid_problems`, 렌더는 `Table.tsx`의 `TableRows`. `highlight_column`은 병합 셀이 그 열을 덮으면 강조한다. 인쇄에서 rowspan 묶음이 페이지 경계에 걸리면 `tr` 단위로만 잘림을 막는다(브라우저가 rowspan 묶음 전체를 지키지는 못한다).
- 목차는 저장하지 않는다. `toc.ts`가 렌더링할 때 블록 제목에서 계산한다(markdown은 `level`대로, kpi·table 제목은 3수준).
- 미디어 참조: `gallery`(이미지), `audio-compare`(원음 `original` + 분리 트랙 `tracks[]`, 오디오), `video`(`media_id` 영상 + `poster_media_id` 이미지)는 `media_id`로 미디어를 가리킨다. 저장할 때 종류(이미지/오디오/영상)를 확인하고 `url`·`poster_url`은 비운다. 서버가 문서를 내보낼 때(`services/media.resolve_document`) URL을 채운다. `url`이 없는 이미지는 그리지 않고, 오디오·영상은 「더 이상 제공되지 않습니다」라고 쓴다.
- **비공개 미디어**는 제안서 문서에서만 참조할 수 있다(`stored_document(allow_private_media=True)`; 공개 페이지·포트폴리오는 거부). 발행 스냅샷에는 미디어 ID만 얼리고, 고객 페이지·미리보기가 서빙할 때 10분짜리 presigned URL을 넣는다. 페이지 데이터의 `media_endpoint`(`/p/<slug>/media`, `/preview/<token>/media`)에 `GET {endpoint}/{id}`(`?download=1`이면 저장용)로 새 URL을 받는다. 렌더러는 `media.ts`의 `MediaUrlContext`(제안서 화면이 제공)·`useMediaUrls`·`usePlayback`으로, 로드가 실패하면 새 URL을 받아 그 위치·재생 상태에서 이어 간다(같은 항목은 5초에 한 번만 다시 묻는다).
- `case-ref` 블록은 포트폴리오 항목을 **PK(`item_id`)**로 참조한다(slug는 바뀐다). 항목마다 `highlight`(제안서용 강조 문구, 요약을 대신한다)와 서버가 채우는 `case`(제목·요약·기간·태그·대표 이미지 URL)를 가진다. 같은 블록의 두 상태다: 초안에는 참조만 저장되고(`case`는 저장 때 비운다), 초안·미리보기는 서빙 때 현재 포트폴리오로 `services/case_refs.expand`가 채운다. 발행하면 `services/publishing.snapshot_document`가 같은 펼치기를 리비전에 얼린다. 렌더러는 `case`가 있는 항목만 그리고(없으면 건너뜀) 리비전은 다시 채우지 않는다. 없는 항목 참조는 저장 때 검증 오류다(숨긴 항목은 허용).
- `html` 블록은 **예외용**이다(다른 블록으로 못 쓸 때만). 저장 때 `documents/sanitize.py`(nh3 허용 목록)가 `html` 필드를 정제한다: `<script>`·이벤트 속성·`style`/`class`/`id`·`<img>`·`<iframe>`·`<svg>`·폼과 http(s)/mailto/tel 아닌 URL(`javascript:`, `data:`, 상대·`#` 링크)을 지우고, 링크에 `rel="noopener noreferrer nofollow"`를 단다. 정제는 검증(`validate_document`)에서 한 번 하고(멱등) 초안·스냅샷 모두 정제본을 쓰므로 서빙 때 다시 하지 않는다. 렌더러(`Html.tsx`)만 `dangerouslySetInnerHTML`로 그대로 꽂는다. 허용 태그를 넓히려면 `sanitize.py`와 그 시험을 같이 고친다.
- `steps` 블록은 2~8단계(`items[]`, 항목 id는 블록 안에서 유일)를 화살표로 잇는다. `layout`은 `horizontal`(기본)·`vertical`이고 가로는 600px 이하에서 CSS로 세로로 접힌다. 인쇄 모드는 5단계 이상이면 세로로 그린다. 예시 문서 픽스처는 예외용 `html`을 더는 쓰지 않는다(`Html.test.tsx`가 자체 블록으로 시험).
- `cta` 블록은 링크 버튼 1~3개(`items[]`: `label` 40자 이내, `style` primary·secondary, `target`은 `block`·`tab`·`url` 판별 유니언)다. `block`·`tab` 대상은 같은 문서 안으로 이동하고(`DocumentView`가 `nav.ts`의 `DocumentNavContext`로 탭 전환 후 스크롤을 내려 준다 — `#<블록 id>` 이동과 같은 장치), `url`은 `https:`·`mailto:`·`tel:`만 허용하며 새 창+`rel="noopener noreferrer"`로 연다. 대상이 문서에 있는지는 블록이 아니라 문서 검증(`documents/validation.py`의 `_semantic_errors`가 부르는 `BlockBase.document_problems`)이 본다 — 블록·탭을 지워 대상이 사라지면 저장이 거부된다. 인쇄 모드는 버튼 대신 「문구 + 주소」 또는 「문구 → 탭 · 블록」 한 줄로 적는다. 목차에는 싣지 않는다.
- 이 빌드가 모르는 블록 타입(더 새 데이터)은 건너뛰고 나머지를 그린다.
- 예시 문서 픽스처(가나다상사 견적 제안 원본 `examples/견적 제안 · 가나다상사.html`의 두 탭 전체를 옮긴 것; 미디어 1-3 이미지, 4-6·8-15 오디오, 7·16 영상은 시험이 만드는 가짜 행): 저장소 루트 `fixtures/documents/example-proposal.json`. 백엔드 검증 시험(`backend/tests/conftest.py`의 `example_document`)과 렌더러 시험(`testing.ts`의 `exampleDocument`)이 같은 파일을 읽는다. Docker 빌드도 `tsc`를 돌리므로 Dockerfile이 `fixtures/`를 복사한다.

## 새 블록 추가 절차

블록 하나 = 스키마 하나 + 렌더러 하나 + 시험. `video`를 예로 든다.

1. **스키마**: `backend/documents/blocks.py`에 `class VideoBlock(BlockBase)`를 더한다. `model_config = ConfigDict(title="VideoBlock")`(TS 타입 이름이 된다), `type: Literal["video"]`, 필드마다 `Field(description=...)`. 필드 사이 검사가 있으면 `problems()`를 덮어쓴다(경로는 블록 안 상대 경로, 예: `"tracks[1]"`). 맨 아래 `Block` 유니언에 넣는다.
2. **생성**: `make gen` → `schema/document.schema.json`과 `frontend/src/blocks/types.gen.ts`가 바뀐다. 손으로 고치지 않는다.
3. **렌더러**: `frontend/src/blocks/Video.tsx`에 `function Video({ block, anchor }: { block: VideoBlock; anchor: string })`. 목차에 오를 제목이 있으면 `<Heading id={anchor}>`로 단다. `registry.ts`에 `video: { Render: Video, toc: ... }`를 더한다(빠뜨리면 `tsc`가 알려 준다).
4. **픽스처**: `fixtures/documents/example-proposal.json`에 그 블록을 하나 넣는다. `DocumentView.test.tsx`의 「예시 문서는 블록 타입을 모두 쓴다」 시험이 이를 확인하고, 백엔드 시험이 유효성을 확인한다.
5. **MCP 예시**: `backend/services/blocks.py`의 `EXAMPLES`에 그 타입의 유효한 예시를 더한다(`block_schema` 도구가 돌려준다; `test_mcp.py`가 모든 타입에 예시가 있고 유효한지 확인한다).
6. **시험**: `Video.test.tsx`에서 `documentOf(exampleBlock("…", "video"))`를 `DocumentView`로 그려 화면에 보이는 것을 확인한다. 검증 규칙이 있으면 `backend/tests/test_documents.py`에 잘못된 예와 기대 경로를 더한다.
7. 화면 모양은 `src/styles.css`(`.block-<타입>`). 인쇄 모드가 레이아웃을 바꿔야 하면 `useRenderMode().print`를 읽어 `data-*` 속성으로 내리고 CSS가 그걸 따른다(`Steps.tsx` 참고). 페이지 경계에서 잘리면 안 되는 블록은 `@media print`의 `break-inside: avoid` 목록에 넣는다.
8. `make check`.

## 스타일

- 토큰은 `frontend/src/tokens.css` 하나다(색·글꼴·글자 크기·간격·모서리·폭). 라이트가 기본, 다크는 `prefers-color-scheme`만 따른다. **원시 색 값(`#fff`, `rgb()` 등)은 이 파일에만 둔다** — 컴포넌트 CSS·TSX에 쓰면 `src/tokens.test.ts`가 실패한다. 같은 시험이 본문·강조 색의 대비(4.5:1 이상)를 라이트·다크 모두 확인한다.
- 색 역할: `--color-canvas`(페이지 바탕) / `--color-paper`(카드·시트) / `--color-tint`(목차·KPI·표 머리) / `--color-line` / `--color-ink`(제목) / `--color-text`(본문) / `--color-muted`(보조) / `--color-accent`(링크·강조, 하나뿐) / `--color-accent-tint`(강조 열·경고 바탕). 간격은 `--space-1..8`(4px 단위).
- 컴포넌트 스타일은 `src/styles.css`. 새 블록은 루트에 `.block-<타입>`을 달고, 보조 글자는 `--color-muted`, 테두리는 `--color-line`, 작은 글씨는 `--text-sm`을 쓴다. 표는 반드시 `.table-scroll` 안에 둔다(마크다운 표는 `Prose`가 자동으로 감싼다).
- 글꼴은 Pretendard Variable(dynamic subset)을 npm 패키지로 **자체 호스팅**한다(CDN 의존·외부 요청 없음, 쓰는 글자 조각만 `unicode-range`로 내려받는다).
- 로고: `frontend/src/brand/Logo.tsx`(`Wordmark`, `LogoMark`)는 토큰 색을 따라 다크에서 바뀐다. 파비콘·독립 로고 파일은 `backend/core/static/core/{favicon,logo}.svg`(셸이 파비콘을 건다).
