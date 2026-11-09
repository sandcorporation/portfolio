import { render, screen, waitFor, within } from "@testing-library/react";
import { App } from "../App";
import { highlightLanguage } from "./highlight";
import { loadHighlight } from "./loadHighlight";
import type { TipCard, TipData, TipsIndexData } from "./types";
import { tipsIndexHref } from "./types";

const card = (slug: string, extra: Partial<TipCard> = {}): TipCard => ({
  slug,
  title: `제목 ${slug}`,
  summary: `요약 ${slug}`,
  categories: [{ value: "testing", label: "테스트" }],
  published_at: "2026-10-22T15:30:00+00:00", // 2026.10.23 in Seoul
  ...extra,
});

const index = (extra: Partial<TipsIndexData> = {}): TipsIndexData => ({
  tips: [card("a"), card("b", { categories: [] })],
  categories: [
    { value: "testing", label: "테스트", count: 1 },
    { value: "auth", label: "인증", count: 1 },
  ],
  category: null,
  page: 1,
  pages: 1,
  total: 2,
  ...extra,
});

const BODY = "### 문제\n\n느리다.\n\n```python\ndef f():\n    return 'x'\n```\n\n`inline` 코드";

const tip = (extra: Partial<TipData> = {}): TipData => ({
  card: card("a", { categories: [{ value: "auth", label: "인증" }] }),
  body: BODY,
  related: [card("b"), card("c")],
  ...extra,
});

describe("/tips", () => {
  it("lists tips with date, categories and summary, and filters by category", () => {
    render(<App path="/tips" data={index({ category: { value: "auth", label: "인증" } })} />);

    expect(screen.getByRole("heading", { level: 1, name: "개발 팁" })).toBeInTheDocument();
    const filter = screen.getByRole("navigation", { name: "분류" });
    expect(within(filter).getByRole("link", { name: "인증" })).toHaveAttribute("aria-current", "page");
    expect(within(filter).getByRole("link", { name: "전체" })).toHaveAttribute("href", "/tips");
    const row = screen.getByRole("link", { name: /제목 a →/ });
    expect(row).toHaveAttribute("href", "/tips/a");
    expect(row).toHaveTextContent("2026.10.23");
    expect(row).toHaveTextContent("테스트");
    expect(row).toHaveTextContent("요약 a");
    const nav = screen.getByRole("navigation", { name: "사이트" });
    expect(within(nav).getByRole("link", { name: "팁" })).toHaveAttribute("aria-current", "page");
  });

  it("says so when there is nothing to show", () => {
    const { unmount } = render(<App path="/tips" data={index({ tips: [], categories: [], total: 0 })} />);
    expect(screen.getByText("아직 올린 팁이 없습니다.")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "분류" })).toBeNull();
    unmount();

    render(<App path="/tips" data={index({ tips: [], category: { value: "auth", label: "인증" } })} />);
    expect(screen.getByText("「인증」 분류의 팁이 없습니다.")).toBeInTheDocument();
  });

  it("keeps the category in the pager links", () => {
    expect(tipsIndexHref("auth", 2)).toBe("/tips?category=auth&page=2");
    expect(tipsIndexHref("", 1)).toBe("/tips");
  });
});

describe("/tips/<slug>", () => {
  it("draws the markdown with coloured fenced code and the related tips", async () => {
    const { container } = render(<App path="/tips/a" data={tip()} />);
    await waitFor(() => expect(container.querySelector("pre code.hljs")).not.toBeNull());

    expect(screen.getByRole("heading", { level: 1, name: "제목 a" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "인증" })).toHaveAttribute("href", "/tips?category=auth");
    expect(screen.getByRole("heading", { level: 3, name: "문제" })).toBeInTheDocument();
    const code = container.querySelector("pre code.language-python.hljs");
    expect(code?.querySelector(".hljs-keyword")).toHaveTextContent("def");
    expect(code?.querySelector(".hljs-string")).toHaveTextContent("'x'");
    expect(container.querySelector("p code")).toHaveTextContent("inline"); // inline stays plain
    const related = screen.getByRole("region", { name: "같은 분류의 다른 팁" });
    expect(within(related).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual([
      "/tips/b",
      "/tips/c",
    ]);
  });

  it("leaves out the related list when there is none and opens from a preview link", () => {
    render(<App path="/preview/tips/token" data={tip({ related: [] })} />);

    expect(screen.getByRole("heading", { level: 1, name: "제목 a" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "같은 분류의 다른 팁" })).toBeNull();
  });

  it("colours only the languages it knows, by name or alias", () => {
    expect(highlightLanguage("language-ts")).toBe("ts");
    expect(highlightLanguage("language-sh")).toBe("sh");
    expect(highlightLanguage("language-cobol")).toBeNull();
    expect(highlightLanguage(undefined)).toBeNull();
  });
});

describe("loadHighlight (GlitchTip 119)", () => {
  it("retries a failed chunk once, then gives up quietly", async () => {
    const load = vi.fn().mockRejectedValue(new TypeError("Failed to fetch dynamically imported module"));
    await expect(loadHighlight(load)).resolves.toBeUndefined();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("uses the chunk when the retry works", async () => {
    const module = await import("./highlight");
    const load = vi.fn().mockRejectedValueOnce(new TypeError("offline")).mockResolvedValue(module);
    await expect(loadHighlight(load)).resolves.toBe(module);
  });
});
