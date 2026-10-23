import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { COPIED_MS, InquiryEmail } from "./InquiryEmail";

const EMAIL = "hello@sandcorp.co.kr";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.getSelection()?.removeAllRanges();
});

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

test("주소 복사를 누르면 이메일을 클립보드에 쓰고 「복사됨」을 1.6초 보인 뒤 원래대로 돌린다", async () => {
  vi.useFakeTimers();
  const writeText = vi.fn().mockResolvedValue(undefined);
  stubClipboard(writeText);
  render(<InquiryEmail email={EMAIL} />);

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "주소 복사" }));
  });

  expect(writeText).toHaveBeenCalledExactlyOnceWith(EMAIL);
  expect(screen.getByRole("button", { name: "복사됨" })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("복사했습니다");
  act(() => {
    vi.advanceTimersByTime(COPIED_MS - 1);
  });
  expect(screen.getByRole("button", { name: "복사됨" })).toBeInTheDocument();
  act(() => {
    vi.advanceTimersByTime(1);
  });
  expect(screen.getByRole("button", { name: "주소 복사" })).toBeInTheDocument();
  expect(COPIED_MS).toBe(1600);
});

test("클립보드가 거절하면 이메일 텍스트를 선택하고 「복사됨」은 보이지 않는다", async () => {
  const user = userEvent.setup();
  stubClipboard(vi.fn().mockRejectedValue(new Error("denied")));
  render(<InquiryEmail email={EMAIL} />);

  await user.click(screen.getByRole("button", { name: "주소 복사" }));

  expect(window.getSelection()?.toString()).toBe(EMAIL);
  expect(screen.getByRole("button", { name: "주소 복사" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "복사됨" })).toBeNull();
});

test("클립보드 API가 없는 환경에서도 같게 이메일을 선택한다", async () => {
  const user = userEvent.setup();
  Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
  render(<InquiryEmail email={EMAIL} />);

  await user.click(screen.getByRole("button", { name: "주소 복사" }));

  expect(window.getSelection()?.toString()).toBe(EMAIL);
});

test("버튼은 키보드로 닿고(Tab, Enter), mailto 링크 뒤에 온다", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();
  stubClipboard(writeText);
  render(<InquiryEmail email={EMAIL} />);

  await user.tab();
  expect(screen.getByRole("link", { name: EMAIL })).toHaveFocus();
  await user.tab();
  expect(screen.getByRole("button", { name: "주소 복사" })).toHaveFocus();
  await user.keyboard("{Enter}");

  expect(writeText).toHaveBeenCalledWith(EMAIL);
});

test("이메일이 비어 있으면 링크도 버튼도 그리지 않는다", () => {
  const { container } = render(<InquiryEmail email="" />);

  expect(container).toBeEmptyDOMElement();
});
