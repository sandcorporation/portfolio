import { render, screen, within } from "@testing-library/react";
import { App } from "../App";
import { exampleDocument } from "../blocks/testing";
import type { HomeData } from "../home/types";
import type { Offering, ServiceData } from "./types";

const offering = (extra: Partial<Offering> = {}): Offering => ({
  slug: "mcp-integration",
  name: "사내 MCP 연동",
  summary: "한 줄 소개",
  lead: "리드 문장",
  service_type: "MCP 서버 구축",
  audience: ["대상 하나", "대상 둘"],
  deliverables: [{ title: "설계", text: "도구로 나눕니다." }],
  steps: ["상담", "범위 정의", "주 단위 시연", "납품", "운영 지원"].map((title) => ({ title, text: `${title} 설명` })),
  cases: [
    { title: "인가 서버 글", href: "/blog/auth", kind: "기록", note: "일주일 동안 만들었습니다." },
    { title: "Flow", href: "/work/flow", kind: "포트폴리오", note: "흐름을 고칩니다." },
    { title: "체험", href: "https://flow.sandcorp.co.kr/", kind: "포트폴리오", note: "다른 사이트입니다." },
  ],
  contact: "적어 보내 주세요.",
  ...extra,
});

const page = (): ServiceData => ({ offering: offering() });

test("미리보기 주소(/preview/services/…)도 서비스 화면을 그린다", () => {
  render(<App path="/preview/services/token" data={page()} />);

  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("사내 MCP 연동");
  expect(screen.queryByText("사이트를 준비하고 있습니다")).toBeNull();
});

test("서비스 화면은 제목·리드 → 대상 → 할 일 → 진행 방식 → 사례 → 견적 문의 순으로 보여 준다", () => {
  render(<App path="/services/mcp-integration" data={page()} />);

  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("사내 MCP 연동");
  expect(screen.getByText("리드 문장")).toBeInTheDocument();
  const titles = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
  expect(titles).toEqual(["이런 분께 맞습니다", "해 드리는 일", "진행 방식", "실제 사례", "문의"]);
  const steps = within(screen.getByRole("region", { name: "진행 방식" })).getAllByRole("listitem");
  expect(steps.map((li) => li.querySelector("strong")?.textContent)).toEqual([
    "상담",
    "범위 정의",
    "주 단위 시연",
    "납품",
    "운영 지원",
  ]);
  const cases = within(screen.getByRole("region", { name: "실제 사례" })).getAllByRole("link");
  expect(cases.map((a) => a.getAttribute("href"))).toEqual(["/blog/auth", "/work/flow", "https://flow.sandcorp.co.kr/"]);
  expect(cases[0]).not.toHaveAttribute("target");
  expect(cases[2]).toHaveAttribute("target", "_blank"); // another site: a new tab
  expect(cases[2]).toHaveAttribute("rel", "noopener noreferrer");
  const quote = screen.getByRole("link", { name: "견적 문의 →" });
  expect(quote).toHaveAttribute("href", `/?inquiry=${offering().slug}#home-inquiry`);
  expect(quote).toHaveAttribute("data-style", "primary");
  expect(document.querySelectorAll('[data-style="primary"]')).toHaveLength(1);
  const nav = within(screen.getByRole("navigation", { name: "사이트" }));
  expect(nav.getByRole("link", { name: "서비스" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "← 서비스" })).toHaveAttribute("href", "/#home-services");
});

const home = (extra: Partial<HomeData> = {}): HomeData => ({
  tagline: "",
  stack: [],
  company_intro: exampleDocument,
  portfolio: [],
  posts: [],
  news: [],
  contact: { email: "", phone: "", address: "" },
  ...extra,
});

test("홈의 서비스 섹션은 회사 소개 바로 뒤에 두 페이지로 가는 행을 둔다", () => {
  render(
    <App
      path="/"
      data={home({
        services: [
          { slug: "rag-chatbot", name: "RAG 상담 챗봇 구축", inquiry_kind: "RAG 상담 챗봇", summary: "영", href: "/?inquiry=rag-chatbot#home-inquiry" },
          { slug: "mcp-integration", name: "사내 MCP 연동", inquiry_kind: "MCP 연동", summary: "하나", href: "/services/mcp-integration" },
          { slug: "claude-code-automation", name: "개발 자동화", inquiry_kind: "Claude Code 자동화", summary: "둘", href: "/services/claude-code-automation" },
        ],
      })}
    />,
  );

  const section = screen.getByRole("region", { name: "외주로 맡는 일" });
  expect(section).toHaveTextContent("02 — Services");
  expect(within(section).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual([
    "/?inquiry=rag-chatbot#home-inquiry",
    "/services/mcp-integration",
    "/services/claude-code-automation",
  ]);
  expect(screen.getByText(/Contact/)).toHaveTextContent("03 — Contact");
  const row = document.querySelector(".link-row") as HTMLElement;
  expect(within(row).getByText("서비스 →")).toHaveAttribute("href", "#home-services");
});

test("서비스가 없으면 홈 섹션째 빠진다", () => {
  render(<App path="/" data={home()} />);
  expect(screen.queryByRole("region", { name: "외주로 맡는 일" })).toBeNull();
});
