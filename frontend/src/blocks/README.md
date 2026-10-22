# blocks — 블록 렌더러

「문서 JSON → 화면」만 책임지는 모듈. 공개 페이지·포트폴리오·제안서·미리보기·인쇄가 모두 `DocumentView`를 쓴다.

## 구조

- 원본은 **백엔드 Pydantic 모델** `backend/documents/blocks.py` 하나다. 문서는 `tabs[]`, 탭은 `{id, title, blocks[]}`, 블록은 `type`으로 판별하는 유니언이다.
- `make gen`이 그 모델에서 `schema/document.schema.json`(JSON Schema)을 뽑고, 다시 거기서 `types.gen.ts`를 만든다(json-schema-to-typescript, `frontend/scripts/gen-types.mjs`). 생성물은 커밋한다. `make check`의 `gen-check`가 다시 생성했을 때 차이가 있으면 실패한다.
- 검증은 `backend/documents/validation.py`의 `validate_document`. 실패하면 `InvalidDocument.errors`에 `(path, reason)` 목록이 담긴다. 경로는 `tabs[0].blocks[3].rows[2]` 모양이다. 필드 하나로 표현할 수 없는 검사(행의 칸 수, 강조 열 범위)는 블록 클래스의 `problems()`가 맡는다.
- `registry.ts`가 블록 타입마다 렌더러와 목차 줄(`toc`)을 하나씩 묶는다. 매핑 타입이라 스키마에 있는 타입이 여기 빠지면 `tsc`가 실패한다.
- 목차는 저장하지 않는다. `toc.ts`가 렌더링할 때 블록 제목에서 계산한다(markdown은 `level`대로, kpi·table 제목은 3수준).
- 이 빌드가 모르는 블록 타입(더 새 데이터)은 건너뛰고 나머지를 그린다.
- 예시 문서 픽스처: 저장소 루트 `fixtures/documents/example-proposal.json`. 백엔드 검증 시험(`backend/tests/conftest.py`의 `example_document`)과 렌더러 시험(`testing.ts`의 `exampleDocument`)이 같은 파일을 읽는다. Docker 빌드도 `tsc`를 돌리므로 Dockerfile이 `fixtures/`를 복사한다.

## 새 블록 추가 절차

블록 하나 = 스키마 하나 + 렌더러 하나 + 시험. `video`를 예로 든다.

1. **스키마**: `backend/documents/blocks.py`에 `class VideoBlock(BlockBase)`를 더한다. `model_config = ConfigDict(title="VideoBlock")`(TS 타입 이름이 된다), `type: Literal["video"]`, 필드마다 `Field(description=...)`. 필드 사이 검사가 있으면 `problems()`를 덮어쓴다(경로는 블록 안 상대 경로, 예: `"tracks[1]"`). 맨 아래 `Block` 유니언에 넣는다.
2. **생성**: `make gen` → `schema/document.schema.json`과 `frontend/src/blocks/types.gen.ts`가 바뀐다. 손으로 고치지 않는다.
3. **렌더러**: `frontend/src/blocks/Video.tsx`에 `function Video({ block, anchor }: { block: VideoBlock; anchor: string })`. 목차에 오를 제목이 있으면 `<Heading id={anchor}>`로 단다. `registry.ts`에 `video: { Render: Video, toc: ... }`를 더한다(빠뜨리면 `tsc`가 알려 준다).
4. **픽스처**: `fixtures/documents/example-proposal.json`에 그 블록을 하나 넣는다. `DocumentView.test.tsx`의 「예시 문서는 블록 타입을 모두 쓴다」 시험이 이를 확인하고, 백엔드 시험이 유효성을 확인한다.
5. **시험**: `Video.test.tsx`에서 `documentOf(exampleBlock("…", "video"))`를 `DocumentView`로 그려 화면에 보이는 것을 확인한다. 검증 규칙이 있으면 `backend/tests/test_documents.py`에 잘못된 예와 기대 경로를 더한다.
6. `make check`.

## 스타일

`src/styles.css`의 CSS 변수만 쓴다. 디자인 토큰·브랜드는 #5가 정한다.
