import { render, screen } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { documentOf } from "./testing";
import type { HtmlBlock } from "./types";

// html is the exception block, so the example proposal no longer uses it; it has its own.
const flow: HtmlBlock = {
  id: "lecture-flow",
  type: "html",
  title: "제작 흐름",
  level: 3,
  html: "<ol><li><strong>강의 대본</strong></li><li><strong>본인 목소리 음성</strong></li><li><strong>강의 영상</strong></li></ol>",
};

test("html 블록은 제목과 정제된 마크업을 그린다", () => {
  const { container } = render(
    <DocumentView document={documentOf(flow)} />,
  );

  expect(screen.getByRole("heading", { level: 3, name: "제작 흐름" })).toBeInTheDocument();
  const steps = container.querySelectorAll(".block-html ol > li > strong");
  expect([...steps].map((li) => li.textContent)).toEqual([
    "강의 대본",
    "본인 목소리 음성",
    "강의 영상",
  ]);
  expect(container.querySelector("script")).toBeNull();
});

test("html 블록의 제목은 목차에 오른다", () => {
  render(
    <DocumentView
      document={documentOf(
        { id: "a", type: "markdown", title: "앞", body: "" },
        flow,
      )}
    />,
  );

  expect(screen.getByRole("link", { name: "제작 흐름" })).toHaveAttribute("href", "#lecture-flow");
});
