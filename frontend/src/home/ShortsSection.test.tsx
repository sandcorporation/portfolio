import { fireEvent, render, screen, within } from "@testing-library/react";
import { App } from "../App";
import { exampleDocument } from "../blocks/testing";
import type { HomeData, ShortCard } from "./types";

const short = (id: string, extra: Partial<ShortCard> = {}): ShortCard => ({
  youtube_id: id,
  title: `쇼츠 ${id}`,
  url: `https://www.youtube.com/shorts/${id}`,
  thumbnail_url: `https://i.ytimg.com/vi/${id}/hqdefault.jpg`,
  link: "",
  link_label: "",
  ...extra,
});

const home = (shorts: ShortCard[]): HomeData => ({
  tagline: "",
  stack: [],
  company_intro: exampleDocument,
  portfolio: [],
  posts: [],
  news: [],
  shorts,
  contact: { email: "", phone: "", address: "" },
});

test("홈 쇼츠는 썸네일과 재생 버튼만 두고, 누르면 그 자리에서 nocookie 플레이어가 뜬다", () => {
  render(
    <App path="/" data={home([short("aaaaaaaaaaa", { link: "/tips/x", link_label: "관련 팁 →" }), short("bbbbbbbbbbb")])} />,
  );
  const section = screen.getByRole("region", { name: "짧은 영상" });
  expect(section.querySelector("iframe")).toBeNull();
  expect(within(section).getByText("만들고 운영하며 겪은 일을 1분 안팎으로 보여 줍니다.")).toBeInTheDocument();
  const imgs = section.querySelectorAll("img");
  expect(imgs).toHaveLength(2);
  expect(imgs[0]).toHaveAttribute("loading", "lazy");
  expect(imgs[0]).toHaveAttribute("src", "https://i.ytimg.com/vi/aaaaaaaaaaa/hqdefault.jpg");
  expect(within(section).getByRole("link", { name: "관련 팁 →" })).toHaveAttribute("href", "/tips/x");
  const channel = within(section).getByRole("link", { name: "유튜브에서 보기 →" });
  expect(channel).toHaveAttribute("href", "https://www.youtube.com/@sandcorporation");
  expect(channel).toHaveAttribute("target", "_blank");

  fireEvent.click(within(section).getByRole("button", { name: "쇼츠 aaaaaaaaaaa 재생" }));

  const frame = section.querySelector("iframe");
  expect(frame).toHaveAttribute("src", "https://www.youtube-nocookie.com/embed/aaaaaaaaaaa?autoplay=1&playsinline=1");
  expect(frame).toHaveAttribute("title", "쇼츠 aaaaaaaaaaa");
  expect(frame).toHaveAttribute("referrerpolicy", "strict-origin-when-cross-origin"); // else YouTube error 153
  expect(within(section).getAllByRole("button")).toHaveLength(1); // the other card is still a thumbnail
});

test("노출할 쇼츠가 없으면 섹션째 없다", () => {
  render(<App path="/" data={home([])} />);
  expect(screen.queryByRole("region", { name: "짧은 영상" })).toBeNull();
});
