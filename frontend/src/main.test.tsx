import { act } from "@testing-library/react";
import { vi } from "vitest";

// Issue 109: public pages arrive with a server HTML copy in #root. The app renders over it with
// createRoot (no hydration), so the copy is replaced and React reports nothing about it.
test("the app replaces the server HTML in #root without warnings", async () => {
  const errors = vi.spyOn(console, "error");
  const warnings = vi.spyOn(console, "warn");
  window.history.replaceState(null, "", "/blog");
  document.body.innerHTML = `
    <div id="root"><main class="page"><h1>server copy</h1><p>only for readers without JS</p></main></div>
    <script id="page-data" type="application/json">
      {"posts": [], "tags": [], "tag": "", "page": 1, "pages": 1, "total": 0, "availability": null, "business": null}
    </script>`;

  await act(async () => {
    await import("./main");
  });

  const root = document.getElementById("root");
  expect(root?.textContent).not.toContain("server copy");
  expect(root?.querySelector("h1")?.textContent).toBe("만들면서 남긴 기록");
  expect(root?.querySelectorAll("h1")).toHaveLength(1);
  expect(errors).not.toHaveBeenCalled();
  expect(warnings).not.toHaveBeenCalled();
});
