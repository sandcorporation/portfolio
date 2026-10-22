import { render, screen } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { documentOf, exampleBlock } from "./testing";

test("cover 블록은 받는 사람, 제목, 부제를 보여 준다", () => {
  render(<DocumentView document={documentOf(exampleBlock("cover", "cover"))} />);

  expect(screen.getByText("홍길순 대표님께")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { level: 1, name: "채권추심 녹취 분석 시스템 구축 제안" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText("사내 분석 환경 구축을 위한 견적과 관련 수행 사례입니다."),
  ).toBeInTheDocument();
});
