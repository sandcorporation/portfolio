import { render, screen } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { RenderModeContext, screenMode } from "./mode";
import { documentOf, exampleBlock } from "./testing";
import type { StepsBlock } from "./types";

const block = exampleBlock("lecture-flow", "steps");

function renderBlock(b: StepsBlock = block, print = false) {
  return render(
    <RenderModeContext.Provider value={{ ...screenMode, print }}>
      <DocumentView document={documentOf(b)} />
    </RenderModeContext.Provider>,
  );
}

function stepsWith(count: number, patch: Partial<StepsBlock> = {}): StepsBlock {
  const items = Array.from({ length: count }, (_, i) => ({ id: `s${i}`, title: `단계 ${i + 1}` }));
  return { ...block, items, ...patch };
}

test("steps 블록은 제목, 단계 순서, 번호 배지를 그린다", () => {
  const { container } = renderBlock();

  expect(screen.getByRole("heading", { level: 3, name: "제작 흐름" })).toBeInTheDocument();
  const steps = [...container.querySelectorAll(".block-steps ol > li")];
  expect(steps.map((li) => li.querySelector(".step-title")?.textContent)).toEqual([
    "강의 대본",
    "본인 목소리 음성",
    "강의 영상",
  ]);
  expect(steps.map((li) => li.querySelector(".step-badge")?.textContent)).toEqual(["1", "2", "3"]);
  expect(screen.getByText("대본을 쓰고 고칩니다")).toBeInTheDocument();
});

test("numbered가 꺼지면 번호 배지가 없다", () => {
  const { container } = renderBlock({ ...block, numbered: false });

  expect(container.querySelector(".step-badge")).toBeNull();
  expect(container.querySelector(".block-steps")).toHaveAttribute("data-numbered", "false");
});

test("layout이 구조에 남아 CSS가 가로·세로·좁은 폭 접힘을 고른다", () => {
  const horizontal = renderBlock({ ...block, layout: "horizontal" });
  expect(horizontal.container.querySelector(".block-steps")).toHaveAttribute(
    "data-layout",
    "horizontal",
  );
  horizontal.unmount();

  const vertical = renderBlock({ ...block, layout: "vertical" });
  expect(vertical.container.querySelector(".block-steps")).toHaveAttribute("data-layout", "vertical");
});

test("캡션을 그린다", () => {
  renderBlock({ ...block, items: [...block.items.slice(0, 2), { id: "z", title: "끝", caption: "하루" }] });

  expect(screen.getByText("하루")).toBeInTheDocument();
});

test("인쇄 모드: 가로 4개까지는 그대로, 4개 초과면 세로", () => {
  const four = renderBlock(stepsWith(4), true);
  expect(four.container.querySelector(".block-steps")).toHaveAttribute("data-layout", "horizontal");
  expect(four.container.querySelector(".block-steps")).toHaveAttribute("data-print", "true");
  four.unmount();

  const five = renderBlock(stepsWith(5), true);
  expect(five.container.querySelector(".block-steps")).toHaveAttribute("data-layout", "vertical");
  five.unmount();

  const screenFive = renderBlock(stepsWith(5), false);
  expect(screenFive.container.querySelector(".block-steps")).toHaveAttribute(
    "data-layout",
    "horizontal",
  );
});

test("steps 블록의 제목은 목차에 오른다", () => {
  render(<DocumentView document={documentOf({ id: "a", type: "markdown", title: "앞", body: "" }, block)} />);

  expect(screen.getByRole("link", { name: "제작 흐름" })).toHaveAttribute("href", "#lecture-flow");
});

test("가로 배치는 단계 수와 상관없이 한 목록에 모두 그린다 (줄바꿈은 CSS grid)", () => {
  const { container } = renderBlock(stepsWith(8, { layout: "horizontal" }));

  expect(container.querySelectorAll(".block-steps ol > li")).toHaveLength(8);
});

test("번호가 있으면 data-numbered=true, 없으면 false로 내려 CSS가 화살표를 끈다", async () => {
  const on = renderBlock({ ...block, numbered: true });
  expect(on.container.querySelector(".block-steps")).toHaveAttribute("data-numbered", "true");
  on.unmount();
  const off = renderBlock({ ...block, numbered: false });
  expect(off.container.querySelector(".block-steps")).toHaveAttribute("data-numbered", "false");

  const { readFileSync } = await import("node:fs");
  const css = readFileSync(`${process.cwd()}/src/styles.css`, "utf8");
  expect(css).toMatch(/\.block-steps\[data-numbered="false"\] \.step::after\s*\{\s*content: none !important/);
});
