import { render, screen, within } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { RenderModeContext, screenMode } from "./mode";
import { documentOf, exampleBlock } from "./testing";
import type { CaseRefBlock } from "./types";

function renderCases(block: CaseRefBlock) {
  return render(<DocumentView document={documentOf(block)} />);
}

const filled = (id: number, title: string, summary: string, highlight?: string) => ({
  item_id: id,
  highlight,
  case: { slug: `s${id}`, title, summary, period: "2025.03", tags: ["웹"], cover_url: "" },
});

test("채워진 상태(스냅샷·미리보기)는 지정한 순서로 사례를 보이고 덮어쓴 문구가 요약을 대신한다", () => {
  renderCases({
    id: "c",
    type: "case-ref",
    title: "수행사례",
    items: [filled(2, "베타", "베타 요약", "닮은 사례"), filled(1, "알파", "알파 요약")],
  });

  expect(screen.getByRole("heading", { name: "수행사례" })).toBeInTheDocument();
  const cards = screen.getAllByRole("listitem").filter((li) => li.classList.contains("case-card"));
  expect(cards.map((li) => within(li).getByText(/^(알파|베타)$/).textContent)).toEqual(["베타", "알파"]);
  const [first, second] = cards as [HTMLElement, HTMLElement];
  expect(within(first).getByText("닮은 사례")).toHaveClass("case-highlight");
  expect(within(first).queryByText("베타 요약")).toBeNull();
  expect(within(second).getByText("알파 요약")).not.toHaveClass("case-highlight");
});

test("참조만 있는 항목은 그리지 않고, 모두 비면 블록 전체를 그리지 않는다", () => {
  const { container } = renderCases({
    id: "c",
    type: "case-ref",
    title: "수행사례",
    items: [{ item_id: 5 }],
  });

  expect(container.querySelector(".block-case-ref")).toBeNull();
  expect(screen.queryByRole("heading", { name: "수행사례" })).toBeNull();
});

test("예시 문서의 case-ref는 채워진 항목만 보여 준다", () => {
  render(<DocumentView document={documentOf(exampleBlock("case-refs", "case-ref"))} />);

  expect(screen.getByText("라마바 통화 분석")).toBeInTheDocument();
  expect(screen.getByText("주문·재고를 한 화면으로 옮긴 사례")).toBeInTheDocument();
  expect(screen.getByText("분석")).toBeInTheDocument();
});

test("사례 카드 썸네일은 화면에서 lazy, 인쇄(PDF)에서는 eager다", () => {
  const block: CaseRefBlock = {
    id: "c",
    type: "case-ref",
    items: [{ ...filled(1, "알파", "요약"), case: { ...filled(1, "알파", "요약").case, cover_url: "/m/a.png" } }],
  };
  const { container, unmount } = render(<DocumentView document={documentOf(block)} />);
  expect(container.querySelector("img.case-cover")).toHaveAttribute("loading", "lazy");
  unmount();
  const printed = render(
    <RenderModeContext.Provider value={{ ...screenMode, print: true }}>
      <DocumentView document={documentOf(block)} />
    </RenderModeContext.Provider>,
  );
  expect(printed.container.querySelector("img.case-cover")).toHaveAttribute("loading", "eager");
});
