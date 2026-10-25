import { render, screen } from "@testing-library/react";
import { Prose } from "./blocks/Prose";
import { isExternalHref } from "./links";

test("외부·내부·같은 호스트 절대 주소 판정", () => {
  expect(isExternalHref("https://flow.sandcorp.co.kr/x", "sandcorp.co.kr")).toBe(true);
  expect(isExternalHref("//example.com", "sandcorp.co.kr")).toBe(true);
  expect(isExternalHref("/work/a", "sandcorp.co.kr")).toBe(false);
  expect(isExternalHref("#a", "sandcorp.co.kr")).toBe(false);
  expect(isExternalHref("mailto:a@b.kr", "sandcorp.co.kr")).toBe(false);
  expect(isExternalHref("https://SANDCORP.co.kr/x", "sandcorp.co.kr")).toBe(false);
});

test("마크다운 링크: 외부만 새 탭", () => {
  render(<Prose source={`[밖](https://example.com) [안](/work/a) [같은](${window.location.origin}/x)`} />);
  expect(screen.getByText("밖")).toHaveAttribute("target", "_blank");
  expect(screen.getByText("밖")).toHaveAttribute("rel", "noopener noreferrer");
  expect(screen.getByText("안")).not.toHaveAttribute("target");
  expect(screen.getByText("같은")).not.toHaveAttribute("target");
});
