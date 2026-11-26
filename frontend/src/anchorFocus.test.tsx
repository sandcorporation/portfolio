import { focusHashTarget } from "./anchorFocus";

afterEach(() => {
  document.body.innerHTML = "";
  window.location.hash = "";
});

test("hash 대상으로 스크롤하고 초점을 옮긴다", () => {
  document.body.innerHTML = '<h2 id="home-inquiry">문의</h2><button>다음</button>';
  const scroll = vi.fn();
  Element.prototype.scrollIntoView = scroll;
  window.location.hash = "#home-inquiry";

  expect(focusHashTarget()).toBe(true);
  expect(document.activeElement?.id).toBe("home-inquiry");
  expect(scroll).toHaveBeenCalled();
});

test("hash가 없거나 대상이 없으면 아무것도 하지 않는다", () => {
  document.body.innerHTML = '<h2 id="a">a</h2>';
  expect(focusHashTarget()).toBe(false);
  window.location.hash = "#nope";
  expect(focusHashTarget()).toBe(false);
  expect(document.activeElement).toBe(document.body);
});

test("HashFocus는 마운트 뒤 hash 대상에 초점을 둔다", async () => {
  const { render } = await import("@testing-library/react");
  const { HashFocus } = await import("./HashFocus");
  document.body.innerHTML = '<section id="home-services" tabindex="-1">서비스</section>';
  window.location.hash = "#home-services";
  render(<HashFocus />);
  expect(document.activeElement?.id).toBe("home-services");
});
