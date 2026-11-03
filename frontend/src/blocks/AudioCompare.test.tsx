import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocumentView } from "./DocumentView";
import { MediaUrlContext, type RefreshMediaUrl } from "./media";
import { documentOf, exampleBlock } from "./testing";
import type { AudioCompareBlock } from "./types";

const block = exampleBlock("separation", "audio-compare");

function renderBlock(b: AudioCompareBlock = block, refresh: RefreshMediaUrl | null = null) {
  return render(
    <MediaUrlContext.Provider value={refresh}>
      <DocumentView document={documentOf(b)} />
    </MediaUrlContext.Provider>,
  );
}

/** jsdom has no media playback: give the element a settable position and a no-op play(). */
function playable(audio: HTMLMediaElement, at: number) {
  let time = at;
  Object.defineProperty(audio, "currentTime", {
    configurable: true,
    get: () => time,
    set: (value: number) => {
      time = value;
    },
  });
  const play = vi.fn(() => Promise.resolve());
  Object.defineProperty(audio, "play", { configurable: true, value: play });
  return play;
}

function player() {
  return document.querySelector("audio") as HTMLAudioElement;
}

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
});

afterEach(() => vi.restoreAllMocks());

test("audio-compare는 원음과 분리 트랙을 한 플레이어에서 고르고, 지표 표를 보여 준다", () => {
  renderBlock();

  expect(screen.getByRole("heading", { name: "01 · 맞장구와 말 끊기가 있는 대화" })).toBeInTheDocument();
  const tracks = within(screen.getByRole("group", { name: "재생할 트랙" })).getAllByRole("button");
  expect(tracks.map((t) => t.textContent)).toEqual([
    "원음 · 두 화자 혼합",
    "화자 A · 분리 결과",
    "화자 B · 분리 결과",
  ]);
  expect(tracks[0]).toHaveAttribute("aria-pressed", "true");
  expect(player()).toHaveAttribute("src", "https://private.example/mix.mp3?expires=600");
  expect(screen.getByRole("columnheader", { name: "잔류음 처리 후" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "9 / 237" })).toBeInTheDocument();
  expect(screen.getByText(/화자 구분 정확도와 동일한 지표는 아닙니다/)).toBeInTheDocument();
});

test("트랙을 바꾸면 같은 시점에서 이어 재생하고 그 화자의 변환 글과 원래 대본을 나란히 보여 준다", async () => {
  const user = userEvent.setup();
  renderBlock();
  const play = playable(player(), 12.5);
  fireEvent.play(player());

  await user.click(screen.getByRole("button", { name: "화자 A · 분리 결과" }));

  expect(screen.getByRole("button", { name: "화자 A · 분리 결과" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(player()).toHaveAttribute("src", "https://private.example/a.mp3?expires=600");
  const play2 = playable(player(), 0);
  fireEvent.loadedMetadata(player());
  expect(player().currentTime).toBe(12.5);
  expect(play2.mock.calls.length + play.mock.calls.length).toBe(1);

  const text = screen.getByRole("group", { name: "화자 A · 분리 결과 글 비교" });
  expect(within(text).getByRole("heading", { name: "변환한 글" })).toBeInTheDocument();
  expect(text).toHaveTextContent("여보세요? 지금 통화 괜찮으세요? 지난번에 말씀하신 납부 일정 때문에 연락드렸어요 네, 이번 주");
  expect(within(text).getByRole("heading", { name: "원래 대본" })).toBeInTheDocument();
  expect(text).toHaveTextContent("지난번에 말씀하신 납부 일정 때문에 연락드렸어요. 네. 이번 주 금요일까지");
});

test("presigned URL이 만료되어 재생이 실패하면 새 URL을 받아 그 자리에서 이어 재생한다", async () => {
  const refresh = vi.fn<RefreshMediaUrl>(() => Promise.resolve("https://private.example/mix.mp3?fresh"));
  renderBlock(block, refresh);
  playable(player(), 61);
  fireEvent.play(player());

  await act(async () => {
    fireEvent.error(player());
  });

  expect(refresh).toHaveBeenCalledWith(4);
  expect(player()).toHaveAttribute("src", "https://private.example/mix.mp3?fresh");
  const play = playable(player(), 0);
  fireEvent.loadedMetadata(player());
  expect(player().currentTime).toBe(61);
  expect(play).toHaveBeenCalledOnce();

  // A second failure right away is not an expired URL: no request loop.
  await act(async () => {
    fireEvent.error(player());
  });
  expect(refresh).toHaveBeenCalledOnce();
});

test("지워진 미디어의 트랙은 고를 수 없고 그렇다고 말한다", () => {
  const gone: AudioCompareBlock = {
    ...block,
    original: { ...block.original, url: null },
    tracks: block.tracks.map((t) => ({ ...t, url: null })),
  };
  renderBlock(gone);

  for (const button of screen.getAllByRole("button").filter((b) => !b.closest(".document-toc"))) expect(button).toBeDisabled();
  expect(screen.getByText("이 자료는 더 이상 제공되지 않습니다.")).toBeInTheDocument();
  expect(player()).toBeNull();
});
