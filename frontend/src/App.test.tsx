import { render, screen } from "@testing-library/react";
import { App } from "./App";
import { exampleDocument } from "./blocks/testing";
import type { HomeData } from "./home/types";

const home: HomeData = {
  tagline: "",
  stack: [],
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
