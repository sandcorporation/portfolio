import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { InquiryForm } from "./InquiryForm";

afterEach(() => vi.unstubAllGlobals());

async function fillAndSend() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("이름"), "김대표");
  await user.type(screen.getByLabelText("연락처"), "a@b.kr");
  await user.type(screen.getByLabelText("내용"), "견적 부탁드립니다");
  await user.click(screen.getByRole("button", { name: "보내기" }));
}

test("보내면 JSON으로 POST하고 접수 확인을 보여 준다", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201 });
  vi.stubGlobal("fetch", fetchMock);
  render(<InquiryForm />);

  await fillAndSend();

  expect(await screen.findByRole("status")).toHaveTextContent("접수되었습니다");
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(url).toBe("/api/inquiries");
  expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
  expect(JSON.parse(init.body as string)).toMatchObject({
    name: "김대표",
    contact: "a@b.kr",
    message: "견적 부탁드립니다",
    kind: "신규 개발",
    website: "",
  });
});

test("요청 제한에 걸리면 안내를 보여 주고 입력은 남긴다", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 429 }));
  render(<InquiryForm />);

  await fillAndSend();

  expect(await screen.findByRole("alert")).toHaveTextContent("잠시 후 다시");
  expect(screen.getByLabelText("이름")).toHaveValue("김대표");
});

test("구분은 신규 개발 · 유지보수 · 제안 · 기타 순이고 기본은 신규 개발이다", () => {
  render(<InquiryForm />);
  const select = screen.getByLabelText("구분");
  expect(Array.from(select.querySelectorAll("option")).map((o) => o.value)).toEqual([
    "신규 개발",
    "유지보수",
    "제안",
    "기타",
  ]);
  expect(select).toHaveValue("신규 개발");
});

const OFFERINGS = [
  { slug: "mcp-integration", name: "사내 MCP", inquiry_kind: "MCP 연동", summary: "s" },
  { slug: "claude-code-automation", name: "Claude Code", inquiry_kind: "Claude Code 자동화", summary: "s" },
];

test("상품이 있으면 구분에 이름으로 끼고 질의 값의 slug로 미리 고른다", () => {
  window.history.pushState({}, "", "/?inquiry=claude-code-automation");
  render(<InquiryForm offerings={OFFERINGS} />);
  const select = screen.getByLabelText("구분");
  expect(Array.from(select.querySelectorAll("option")).map((o) => o.value)).toEqual([
    "신규 개발",
    "유지보수",
    "MCP 연동",
    "Claude Code 자동화",
    "제안",
    "기타",
  ]);
  expect(select).toHaveValue("Claude Code 자동화");
  window.history.pushState({}, "", "/");
});

test("알 수 없는 질의 값은 기본값을 쓴다", () => {
  window.history.pushState({}, "", "/?inquiry=nope");
  render(<InquiryForm offerings={OFFERINGS} />);
  expect(screen.getByLabelText("구분")).toHaveValue("신규 개발");
  window.history.pushState({}, "", "/");
});
