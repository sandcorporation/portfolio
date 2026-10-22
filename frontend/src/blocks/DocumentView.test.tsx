import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocumentView } from "./DocumentView";
import { registry } from "./registry";
import { documentOf, exampleDocument } from "./testing";
import type { Block, Document } from "./types";

test("예시 문서는 예외용 html 말고 블록 타입을 모두 쓴다", () => {
  const used = new Set(exampleDocument.tabs.flatMap((tab) => tab.blocks.map((b) => b.type)));

  // html is the exception block; Html.test.tsx covers it with its own document.
  expect([...used].sort()).toEqual(Object.keys(registry).filter((t) => t !== "html").sort());
});

test("목차는 현재 탭의 블록 제목에서 만들어지고 각 제목으로 이동한다", () => {
  render(<DocumentView document={exampleDocument} idPrefix="doc-" />);

  const toc = screen.getByRole("navigation", { name: "목차" });
  const links = within(toc).getAllByRole("link");
  expect(links.map((link) => link.textContent).slice(0, 4)).toEqual([
    "견적 개요",
    "구축 견적",
    "견적 금액",
    "월 운영비",
  ]);
  expect(links[2]).toHaveAttribute("href", "#doc-price-table");
  expect(screen.getByRole("heading", { name: "견적 금액" })).toHaveAttribute("id", "doc-price-table");
});

test("탭을 누르면 그 탭의 블록과 목차로 바뀐다", async () => {
  render(<DocumentView document={exampleDocument} />);

  expect(screen.getByRole("tab", { name: "견적 제안" })).toHaveAttribute("aria-selected", "true");
  await userEvent.click(screen.getByRole("tab", { name: "회사소개·수행사례" }));

  expect(screen.getByRole("tab", { name: "회사소개·수행사례" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(screen.getByRole("heading", { name: "가나다상사 소개" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "견적 금액" })).toBeNull();
  const toc = screen.getByRole("navigation", { name: "목차" });
  const titles = within(toc).getAllByRole("link").map((l) => l.textContent);
  expect(titles.slice(0, 3)).toEqual([
    "가나다상사 소개",
    "라마바유통 구축 사례",
    "운영자가 직접 수정하는 AI 처리 흐름",
  ]);
  expect(titles).toContain("수행사례");
});

test("탭이 하나면 탭 목록을 보이지 않는다", () => {
  render(<DocumentView document={documentOf({ id: "m", type: "markdown", body: "본문" })} />);

  expect(screen.queryByRole("tablist")).toBeNull();
  expect(screen.queryByRole("navigation", { name: "목차" })).toBeNull();
});

test("알 수 없는 블록 타입은 건너뛰고 나머지를 그린다", () => {
  const future = { id: "chart", type: "chart", series: [1, 2] } as unknown as Block;
  const document: Document = documentOf(
    { id: "before", type: "markdown", title: "앞", body: "" },
    future,
    { id: "after", type: "markdown", title: "뒤", body: "" },
  );

  render(<DocumentView document={document} />);

  expect(screen.getByRole("heading", { name: "앞" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "뒤" })).toBeInTheDocument();
  expect(within(screen.getByRole("navigation")).getAllByRole("link")).toHaveLength(2);
});

describe("#<블록 id>로 들어오면", () => {
  const scrolled: string[] = [];

  beforeEach(() => {
    scrolled.length = 0;
    Element.prototype.scrollIntoView = function (this: HTMLElement) {
      scrolled.push(this.dataset.blockId ?? "");
    };
  });

  afterEach(() => {
    window.location.hash = "";
  });

  test("그 블록이 있는 탭으로 바뀌고 그 블록으로 스크롤한다", () => {
    window.location.hash = "#demo-video";
    render(<DocumentView document={exampleDocument} />);

    expect(screen.getByRole("tab", { name: "회사소개·수행사례" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(scrolled).toEqual(["demo-video"]);
  });

  test("열려 있는 중에 주소가 바뀌어도 따라간다", async () => {
    render(<DocumentView document={exampleDocument} />);
    expect(screen.getByRole("tab", { name: "견적 제안" })).toHaveAttribute("aria-selected", "true");

    window.location.hash = "#demo-video";
    await vi.waitFor(() => expect(scrolled).toContain("demo-video"));

    expect(screen.getByRole("tab", { name: "회사소개·수행사례" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("모르는 블록 id는 무시한다", () => {
    window.location.hash = "#nothing-here";
    render(<DocumentView document={exampleDocument} />);

    expect(screen.getByRole("tab", { name: "견적 제안" })).toHaveAttribute("aria-selected", "true");
    expect(scrolled).toEqual([]);
  });
});
