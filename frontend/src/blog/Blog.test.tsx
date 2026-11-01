import { render, screen, within } from "@testing-library/react";
import { App } from "../App";
import { exampleDocument } from "../blocks/testing";
import type { HomeData } from "../home/types";
import type { BlogIndexData, BlogPostData, PostCard } from "./types";

const card = (slug: string, extra: Partial<PostCard> = {}): PostCard => ({
  slug,
  title: `제목 ${slug}`,
  summary: `요약 ${slug}`,
  cover_url: "",
  tags: ["운영", "도구"],
  published_at: "2026-10-22T15:30:00+00:00", // 2026.10.23 00:30 in Seoul
  ...extra,
});

const index = (extra: Partial<BlogIndexData> = {}): BlogIndexData => ({
  posts: [card("a"), card("b", { tags: [] })],
  tags: [
    { tag: "운영", count: 2 },
    { tag: "도구", count: 1 },
  ],
  tag: "",
  page: 1,
  pages: 1,
  total: 2,
  ...extra,
});

const post = (extra: Partial<BlogPostData> = {}): BlogPostData => ({
  card: card("a", { cover_url: "https://img.example/cover.png" }),
  body: {
    tabs: [
      { id: "main", title: "본문", blocks: [{ id: "intro", type: "markdown", title: "왜 만들었나", level: 2, body: "본문입니다" }] },
    ],
  },
  prev: { slug: "older", title: "예전 글" },
  next: { slug: "newer", title: "새 글" },
  ...extra,
});

const home = (extra: Partial<HomeData> = {}): HomeData => ({
  tagline: "",
  stack: [],
  company_intro: exampleDocument,
  portfolio: [],
  posts: [card("a"), card("b")],
  news: [
    {
      title: "새 모델 공개",
      summary: "한 줄 요약",
      category: "모델",
      image_url: "https://img.example/1.jpg",
      url: "https://news.sandcorp.co.kr/a/1?utm_source=sandcorp&utm_medium=home",
      when: "3시간 전",
      published_at: "2026-10-23T09:00:00+00:00",
    },
    {
      title: "정책 발표",
      summary: "",
      category: "",
      image_url: "",
      url: "https://news.sandcorp.co.kr/a/2?utm_source=sandcorp&utm_medium=home",
      when: "2일 전",
      published_at: "2026-10-21T09:00:00+00:00",
    },
  ],
  contact: { email: "", phone: "", address: "" },
  ...extra,
});

test("홈의 기록 섹션은 글 행과 「모든 기록 보기」 링크를 보여 준다", () => {
  render(<App path="/" data={home()} />);

  const section = screen.getByRole("region", { name: "만들면서 남긴 기록" });
  expect(within(section).getByRole("link", { name: /제목 a →/ })).toHaveAttribute("href", "/blog/a");
  expect(within(section).getAllByText("2026.10.23")).toHaveLength(2); // Seoul date, not the reader's
  expect(within(section).getAllByText("운영")).toHaveLength(2);
  expect(within(section).getByText("요약 a")).toBeInTheDocument();
  expect(within(section).getByRole("link", { name: "모든 기록 보기 →" })).toHaveAttribute("href", "/blog");
});

test("홈의 Foresight 섹션은 기사 행을 utm이 붙은 주소로 새 탭으로 잇는다", () => {
  render(<App path="/" data={home()} />);

  const section = screen.getByRole("region", { name: "Foresight · 최근 뉴스" });
  const link = within(section).getByRole("link", { name: /새 모델 공개/ });
  expect(link).toHaveAttribute("href", "https://news.sandcorp.co.kr/a/1?utm_source=sandcorp&utm_medium=home");
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  expect(within(section).getByText("모델")).toBeInTheDocument();
  expect(within(section).getByText("3시간 전")).toBeInTheDocument();
  expect(section.querySelectorAll("img")).toHaveLength(1); // only the article with a picture
  expect(within(section).getByRole("link", { name: "Foresight 보기 →" })).toBeInTheDocument();
});

test("글이 없거나 뉴스가 비면 그 섹션을 통째로 뺀다", () => {
  render(<App path="/" data={home({ posts: [], news: [] })} />);

  expect(screen.queryByRole("region", { name: "만들면서 남긴 기록" })).toBeNull();
  expect(screen.queryByRole("region", { name: "Foresight · 최근 뉴스" })).toBeNull();
  expect(screen.queryByText(/뉴스/)).toBeNull();
  expect(screen.getByText(/Contact/)).toHaveTextContent("02 — Contact");
});

test("상단 내비는 회사 소개 · 서비스 · 기록 · Foresight ↗ · 포트폴리오 · 문의 순서로 주소를 건다", () => {
  render(<App path="/" data={home()} />);

  const links = within(screen.getByRole("navigation", { name: "사이트" })).getAllByRole("link");
  expect(links.map((l) => [l.textContent, l.getAttribute("href")])).toEqual([
    ["회사 소개", "/#home-company"],
    ["서비스", "/#home-services"],
    ["기록", "/blog"],
    ["Foresight ↗", "https://news.sandcorp.co.kr/?utm_source=sandcorp&utm_medium=nav"],
    ["포트폴리오", "/#home-portfolio"],
    ["문의", "/#home-inquiry"],
  ]);
  expect(links[3]).toHaveAttribute("rel", "noopener noreferrer");
  expect(links[3]).toHaveAttribute("target", "_blank");
});

test("홈 섹션은 기록 · Foresight가 포트폴리오보다 위이고 목차 레일이 없다", () => {
  const data = home({
    portfolio: [
      { slug: "voice", title: "녹취 분석", summary: "요약", cover_url: "", tags: [], period: "2025.03" },
    ],
  });
  const { container } = render(<App path="/" data={data} />);

  const h2 = Array.from(container.querySelectorAll("main h2.page-section-title")).map((h) => h.textContent);
  expect(h2).toEqual([
    "회사 소개",
    "만들면서 남긴 기록",
    "Foresight · 최근 뉴스",
    "포트폴리오",
    "문의·제안",
  ]);
  expect(Array.from(container.querySelectorAll(".section-head")).map((e) => e.textContent?.slice(0, 2))).toEqual([
    "01", "02", "03", "04", "05",
  ]);
  expect(container.querySelector(".page-toc")).toBeNull();
  expect(container.querySelector(".document-toc")).toBeNull();
  const row = container.querySelector(".link-row") as HTMLElement;
  expect(Array.from(row.querySelectorAll("a")).map((a) => a.textContent)).toEqual([
    "회사 소개 →",
    "기록 →",
    "포트폴리오 →",
    "문의 →",
  ]);
});

test("기록 화면은 내비의 기록에 현재 표시를 단다", () => {
  render(<App path="/blog" data={index({ posts: [card("a")], total: 1 })} />);

  expect(within(screen.getByRole("navigation", { name: "사이트" })).getByRole("link", { name: "기록" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("/blog는 글 행과 태그 탭을 보여 주고 지금 태그를 표시한다", () => {
  render(<App path="/blog" data={index({ tag: "도구", posts: [card("a")], total: 1 })} />);

  expect(screen.getByRole("heading", { level: 1, name: "만들면서 남긴 기록" })).toBeInTheDocument();
  const tags = screen.getByRole("navigation", { name: "태그" });
  expect(within(tags).getByRole("link", { name: "도구" })).toHaveAttribute("aria-current", "page");
  expect(within(tags).getByRole("link", { name: "운영" })).toHaveAttribute("href", "/blog?tag=%EC%9A%B4%EC%98%81");
  expect(within(tags).getByRole("link", { name: "전체" })).toHaveAttribute("href", "/blog");
  expect(screen.getByRole("link", { name: /제목 a →/ })).toHaveAttribute("href", "/blog/a");
});

test("/blog 쪽 이동은 태그를 지키고 처음·끝에서는 없는 쪽으로 가는 링크를 두지 않는다", () => {
  const { rerender } = render(<App path="/blog" data={index({ tag: "운영", page: 2, pages: 3 })} />);

  const pager = screen.getByRole("navigation", { name: "쪽" });
  expect(within(pager).getByRole("link", { name: "← 이전" })).toHaveAttribute("href", "/blog?tag=%EC%9A%B4%EC%98%81");
  expect(within(pager).getByRole("link", { name: "다음 →" })).toHaveAttribute(
    "href",
    "/blog?tag=%EC%9A%B4%EC%98%81&page=3",
  );

  rerender(<App path="/blog" data={index({ page: 1, pages: 1 })} />);
  expect(screen.queryByRole("navigation", { name: "쪽" })).toBeNull();
});

test("/blog에 글이 없으면 빈 안내를 보여 준다", () => {
  render(<App path="/blog" data={index({ posts: [], tags: [], total: 0 })} />);

  expect(screen.getByText("아직 올린 글이 없습니다.")).toBeInTheDocument();
  expect(screen.queryByRole("navigation", { name: "태그" })).toBeNull();
});

test("글 화면은 메타·제목·요약·커버·블록 본문·이전/다음·문의 버튼 순으로 보여 준다", () => {
  render(<App path="/blog/a" data={post()} />);

  expect(screen.getByRole("heading", { level: 1, name: "제목 a" })).toBeInTheDocument();
  expect(screen.getByText("요약 a")).toBeInTheDocument();
  expect(screen.getByText("2026.10.23")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "도구" })).toHaveAttribute("href", "/blog?tag=%EB%8F%84%EA%B5%AC");
  expect(document.querySelector("img.work-cover")).toHaveAttribute("src", "https://img.example/cover.png");
  expect(screen.getByText("본문입니다")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /이전 글.*예전 글/ })).toHaveAttribute("href", "/blog/older");
  expect(screen.getByRole("link", { name: /다음 글.*새 글/ })).toHaveAttribute("href", "/blog/newer");
  expect(screen.getByRole("link", { name: "문의 →" })).toHaveAttribute("href", "/#home-inquiry");
  expect(screen.getByRole("link", { name: "← 기록" })).toHaveAttribute("href", "/blog");
});

test("가장 오래된·새 글은 없는 쪽 이웃 링크를 두지 않는다", () => {
  render(<App path="/blog/a" data={post({ prev: null, card: card("a") })} />);

  expect(screen.queryByRole("link", { name: /이전 글/ })).toBeNull();
  expect(screen.getByRole("link", { name: /다음 글/ })).toBeInTheDocument();
  expect(document.querySelector("img.work-cover")).toBeNull();
});
