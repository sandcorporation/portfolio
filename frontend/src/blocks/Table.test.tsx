import { render, screen, within } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { documentOf, exampleBlock } from "./testing";
import type { TableBlock } from "./types";

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

function tableDoc(rows: TableBlock["rows"], highlight: number | null = null) {
  return documentOf({
    id: "m",
    type: "table",
    columns: ["a", "b", "c"],
    rows,
    highlight_column: highlight,
    footnotes: [],
  });
}

test("colspan·rowspan이 td 속성으로 나오고 병합 셀은 표시가 붙는다", () => {
  render(
    <DocumentView
      document={tableDoc([
        [{ text: "A", rowspan: 2 }, "b", { text: "c", align: "right" }],
        ["e", "f"],
        [{ text: "넓음", colspan: 3 }],
      ])}
    />,
  );

  const cells = screen.getAllByRole("cell");
  expect(cells.map((c) => c.textContent)).toEqual(["A", "b", "c", "e", "f", "넓음"]);
  expect(cells[0]).toHaveAttribute("rowspan", "2");
  expect(cells[0]).toHaveAttribute("data-merged");
  expect(cells[1]).not.toHaveAttribute("data-merged");
  expect(cells[2]).toHaveAttribute("data-align", "right");
  expect(cells[5]).toHaveAttribute("colspan", "3");
});

test("강조 열은 병합 셀이 그 열을 덮으면 시작 열이 아니어도 강조된다", () => {
  render(
    <DocumentView
      document={tableDoc(
        [
          [{ text: "A", rowspan: 2 }, "b", "c"],
          ["e", "f"], // column 0 is held by A, so e sits in column 1
          [{ text: "넓음", colspan: 2 }, "z"],
        ],
        1,
      )}
    />,
  );

  const lit = [...screen.getByRole("table").querySelectorAll("td.is-highlight")].map((c) => c.textContent);
  expect(lit).toEqual(["b", "e", "넓음"]);
});
