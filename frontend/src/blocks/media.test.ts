import { endpointRefresher } from "./media";

test("endpointRefresher는 문서의 미디어 주소를 묻고, 거절되면 null을 준다", async () => {
  const fetchImpl = vi.fn<typeof fetch>((input) =>
    Promise.resolve(
      String(input).endsWith("/9")
        ? new Response("{}", { status: 404 })
        : Response.json({ url: "https://private.example/new" }),
    ),
  );
  const refresh = endpointRefresher("/p/abc/media", fetchImpl);

  expect(await refresh(4)).toBe("https://private.example/new");
  expect(await refresh(4, { download: true })).toBe("https://private.example/new");
  expect(await refresh(9)).toBeNull();
  expect(fetchImpl.mock.calls.map(([input]) => input)).toEqual([
    "/p/abc/media/4",
    "/p/abc/media/4?download=1",
    "/p/abc/media/9",
  ]);
});
