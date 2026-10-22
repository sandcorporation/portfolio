import { render, screen } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { documentOf, exampleBlock } from "./testing";

test("html 블록은 제목과 정제된 마크업을 그린다", () => {
  const { container } = render(
    <DocumentView document={documentOf(exampleBlock("lecture-flow", "html"))} />,
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
        exampleBlock("lecture-flow", "html"),
      )}
    />,
  );

  expect(screen.getByRole("link", { name: "제작 흐름" })).toHaveAttribute("href", "#lecture-flow");
});
