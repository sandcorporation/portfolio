import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { exampleDocument } from "../blocks/testing";
import { ProposalDocument } from "./ProposalDocument";
import type { ProposalData } from "./types";

const data: ProposalData = {
  preview: true,
  recipient: "홍길순 대표님께",
  title: "업무 자동화 제안",
  subtitle: "견적과 일정",
  quote_date: "2026-10-01",
  valid_until: "2026-12-31",
  supplier: { name: "샌드코퍼레이션", email: "hi@sandcorp.co.kr", phone: "", address: "" },
  document: exampleDocument,
};

test("표지에 고객 호칭, 제목, 부제, 견적 기준일, 공급자를 보인다", () => {
  render(<ProposalDocument data={data} />);

  expect(screen.getByRole("heading", { level: 1, name: "업무 자동화 제안" })).toBeInTheDocument();
  expect(screen.getByText("홍길순 대표님께")).toBeInTheDocument();
  expect(screen.getByText("견적과 일정")).toBeInTheDocument();
  expect(screen.getByText("2026.10.01")).toBeInTheDocument();
  expect(screen.getByText("2026.12.31까지")).toBeInTheDocument();
  expect(screen.getByText("샌드코퍼레이션")).toBeInTheDocument();
  expect(screen.getByText("hi@sandcorp.co.kr")).toBeInTheDocument();
});

test("문서의 표지 블록은 표지와 겹치지 않게 빼고, 탭과 목차를 그린다", async () => {
  render(<ProposalDocument data={data} />);

  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(screen.getByRole("tab", { name: "견적 제안" })).toHaveAttribute("aria-selected", "true");
  const toc = screen.getByRole("navigation", { name: "목차" });
  expect(within(toc).getByRole("link", { name: "견적 금액" })).toHaveAttribute(
    "href",
    "#proposal-price-table",
  );

  await userEvent.click(screen.getByRole("tab", { name: "회사소개·수행사례" }));
  expect(screen.getByRole("heading", { name: "가나다상사 소개" })).toBeInTheDocument();
});

test("미리보기일 때만 초안 안내를 보인다", () => {
  const { rerender } = render(<ProposalDocument data={data} />);
  expect(screen.getByRole("status")).toHaveTextContent("초안 미리보기");

  rerender(<ProposalDocument data={{ ...data, preview: false }} />);
  expect(screen.queryByRole("status")).toBeNull();
});
