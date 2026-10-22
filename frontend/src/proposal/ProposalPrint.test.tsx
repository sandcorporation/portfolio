import { render, screen, within } from "@testing-library/react";
import { exampleDocument } from "../blocks/testing";
import { App } from "../App";
import { ProposalDocument } from "./ProposalDocument";
import type { ProposalData } from "./types";

const data: ProposalData = {
  preview: false,
  recipient: "홍길순 대표님께",
  title: "업무 자동화 제안",
  subtitle: "견적과 일정",
  quote_date: "2026-10-01",
  valid_until: null,
  supplier: { name: "샌드코프", email: "", phone: "", address: "" },
  document: exampleDocument,
  revision: { number: 2, doc_number: "SC-20261001-NW-001", published_at: "2026-10-01T00:00:00Z" },
  print_mode: true,
  public_url: "https://sandcorp.co.kr/p/abc123",
};

test("인쇄 모드는 탭 버튼 없이 모든 탭을 순서대로 펼친다", () => {
  render(<ProposalDocument data={data} />);

  expect(screen.queryByRole("tab")).toBeNull();
  const tabTitles = screen.getAllByRole("heading", { level: 2 }).filter((h) =>
    h.classList.contains("print-tab-title"),
  );
  expect(tabTitles.map((h) => h.textContent)).toEqual(["견적 제안", "회사소개·수행사례"]);
  expect(screen.getByRole("heading", { name: "견적 금액" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "가나다상사 소개" })).toBeInTheDocument();
});

test("표지에 문서번호와 리비전, 그다음에 목차가 온다", () => {
  const { container } = render(<ProposalDocument data={data} />);

  expect(screen.getByText("SC-20261001-NW-001")).toBeInTheDocument();
  expect(screen.getByText("2차 발행본")).toBeInTheDocument();
  const order = Array.from(container.querySelectorAll("header.proposal-cover, nav.document-toc, .print-tab"));
  expect(order.map((el) => el.tagName + "." + el.className.split(" ")[0])).toEqual([
    "HEADER.proposal-cover",
    "NAV.document-toc",
    "SECTION.print-tab",
    "SECTION.print-tab",
  ]);
});

test("목차는 탭 제목과 2단계 제목까지만 싣는다", () => {
  render(<ProposalDocument data={data} />);

  const toc = screen.getByRole("navigation", { name: "목차" });
  const items = Array.from(toc.querySelectorAll("li"));
  expect(items.some((li) => li.dataset.level === "3")).toBe(false);
  const texts = items.map((li) => li.textContent);
  expect(texts).toContain("견적 제안");
  expect(texts).toContain("구축 견적");
  expect(texts).toContain("회사소개·수행사례");
  expect(texts).not.toContain("견적 금액");
  expect(within(toc).getByRole("link", { name: "견적 제안" })).toHaveAttribute(
    "href",
    "#proposal-tab-estimate",
  );
});

test("오디오 비교와 영상은 QR 코드와 /p/<slug>#<블록 id> 링크로 바뀐다", () => {
  const { container } = render(<ProposalDocument data={data} />);

  expect(container.querySelectorAll("audio, video")).toHaveLength(0);
  const links = Array.from(container.querySelectorAll<HTMLAnchorElement>(".qr-link a")).map((a) =>
    a.getAttribute("href"),
  );
  expect(links).toContain("https://sandcorp.co.kr/p/abc123#separation");
  expect(links).toContain("https://sandcorp.co.kr/p/abc123#demo-video");
  expect(links).toHaveLength(5);
  expect(container.querySelectorAll(".qr-link svg.qr-code path")).toHaveLength(5);
});

test("오디오 비교의 변환 글과 대본은 인쇄에도 남는다", () => {
  const { container } = render(<ProposalDocument data={data} />);

  const block = container.querySelector('[data-block-id="separation"]');
  expect(block).not.toBeNull();
  expect(within(block as HTMLElement).getAllByText("변환한 글").length).toBeGreaterThan(1);
  expect(within(block as HTMLElement).getAllByText("원래 대본").length).toBeGreaterThan(1);
});

test("/print/ 경로는 마스트헤드 없이 인쇄 페이지를 그리고 준비 신호를 건다", async () => {
  // jsdom never loads images; a real browser reports them complete or fires load / error.
  Object.defineProperty(HTMLImageElement.prototype, "complete", { configurable: true, get: () => true });
  const { container } = render(<App path="/print/token" data={data} />);

  expect(container.querySelector(".masthead")).toBeNull();
  expect(container.querySelector(".print-page")).not.toBeNull();
  await vi.waitFor(() => expect(document.body.dataset.printReady).toBe("true"));
});
