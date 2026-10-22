import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocumentView } from "./DocumentView";
import { MediaUrlContext, type RefreshMediaUrl } from "./media";
import { documentOf, exampleBlock } from "./testing";
import type { VideoBlock } from "./types";

const block = exampleBlock("demo-video", "video");

function renderBlock(b: VideoBlock = block, refresh: RefreshMediaUrl | null = null) {
  return render(
    <MediaUrlContext.Provider value={refresh}>
      <DocumentView document={documentOf(b)} />
    </MediaUrlContext.Provider>,
  );
}

function video() {
  return document.querySelector("video") as HTMLVideoElement;
}

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
});

afterEach(() => vi.restoreAllMocks());

test("video 블록은 포스터·캡션과 함께 영상을 보여 주고, 허용되면 내려받기 링크를 단다", () => {
  renderBlock();

  expect(screen.getByRole("heading", { name: "시연 영상" })).toBeInTheDocument();
  expect(video()).toHaveAttribute("src", "https://private.example/demo.mp4?expires=600");
  expect(video()).toHaveAttribute("poster", "https://public.example/gallery-1.png");
  expect(screen.getByText("약 45초 · 본인 목소리 합성 · 자막")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "영상 파일 내려받기" })).toBeInTheDocument();
});

test("내려받기가 허용되지 않으면 링크가 없고 플레이어의 내려받기도 숨긴다", () => {
  renderBlock({ ...block, allow_download: false });

  expect(screen.queryByRole("link", { name: "영상 파일 내려받기" })).toBeNull();
  expect(video()).toHaveAttribute("controlslist", "nodownload");
});

test("비공개 영상의 내려받기는 저장용 URL을 새로 받아 연다", async () => {
  const user = userEvent.setup();
  const refresh = vi.fn<RefreshMediaUrl>(() => Promise.resolve("https://private.example/save"));
  const assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, assign });
  renderBlock(block, refresh);

  await user.click(screen.getByRole("link", { name: "영상 파일 내려받기" }));

  expect(refresh).toHaveBeenCalledWith(7, { download: true });
  expect(assign).toHaveBeenCalledWith("https://private.example/save");
  vi.unstubAllGlobals();
});

test("만료로 영상이 실패하면 새 URL로 바꾼다", async () => {
  const refresh = vi.fn<RefreshMediaUrl>(() => Promise.resolve("https://private.example/demo.mp4?fresh"));
  renderBlock(block, refresh);

  await act(async () => {
    fireEvent.error(video());
  });

  expect(refresh).toHaveBeenCalledWith(7);
  expect(video()).toHaveAttribute("src", "https://private.example/demo.mp4?fresh");
});
