import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HomePage } from "./HomePage";
import { exampleDocument } from "../blocks/testing";
import type { HomeData } from "./types";

const data: HomeData = {
  tagline: "",
  stack: [],
  company_intro: exampleDocument,
  ceo_intro: {
    tabs: [
      {
        id: "ceo",
        title: "대표",
        blocks: [
          { id: "bio", type: "markdown", title: "한상진", body: "음성 처리 개발자" },
          { id: "career", type: "markdown", title: "경력", body: "10년" },
          { id: "view", type: "markdown", title: "일하는 방식", body: "작게" },
        ],
      },
    ],
  },
  portfolio: [
    { slug: "voice", title: "녹취 분석", summary: "요약", cover_url: "", tags: [], period: "2025.03" },
  ],
  contact: { email: "", phone: "", address: "" },
};

const links = () =>
  within(screen.getByRole("navigation", { name: "목차" }))
    .getAllByRole("link")
    .map((l) => l.textContent);

test("홈 목차는 하나이고 섹션 제목 아래에 각 문서의 목차가 이어진다", () => {
  render(<HomePage data={data} />);

  expect(screen.getAllByRole("navigation", { name: "목차" })).toHaveLength(1);
  const titles = links();
  expect(titles.slice(0, 5)).toEqual(["회사 소개", "견적 개요", "구축 견적", "견적 금액", "월 운영비"]);
  const ceo = titles.indexOf("대표 소개");
  expect(ceo).toBeGreaterThan(4);
  expect(titles.slice(ceo)).toEqual(["대표 소개", "한상진", "경력", "일하는 방식", "포트폴리오", "문의·제안"]);
  expect(within(screen.getByRole("navigation", { name: "목차" })).getByRole("link", { name: "대표 소개" })).toHaveAttribute(
    "href",
    "#home-ceo",
  );
});

test("회사 소개의 탭을 바꾸면 페이지 목차의 그 구간이 바뀐다", async () => {
  render(<HomePage data={data} />);
  await userEvent.click(screen.getByRole("tab", { name: "회사소개·수행사례" }));

  const titles = links();
  expect(titles.slice(0, 3)).toEqual(["회사 소개", "가나다상사 소개", "라마바유통 구축 사례"]);
  expect(titles).not.toContain("견적 금액");
  expect(titles).toContain("대표 소개");
});

test("포트폴리오가 없으면 목차에도 없고 연락처가 있으면 끝에 붙는다", () => {
  render(
    <HomePage data={{ ...data, portfolio: [], contact: { email: "a@b.kr", phone: "", address: "" } }} />,
  );
  const titles = links();
  expect(titles).not.toContain("포트폴리오");
  expect(titles.slice(-2)).toEqual(["문의·제안", "연락처"]);
});
