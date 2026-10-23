import { render, screen } from "@testing-library/react";
import { PortfolioCards, CardMeta } from "./PortfolioCards";
import { portfolioMeta, type PortfolioCard } from "./types";

const base: PortfolioCard = {
  slug: "a",
  title: "알파",
  summary: "요약 문장",
  cover_url: "",
  tags: [],
  period: "",
};

test("결과 한 줄이 있으면 요약 대신 보이고, 없으면 요약이 보인다", () => {
  render(
    <PortfolioCards
      cards={[
        { ...base, outcome: "월 3천 건 처리" },
        { ...base, slug: "b", title: "베타", summary: "베타 요약", outcome: "" },
      ]}
    />,
  );
  expect(screen.getByText("월 3천 건 처리")).toBeInTheDocument();
  expect(screen.queryByText("요약 문장")).toBeNull();
  expect(screen.getByText("베타 요약")).toBeInTheDocument();
});

test("왼쪽 열은 기간과 상태, live만 강조하고 오른쪽 열은 방문 숫자와 태그 네 개까지", () => {
  render(
    <PortfolioCards
      cards={[
        {
          ...base,
          period: "2025.03 ~",
          status: "live",
          status_label: "운영 중",
          tags: ["a", "b", "c", "d", "e"],
          visits: { today: 3, total: 1200 },
        },
        { ...base, slug: "b", title: "베타", status: "ended", status_label: "서비스 종료" },
      ]}
    />,
  );
  expect(screen.getByText("2025.03 ~")).toBeInTheDocument();
  expect(screen.getByText("운영 중")).toHaveClass("is-live");
  expect(screen.getByText("서비스 종료")).not.toHaveClass("is-live");
  expect(screen.getByText("오늘 3 · 누적 1,200")).toBeInTheDocument();
  expect(screen.queryByText("e")).toBeNull();
  expect(screen.getByText("d")).toBeInTheDocument();
});

test("상태·결과·기간이 모두 비어도 행이 정상이다", () => {
  render(<PortfolioCards cards={[{ ...base, summary: "" }]} />);
  expect(screen.getByRole("link", { name: /알파/ })).toHaveAttribute("href", "/work/a");
});

test("머리 메타는 운영 중이 0이면 생략한다", () => {
  expect(portfolioMeta([base, base])).toBe("2 projects");
  expect(portfolioMeta([{ ...base, status: "live" }, base])).toBe("2 projects · 운영 중 1");
});

test("작품 상세 메타 행에 상태 뱃지가 있다", () => {
  render(<CardMeta card={{ ...base, status: "building", status_label: "진행 중" }} />);
  expect(screen.getByText("진행 중")).toHaveClass("status-badge");
});

test("썸네일 칸은 썸네일이 없는 행에도 비어 있는 채로 있어 열 구조가 같다", () => {
  const { container } = render(
    <PortfolioCards
      cards={[
        { ...base, cover_url: "/m/a.png" },
        { ...base, slug: "b", title: "베타", cover_url: "" },
      ]}
    />,
  );
  const rows = Array.from(container.querySelectorAll(".portfolio-row"));
  expect(rows).toHaveLength(2);
  const [withThumb, without] = rows as [Element, Element];
  const shape = (row: Element) => Array.from(row.children).map((c) => c.className);
  expect(shape(without)).toEqual(shape(withThumb));
  expect(withThumb.querySelector(".portfolio-row-thumb img")).not.toBeNull();
  const empty = without.querySelector(".portfolio-row-thumb");
  expect(empty).not.toBeNull();
  expect(empty).toBeEmptyDOMElement();
});
