import { render, screen, within } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { documentOf, exampleBlock } from "./testing";

test("kpi 블록은 수치마다 라벨, 값, 보조 문구 카드를 만든다", () => {
  render(<DocumentView document={documentOf(exampleBlock("summary-kpi", "kpi"))} />);

  const section = screen.getByRole("region", { name: "견적 개요" });
  const cards = within(section).getAllByRole("listitem");
  expect(cards).toHaveLength(3);
  expect(cards[0]).toHaveTextContent("로컬 총 도입 예산");
  expect(within(section).getByText("5,950만원").closest("li")).toBe(cards[0]);
  expect(cards[0]).toHaveTextContent("개발 부가세·장비 예산 포함");
});
