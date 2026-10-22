// Acceptance for the first block set (#15): the GanadaTrade proposal, moved from the HTML sample
// into fixtures/documents/example-proposal.json, reads fully through the block renderers.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocumentView } from "./DocumentView";
import { exampleDocument } from "./testing";

test("두 탭: 견적 제안과 회사소개·수행사례", () => {
  render(<DocumentView document={exampleDocument} />);

  const tabs = within(screen.getByRole("tablist")).getAllByRole("tab");
  expect(tabs.map((tab) => tab.textContent)).toEqual(["견적 제안", "회사소개·수행사례"]);
});

test("견적 제안 탭: 목차가 절을 모두 잇고, 견적표는 로컬형 열을 강조한다", () => {
  render(<DocumentView document={exampleDocument} idPrefix="doc-" />);

  const toc = within(screen.getByRole("navigation", { name: "목차" }));
  const titles = toc.getAllByRole("link").map((link) => link.textContent);
  for (const title of [
    "견적 개요",
    "견적 금액",
    "월 운영비",
    "4. 개발비 내역",
    "7. 장비 구입 예산",
    "유사 프로젝트 비교",
    "개발사 소개",
  ]) {
    expect(titles).toContain(title);
    expect(screen.getByRole("heading", { name: title })).toHaveAttribute("id");
  }

  const price = screen.getByRole("heading", { name: "견적 금액" }).closest("section");
  if (!price) throw new Error("no price table section");
  const highlighted = [...price.querySelectorAll("thead .is-highlight, tbody .is-highlight")];
  expect(highlighted[0]).toHaveTextContent("로컬형 · 제안");
  expect(highlighted.map((cell) => cell.textContent)).toContain("5,950");
  // Row label plus the two reference plans stay plain.
  expect(price.querySelectorAll("tbody tr:first-child td:not(.is-highlight)")).toHaveLength(3);
});

test("견적 제안 탭: 사전시험 세 가지가 오디오 비교로 있고 원음과 분리 트랙을 고른다", async () => {
  render(<DocumentView document={exampleDocument} />);

  for (const title of [
    "01 · 맞장구와 말 끊기가 있는 대화",
    "02 · 같은 대화에 전화 음질과 잡음을 적용",
    "03 · 먼저 확인했던 겹침 대화",
  ]) {
    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
  }
  const groups = screen.getAllByRole("group", { name: "재생할 트랙" });
  expect(groups).toHaveLength(3);
  const group = (i: number): HTMLElement => {
    const found = groups[i];
    if (!found) throw new Error(`no track group ${i}`);
    return found;
  };
  // 02 keeps the failed run next to the fixed one.
  expect(within(group(1)).getAllByRole("button").map((b) => b.textContent)).toEqual([
    "원음 · 두 화자 혼합",
    "화자 A · 분리 결과",
    "화자 B · 분리 결과",
    "보완 전 화자 A",
    "보완 전 화자 B",
  ]);
  await userEvent.click(within(group(0)).getByRole("button", { name: "화자 B · 분리 결과" }));
  expect(within(group(0)).getByRole("button", { name: "화자 B · 분리 결과" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("회사소개·수행사례 탭: 사례 글, 화면 갤러리, 영상 둘, steps 흐름도, 수행사례 목록", async () => {
  render(<DocumentView document={exampleDocument} />);
  await userEvent.click(screen.getByRole("tab", { name: "회사소개·수행사례" }));

  expect(screen.getByRole("heading", { name: "라마바유통 구축 사례" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "사례 화면" })).toBeInTheDocument();
  expect(document.querySelectorAll("video")).toHaveLength(2);
  expect(document.querySelectorAll(".block-steps .step")).toHaveLength(3);
  expect(screen.getByRole("heading", { name: "수행사례" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "견적 금액" })).toBeNull();
});
