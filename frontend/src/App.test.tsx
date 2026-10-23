import { render, screen } from "@testing-library/react";
import { App } from "./App";
import { exampleDocument } from "./blocks/testing";
import type { HomeData } from "./home/types";

const home: HomeData = {
  tagline: "",
  stack: [],
  posts: [],
  news: [],
  company_intro: exampleDocument,
  ceo_intro: {
    tabs: [
      {
        id: "ceo",
        title: "대표",
        blocks: [{ id: "bio", type: "markdown", title: "한상진", body: "음성 처리 개발자" }],
      },
    ],
  },
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

test("홈은 셸에 심긴 프로필로 회사 소개, 대표 소개, 연락처를 보여 준다", () => {
  render(<App path="/" data={home} />);

  expect(screen.getByRole("region", { name: "회사 소개" })).toHaveTextContent(
    "채권추심 녹취 분석 시스템 구축 제안",
  );
  expect(screen.getByRole("region", { name: "대표 소개" })).toHaveTextContent("음성 처리 개발자");
  expect(screen.getByRole("link", { name: "hello@sandcorp.co.kr" })).toHaveAttribute(
    "href",
    "mailto:hello@sandcorp.co.kr",
  );
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
