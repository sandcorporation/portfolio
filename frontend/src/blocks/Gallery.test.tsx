import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocumentView } from "./DocumentView";
import { documentOf, exampleBlock } from "./testing";

function renderGallery() {
  return render(<DocumentView document={documentOf(exampleBlock("case-gallery", "gallery"))} />);
}

test("gallery 블록은 url이 있는 이미지만 썸네일로 보여 준다", () => {
  renderGallery();

  expect(screen.getByRole("heading", { name: "사례 화면" })).toBeInTheDocument();
  const thumbs = screen.getAllByRole("button", { name: /크게 보기/ });
  expect(thumbs.map((t) => t.getAttribute("aria-label"))).toEqual([
    "라마바 분석 대시보드 크게 보기",
    "녹취 검수 화면 크게 보기",
  ]);
  expect(screen.getByAltText("라마바 분석 대시보드")).toHaveAttribute(
    "src",
    "https://public.example/gallery-1.png",
  );
});

test("썸네일을 누르면 확대 뷰어가 열리고 이전·다음·Esc로 다룬다", async () => {
  const user = userEvent.setup();
  renderGallery();

  await user.click(screen.getByRole("button", { name: "라마바 분석 대시보드 크게 보기" }));
  const viewer = screen.getByRole("dialog", { name: "이미지 보기" });
  expect(within(viewer).getByRole("img")).toHaveAttribute("alt", "라마바 분석 대시보드");
  expect(viewer).toHaveTextContent("통화 분석 대시보드");
  expect(viewer).toHaveTextContent("1 / 2");

  await user.click(within(viewer).getByRole("button", { name: "다음" }));
  expect(within(viewer).getByRole("img")).toHaveAttribute("alt", "녹취 검수 화면");
  await user.click(within(viewer).getByRole("button", { name: "다음" }));
  expect(viewer).toHaveTextContent("1 / 2");

  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "라마바 분석 대시보드 크게 보기" })).toHaveFocus();
});

test("확대 뷰어는 닫기 버튼으로도 닫힌다", async () => {
  const user = userEvent.setup();
  renderGallery();

  await user.click(screen.getByRole("button", { name: "녹취 검수 화면 크게 보기" }));
  await user.click(screen.getByRole("button", { name: "닫기" }));

  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
