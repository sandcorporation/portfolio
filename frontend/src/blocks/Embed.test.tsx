import { act, render, screen } from "@testing-library/react";
import { DocumentView } from "./DocumentView";
import { RenderModeContext, screenMode } from "./mode";
import { themedSrc } from "./embedSrc";
import type { Document } from "./types";

const FLOW = "https://flow.sandcorp.co.kr";
const doc: Document = {
  tabs: [
    {
      id: "t",
      title: "탭",
      blocks: [
        {
          id: "try",
          type: "embed",
          src: `${FLOW}/try?embed=1&template=home`,
          title: "Flow 체험",
          intro: "아래에서 바로 고쳐 보고 시험 대화까지 해 볼 수 있어요 · 24시간 체험",
          open_label: "새 탭에서 열기",
        },
      ],
    },
  ],
};

function mockScheme(dark: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: dark && query.includes("dark"),
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

function show(print = false) {
  return render(
    <RenderModeContext.Provider value={{ ...screenMode, print }}>
      <DocumentView document={doc} />
    </RenderModeContext.Provider>,
  );
}

function post(source: MessageEventSource | null, origin: string, data: unknown) {
  act(() => {
    window.dispatchEvent(new MessageEvent("message", { source, origin, data }));
  });
}

beforeEach(() => mockScheme(false));

test("라이트: theme 없는 주소의 640px 프레임과 새 탭 링크", () => {
  show();
  const frame = screen.getByTitle("Flow 체험") as HTMLIFrameElement;
  expect(frame.getAttribute("src")).toBe(`${FLOW}/try?embed=1&template=home`);
  expect(frame.style.height).toBe("640px");
  const link = screen.getByRole("link", { name: "새 탭에서 열기" });
  expect(link.getAttribute("target")).toBe("_blank");
  expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  expect(screen.getByText(/24시간 체험/)).toBeTruthy();
});

test("다크: src에 theme=dark", () => {
  mockScheme(true);
  show();
  expect((screen.getByTitle("Flow 체험") as HTMLIFrameElement).getAttribute("src")).toContain("theme=dark");
  expect(themedSrc(`${FLOW}/try?embed=1&theme=dark`, false)).toBe(`${FLOW}/try?embed=1`);
});

test("load하면 hello를 Flow origin으로 보내고 height 메시지로 높이가 바뀐다", () => {
  show();
  const frame = screen.getByTitle("Flow 체험") as HTMLIFrameElement;
  const win = frame.contentWindow as Window;
  const send = vi.spyOn(win, "postMessage");
  act(() => {
    frame.dispatchEvent(new Event("load"));
  });
  expect(send).toHaveBeenCalledWith({ type: "sandcorp-flow:hello" }, FLOW);
  post(win, FLOW, { type: "sandcorp-flow:height", height: 733 });
  expect(frame.style.height).toBe("733px");
});

test("origin이 다르거나 source가 프레임이 아니거나 형식이 틀린 메시지는 무시한다", () => {
  show();
  const frame = screen.getByTitle("Flow 체험") as HTMLIFrameElement;
  const win = frame.contentWindow as Window;
  post(win, "https://evil.example", { type: "sandcorp-flow:height", height: 900 });
  post(window, FLOW, { type: "sandcorp-flow:height", height: 900 });
  post(win, FLOW, { type: "other", height: 900 });
  post(win, FLOW, { type: "sandcorp-flow:height", height: "900" });
  post(win, FLOW, { type: "sandcorp-flow:height", height: Number.NaN });
  expect(frame.style.height).toBe("640px");
  post(win, FLOW, { type: "sandcorp-flow:height", height: 99999 });
  expect(frame.style.height).toBe("4000px");
});

test("인쇄: 프레임 없이 문구와 주소만", () => {
  show(true);
  expect(screen.queryByTitle("Flow 체험")).toBeNull();
  expect(screen.getByText(`${FLOW}/try?embed=1&template=home`, { exact: false })).toBeTruthy();
});
