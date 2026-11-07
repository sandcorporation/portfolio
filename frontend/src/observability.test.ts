import { vi } from "vitest";
import type { ErrorEvent } from "@sentry/react";
import { startErrorReporting } from "./observability";
import { beforeSend } from "./sentry";

test("without a DSN from the shell the reporter is never loaded", async () => {
  const load = vi.fn();
  expect(await startErrorReporting(undefined, load)).toBe(false);
  expect(await startErrorReporting({ sentryDsn: "  " }, load)).toBe(false);
  expect(load).not.toHaveBeenCalled();
});

test("with a DSN it loads the reporter and starts it with the release", async () => {
  const start = vi.fn();
  const load = vi.fn(async () => ({ start }));
  const config = { sentryDsn: "https://public@example.invalid/1", sentryRelease: "a".repeat(40) };
  expect(await startErrorReporting(config, load)).toBe(true);
  expect(start).toHaveBeenCalledWith({
    dsn: "https://public@example.invalid/1",
    release: "a".repeat(40),
    environment: "production",
  });
});

test("beforeSend drops cookies, credential headers and token-shaped strings", () => {
  const event = {
    type: undefined,
    message: "failed with Bearer abcdefgh12345678",
    exception: { values: [{ type: "Error", value: "token=s3cr3tvalue" }] },
    request: {
      url: "https://sandcorp.co.kr/preview/blog/AbC.dEf:1x2y3z:signature",
      cookies: { sessionid: "abc" },
      headers: { Cookie: "sessionid=abc", Authorization: "Bearer x", "User-Agent": "UA" },
    },
  } as ErrorEvent;
  const kept = beforeSend(event);
  const text = JSON.stringify(kept);
  for (const secret of ["abcdefgh12345678", "s3cr3tvalue", "sessionid", "signature"]) {
    expect(text).not.toContain(secret);
  }
  expect(kept.request?.headers).toEqual({ "User-Agent": "UA" });
  expect(kept.request?.url).toBe("https://sandcorp.co.kr/preview/blog/[Filtered]");
});
