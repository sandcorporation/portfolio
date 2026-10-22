import { render, screen } from "@testing-library/react";
import { App } from "../App";
import { exampleDocument } from "../blocks/testing";
import type { CodeScreenData, ExpiredScreenData, ProposalData } from "./types";

const supplier = { name: "샌드코프", email: "hi@sandcorp.co.kr", phone: "010-1234-5678", address: "" };
const path = "/p/abc123";

test("코드 입력 화면은 같은 주소로 코드와 CSRF 토큰을 보낸다", () => {
  const data: CodeScreenData = { screen: "code", error: null, csrf_token: "tok" };
  const { container } = render(<App path={path} data={data} />);

  expect(screen.getByRole("heading", { name: "제안서 열기" })).toBeInTheDocument();
  const form = screen.getByRole("form", { name: "제안서 열기" });
  expect(form).toHaveAttribute("method", "post");
  expect(form).toHaveAttribute("action", path);
  expect(screen.getByLabelText("접근 코드")).toHaveAttribute("name", "code");
  expect(container.querySelector('input[name="csrfmiddlewaretoken"]')).toHaveValue("tok");
  expect(screen.getByRole("button", { name: "열기" })).toBeInTheDocument();
  expect(screen.queryByRole("alert")).toBeNull();
  // 만료된 제안서도 같은 데이터를 받으므로, 이 화면은 만료·연락처를 알 수 없다.
  expect(screen.queryByText(/유효|만료|연락/)).toBeNull();
});

test("틀린 코드와 차단을 각각 알린다", () => {
  const { rerender } = render(
    <App path={path} data={{ screen: "code", error: "wrong", csrf_token: "t" }} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("접근 코드가 맞지 않습니다");
  expect(screen.getByLabelText("접근 코드")).toHaveAttribute("aria-invalid", "true");

  rerender(<App path={path} data={{ screen: "code", error: "blocked", csrf_token: "t" }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("잠시 막아 두었습니다");
});

test("만료 화면은 본문 없이 유효기간과 연락처를 보인다", () => {
  const data: ExpiredScreenData = { screen: "expired", valid_until: "2026-09-30", supplier };
  render(<App path={path} data={data} />);

  expect(screen.getByRole("heading", { name: "제안서 유효기간이 지났습니다" })).toBeInTheDocument();
  expect(screen.getByText(/2026\.09\.30까지 유효했습니다/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "hi@sandcorp.co.kr" })).toHaveAttribute(
    "href",
    "mailto:hi@sandcorp.co.kr",
  );
  expect(screen.getByRole("link", { name: "010-1234-5678" })).toHaveAttribute(
    "href",
    "tel:01012345678",
  );
  expect(screen.queryByRole("form")).toBeNull();
});

const body: ProposalData = {
  preview: false,
  recipient: "홍길순 대표님께",
  title: "업무 자동화 제안",
  subtitle: "",
  quote_date: "2026-10-01",
  valid_until: null,
  supplier,
  document: exampleDocument,
  revision: { number: 2, doc_number: "SC-20261022-NEXT-002", published_at: "2026-10-22T10:00:00+09:00" },
  csrf_token: "tok",
};

test("고객 본문은 문서번호와 리비전을 보이고, 잠금은 /lock 으로 보낸다", () => {
  const { container } = render(<App path={path} data={body} />);

  expect(screen.getByRole("heading", { level: 1, name: "업무 자동화 제안" })).toBeInTheDocument();
  expect(screen.getAllByText("SC-20261022-NEXT-002").length).toBeGreaterThan(0);
  expect(screen.getByText("2차 발행본")).toBeInTheDocument();
  const lock = screen.getByRole("button", { name: "잠금" });
  const form = lock.closest("form");
  expect(form).toHaveAttribute("action", `${path}/lock`);
  expect(form).toHaveAttribute("method", "post");
  expect(container.querySelector('input[name="csrfmiddlewaretoken"]')).toHaveValue("tok");
});

test("PDF가 만들어진 리비전에만 PDF 내려받기 링크가 있다", () => {
  const { unmount } = render(<App path={path} data={body} />);
  expect(screen.queryByRole("link", { name: "PDF" })).toBeNull();
  unmount();

  render(<App path={path} data={{ ...body, pdf_url: `${path}/pdf` }} />);
  expect(screen.getByRole("link", { name: "PDF" })).toHaveAttribute("href", `${path}/pdf`);
});

test("미리보기에는 잠금 버튼이 없다", () => {
  render(<App path="/preview/tok" data={{ ...body, preview: true, revision: null, csrf_token: null }} />);

  expect(screen.queryByRole("button", { name: "잠금" })).toBeNull();
  expect(screen.queryByText("문서번호")).toBeNull();
});
