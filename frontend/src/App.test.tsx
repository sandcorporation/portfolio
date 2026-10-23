import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { App } from "./App";
import { exampleDocument } from "./blocks/testing";
import type { HomeData } from "./home/types";

const home: HomeData = {
  tagline: "",
  stack: [],
  posts: [],
  news: [],
  company_intro: exampleDocument,
  portfolio: [
    {
      slug: "voice",
      title: "녹취 분석",
      summary: "채권추심 녹취를 분석합니다",
      cover_url: "",
      tags: ["음성", "분석"],
      period: "2025.03",
    },
  ],
  contact: { email: "hello@sandcorp.co.kr", phone: "010-1234-5678", address: "" },
};

test("홈은 셸에 심긴 프로필로 회사 소개, 연락처를 보여 준다", () => {
  render(<App path="/" data={home} />);

  expect(screen.getByRole("region", { name: "회사 소개" })).toHaveTextContent(
    "채권추심 녹취 분석 시스템 구축 제안",
  );
  expect(screen.queryByRole("region", { name: "대표 소개" })).toBeNull();
  for (const link of screen.getAllByRole("link", { name: "hello@sandcorp.co.kr" })) {
    expect(link).toHaveAttribute("href", "mailto:hello@sandcorp.co.kr");
  }
  expect(screen.getByRole("link", { name: "010-1234-5678" })).toHaveAttribute(
    "href",
    "tel:01012345678",
  );
  expect(screen.queryByText("주소")).toBeNull();
});

test("홈 데이터가 없는 경로는 준비 중 안내를 보여 준다", () => {
  render(<App path="/p/abc" data={null} />);

  expect(screen.getByRole("heading", { name: "Sandcorp" })).toBeInTheDocument();
  expect(screen.getByText("사이트를 준비하고 있습니다.")).toBeInTheDocument();
});

test("홈 포트폴리오 카드는 상세 주소로 연결되고 요약·태그·기간을 보여 준다", () => {
  render(<App path="/" data={home} />);

  const card = screen.getByRole("link", { name: /녹취 분석/ });
  expect(card).toHaveAttribute("href", "/work/voice");
  expect(card).toHaveTextContent("채권추심 녹취를 분석합니다");
  expect(card).toHaveTextContent("2025.03");
  expect(card).toHaveTextContent("음성");
});

test("공개 항목이 없으면 포트폴리오 구역을 그리지 않는다", () => {
  render(<App path="/" data={{ ...home, portfolio: [] }} />);

  expect(screen.queryByRole("region", { name: "포트폴리오" })).toBeNull();
});

test("상세는 제목과 본문 문서를 보여 주고 목록으로 돌아가는 링크를 둔다", () => {
  render(<App path="/work/voice" data={{ card: home.portfolio[0], body: exampleDocument }} />);

  expect(screen.getByRole("heading", { level: 1, name: "녹취 분석" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /포트폴리오 목록/ })).toHaveAttribute("href", "/");
  expect(screen.getByRole("article")).toHaveTextContent("채권추심 녹취 분석 시스템 구축 제안");
});

test("머리띠에 전체 방문 합계를, 포트폴리오 행에 그 사이트 숫자를 보여 준다", () => {
  const data: HomeData = {
    ...home,
    visits: { live: 3, today: 1234, total: 56789 },
    portfolio: home.portfolio.map((c) => ({ ...c, visits: { today: 12, total: 3400 } })),
  };
  render(<App path="/" data={data} />);

  const banner = document.querySelector(".masthead") as HTMLElement;
  expect(banner).toHaveTextContent("지금 3 · 오늘 1,234명 · 누적 56,789명");
  expect(banner.querySelector(".visit-dot-idle")).toBeNull();
  expect(screen.getByRole("link", { name: /녹취 분석/ })).toHaveTextContent("오늘 12 · 누적 3,400");
});

test("지금이 0이면 점을 흐리게, 숫자가 없으면 아무 자리도 만들지 않는다", () => {
  const { unmount } = render(
    <App path="/" data={{ ...home, visits: { live: 0, today: 0, total: 0 } }} />,
  );
  const banner = document.querySelector(".masthead") as HTMLElement;
  expect(banner).toHaveTextContent("지금 0 · 오늘 0명 · 누적 0명");
  expect(banner.querySelector(".visit-dot-idle")).not.toBeNull();
  unmount();

  render(<App path="/" data={{ ...home, visits: null }} />);
  expect(document.querySelector(".masthead") as HTMLElement).not.toHaveTextContent("누적");
  expect(screen.getByRole("link", { name: /녹취 분석/ })).not.toHaveTextContent("오늘");
});

test("홈 문의 섹션은 왼쪽 소개·연락처, 오른쪽 폼의 두 단이다", () => {
  const { container } = render(<App path="/" data={home} />);

  const section = container.querySelector(".inquiry-section") as HTMLElement;
  const intro = section.querySelector(".inquiry-intro") as HTMLElement;
  const body = section.querySelector(".inquiry-body") as HTMLElement;
  expect(intro.nextElementSibling).toBe(body);
  expect(within(intro).getByRole("heading", { name: "문의·제안" })).toBeInTheDocument();
  expect(within(intro).getByText("이메일")).toBeInTheDocument();
  expect(within(intro).getByRole("link", { name: "hello@sandcorp.co.kr" })).toHaveAttribute(
    "href",
    "mailto:hello@sandcorp.co.kr",
  );
  expect(within(intro).getByRole("link", { name: "GitHub" })).toHaveAttribute("href", expect.stringContaining("github.com"));
  expect(within(intro).getAllByRole("button").map((b) => b.textContent)).toEqual(["주소 복사"]);
  expect(within(body).getByRole("button", { name: "보내기" })).toBeInTheDocument();
});

test("연락 이메일이 없으면 왼쪽 단에 이메일 블록을 그리지 않는다", () => {
  const { container } = render(
    <App path="/" data={{ ...home, contact: { email: "", phone: "", address: "" } }} />,
  );

  expect(container.querySelector(".inquiry-intro .inquiry-email")).toBeNull();
  expect(container.querySelector(".inquiry-intro button")).toBeNull();
  expect(container.querySelector(".inquiry-body form")).not.toBeNull();
});

test("히어로 왼쪽 소개 문장과 문의 응답 약속 문구가 이슈 문구 그대로다", () => {
  render(<App path="/" data={home} />);

  expect(
    screen.getByText(
      "웹·모바일 서비스를 기획부터 설계·개발·배포·운영까지 한 번에 맡는 1인 개발사. 재하청 없이 대표가 직접 합니다.",
    ),
  ).toHaveClass("hero-lead");
  expect(screen.getByText("프로젝트 문의나 제안을 남겨 주시면 영업일 1일 안에 답합니다.")).toBeInTheDocument();
});

const availability = { text: "새 프로젝트 받는 중", updated: "2026.10" };

test("머리띠는 방문 지표 바로 뒤에 점·가용 상태·갱신 월을 보인다", () => {
  const visits = { live: 3, today: 12, total: 345 };
  render(<App path="/" data={{ ...home, visits, availability }} />);

  const meta = document.querySelector(".masthead-meta") as HTMLElement;
  const badge = meta.querySelector(".availability") as HTMLElement;
  expect(badge).toHaveTextContent("● 새 프로젝트 받는 중 · 갱신 2026.10");
  expect(meta.querySelector(".visit-counts")?.nextElementSibling).toBe(badge);
  expect(badge.querySelector(".availability-dot")).toHaveAttribute("aria-hidden", "true");
  expect(badge.querySelector(".availability-updated")).toHaveTextContent("갱신 2026.10");
});

test("가용 상태가 없거나 비면 아무 자리도 만들지 않고, 날짜가 없으면 갱신 표시도 없다", () => {
  const { unmount } = render(<App path="/" data={{ ...home, availability: null }} />);
  expect(document.querySelector(".availability")).toBeNull();
  unmount();

  const { unmount: second } = render(<App path="/" data={{ ...home, availability: { text: "", updated: "" } }} />);
  expect(document.querySelector(".availability")).toBeNull();
  second();

  render(<App path="/" data={{ ...home, availability: { text: "새 프로젝트 받는 중", updated: "" } }} />);
  expect(document.querySelector(".availability")).toHaveTextContent(/^● 새 프로젝트 받는 중$/);
  expect(document.querySelector(".availability-updated")).toBeNull();
});

test("목록·상세 같은 다른 공개 페이지의 머리띠에도 보인다", () => {
  const blog = { posts: [], tags: [], tag: "", page: 1, pages: 1, total: 0, availability };
  const { unmount } = render(<App path="/blog" data={blog} />);
  expect(document.querySelector(".masthead .availability")).toHaveTextContent("새 프로젝트 받는 중");
  unmount();

  render(<App path="/work/voice" data={{ card: home.portfolio[0], body: exampleDocument, service_url: "", availability }} />);
  expect(document.querySelector(".masthead .availability")).toHaveTextContent("갱신 2026.10");
});

test("좁은 화면에서는 갱신 월을 숨겨 한 줄을 지키고 새 색은 쓰지 않는다", () => {
  const css = readFileSync(resolve(__dirname, "styles.css"), "utf8");
  const narrow = css.slice(css.indexOf("@media (max-width: 767px)"));
  const block = narrow.slice(0, narrow.indexOf("/* ---- page layout ---- */"));

  expect(block).toMatch(/\.availability-updated\s*{\s*display:\s*none;/);
  expect(css).toMatch(/\.availability-dot\s*{\s*color:\s*var\(--color-accent\);/);
});
