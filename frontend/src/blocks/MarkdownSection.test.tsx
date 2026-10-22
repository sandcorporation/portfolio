import { render, screen } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { documentOf, exampleBlock } from "./testing";

test("markdown 블록은 제목 수준대로 제목을 달고 본문을 마크다운으로 그린다", () => {
  render(
    <DocumentView
      document={documentOf(
        exampleBlock("intro", "markdown"),
        exampleBlock("running-cost", "markdown"),
      )}
    />,
  );

  expect(screen.getByRole("heading", { level: 2, name: "구축 견적" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 3, name: "월 운영비" })).toBeInTheDocument();
  expect(screen.getByText("사내 녹취 분석 시스템").tagName).toBe("STRONG");
  expect(screen.getByText("외부 AI 사용료: 없음").tagName).toBe("LI");
});

test("markdown 본문의 HTML은 그리지 않는다", () => {
  const { container } = render(
    <DocumentView
      document={documentOf({
        id: "raw",
        type: "markdown",
        body: 'a <img src="x" onerror="alert(1)"> b',
      })}
    />,
  );

  expect(container.querySelector("img")).toBeNull();
});
