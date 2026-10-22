import { render, screen, within } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { documentOf, exampleBlock } from "./testing";

test("table 블록은 머리글, 행, 강조 열, 단위, 각주를 보여 준다", () => {
  render(<DocumentView document={documentOf(exampleBlock("price-table", "table"))} />);

  expect(screen.getByRole("heading", { name: "견적 금액" })).toBeInTheDocument();
  expect(screen.getByText("단위: 만원")).toBeInTheDocument();
  const table = screen.getByRole("table");
  const headers = within(table).getAllByRole("columnheader");
  expect(headers.map((h) => h.textContent)).toEqual([
    "구분",
    "API형 · 참고",
    "혼합형 · 참고",
    "로컬형 · 제안",
  ]);
  expect(within(table).getAllByRole("row")).toHaveLength(7);
  const highlighted = table.querySelectorAll(".is-highlight");
  expect([...highlighted].map((cell) => cell.textContent)).toEqual([
    "로컬형 · 제안",
    "4,500",
    "450",
    "1,000",
    "5,950",
    "사내 처리 · 제안 대상",
    "음성·내용 사내 처리",
  ]);
  expect(screen.getByText("장비 예산에는 세금이 포함됩니다.")).toBeInTheDocument();
});
