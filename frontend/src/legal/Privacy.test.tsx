import { render, screen, within } from "@testing-library/react";
import { App } from "../App";
import type { PrivacyData } from "./types";

const page = (): PrivacyData => ({
  policy: {
    title: "개인정보처리방침",
    effective_on: "2026년 11월 4일",
    summary: ["요약 하나", "요약 둘"],
    intro: "이 문서는 …",
    operator: "운영자: 개인사업자 샌드코프(Sandcorp)",
    sections: [
      {
        id: "collect",
        title: "1. 수집하는 항목",
        blocks: [
          { kind: "table", head: ["항목", "언제"], rows: [["이름", "문의할 때"]] },
          { kind: "p", text: "그 밖의 정보는 받지 않습니다." },
        ],
      },
      {
        id: "youtube",
        title: "9. YouTube API 서비스",
        blocks: [
          { kind: "ul", items: ["항목"] },
          {
            kind: "links",
            items: [
              { label: "YouTube 서비스 약관", href: "https://www.youtube.com/t/terms" },
              { label: "메일", href: "mailto:a@example.com" },
            ],
          },
        ],
      },
    ],
  },
  business: { name: "샌드코프(Sandcorp)", representative: "김한얼", number: "752-26-01740", address: "" },
});

test("개인정보처리방침은 시행일·요약·운영자 줄과 번호 절을 보여 주고, 표는 가로 스크롤 감싸개 안에 있다", () => {
  const { container } = render(<App path="/privacy" data={page()} />);

  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("개인정보처리방침");
  expect(screen.getByText("시행 2026년 11월 4일")).toBeInTheDocument();
  expect(within(screen.getByRole("complementary", { name: "요약" })).getByText("요약 둘")).toBeInTheDocument();
  expect(screen.getByText("운영자: 개인사업자 샌드코프(Sandcorp)")).toBeInTheDocument();
  const titles = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
  expect(titles).toEqual(["1. 수집하는 항목", "9. YouTube API 서비스"]);
  expect(container.querySelector(".sc-prose-table-scroll > table")).not.toBeNull();
});

test("외부 링크는 새 탭, mailto는 같은 탭", () => {
  render(<App path="/privacy" data={page()} />);

  expect(screen.getByRole("link", { name: "YouTube 서비스 약관" })).toHaveAttribute("target", "_blank");
  expect(screen.getByRole("link", { name: "메일" })).not.toHaveAttribute("target");
});

test("푸터에 개인정보처리방침 링크가 있다", () => {
  render(<App path="/privacy" data={page()} />);

  const footer = screen.getByRole("contentinfo");
  expect(within(footer).getByRole("link", { name: "개인정보처리방침" })).toHaveAttribute("href", "/privacy");
});
