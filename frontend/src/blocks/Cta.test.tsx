import { fireEvent, render, screen } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { RenderModeContext, screenMode } from "./mode";
import { exampleDocument } from "./testing";
import type { CtaBlock, Document } from "./types";

const doc: Document = {
  tabs: [
    {
      id: "one",
      title: "첫 탭",
      blocks: [
        {
          id: "go",
          type: "cta",
          items: [
            { label: "둘째 탭 표 보기", target: { kind: "block", block_id: "table" }, style: "primary" },
            { label: "둘째 탭으로", target: { kind: "tab", tab_id: "two" }, style: "secondary" },
            { label: "홈페이지", target: { kind: "url", href: "https://example.com/a" }, style: "primary" },
          ],
        } satisfies CtaBlock,
      ],
    },
    {
      id: "two",
      title: "둘째 탭",
      blocks: [{ id: "table", type: "markdown", title: "견적 표", body: "표 본문" }],
    },
  ],
};

function show(document: Document, print = false, onTabChange: ((id: string) => void) | null = null) {
  return render(
    <RenderModeContext.Provider value={{ ...screenMode, print, onTabChange }}>
      <DocumentView document={document} />
    </RenderModeContext.Provider>,
  );
}

test("url 항목은 새 창으로 열리고 rel이 붙는다", () => {
  show(doc);

  const link = screen.getByRole("link", { name: "홈페이지" });
  expect(link).toHaveAttribute("href", "https://example.com/a");
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
});

test("다른 탭의 블록 대상은 탭을 바꾸고 그 블록으로 스크롤한다", () => {
  const scroll = vi.fn();
  Element.prototype.scrollIntoView = scroll;
  const changed: string[] = [];
  show(doc, false, (id) => changed.push(id));

  fireEvent.click(screen.getByRole("button", { name: "둘째 탭 표 보기" }));

  expect(screen.getByRole("tab", { name: "둘째 탭" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("표 본문")).toBeInTheDocument();
  expect(changed).toEqual(["two"]);
  expect(scroll.mock.contexts.at(-1)).toHaveAttribute("data-block-id", "table");
});

test("탭 대상은 그 탭을 연다", () => {
  Element.prototype.scrollIntoView = vi.fn();
  show(doc);

  fireEvent.click(screen.getByRole("button", { name: "둘째 탭으로" }));

  expect(screen.getByRole("tab", { name: "둘째 탭" })).toHaveAttribute("aria-selected", "true");
});

test("인쇄 모드는 버튼 대신 링크 문구를 적는다", () => {
  const { container } = show(doc, true);

  expect(screen.queryByRole("button", { name: "둘째 탭 표 보기" })).toBeNull();
  const lines = [...container.querySelectorAll(".cta-line")].map((p) => p.textContent);
  expect(lines).toEqual([
    "둘째 탭 표 보기 → 둘째 탭 · 견적 표",
    "둘째 탭으로 → 둘째 탭",
    "홈페이지 https://example.com/a",
  ]);
});

test("가나다상사 예시의 CTA 셋이 그려진다", () => {
  show(exampleDocument);

  expect(screen.getByRole("button", { name: "음성 분리 시험 듣기 →" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "회사 소개 및 구축 사례 보기 →" })).toBeInTheDocument();
});

test("인쇄 문구는 라벨 끝의 화살표를 걷어 → 가 한 번만 나온다", () => {
  const arrowed: Document = {
    tabs: [
      {
        id: "one",
        title: "첫 탭",
        blocks: [
          {
            id: "go",
            type: "cta",
            items: [{ label: "표 보기 →", target: { kind: "tab", tab_id: "two" }, style: "primary" }],
          } satisfies CtaBlock,
        ],
      },
      { id: "two", title: "둘째 탭", blocks: [{ id: "x", type: "markdown", body: "본문" }] },
    ],
  };
  const { container } = show(arrowed, true);

  const line = container.querySelector(".cta-line");
  expect(line?.textContent).toBe("표 보기 → 둘째 탭");
});
