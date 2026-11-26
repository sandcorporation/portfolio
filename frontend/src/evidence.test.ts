import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";

// A long evidence value must wrap on a phone (390px) instead of widening the page: the one-line
// `nowrap` belongs to the wide row only, inside a media query.
it("evidence 큰 숫자는 좁은 화면에서 줄바꿈된다", () => {
  const css = readFileSync(join(__dirname, "styles.css"), "utf8");
  const outsideMedia = css.replace(/@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/g, "");
  const rules = [...outsideMedia.matchAll(/(\.evidence-row[^{]*)\{([^}]*)\}/g)];
  expect(rules.length).toBeGreaterThan(0);
  for (const [, selector, body] of rules) {
    expect(body, selector).not.toMatch(/white-space:\s*nowrap/);
  }
  expect(outsideMedia).toMatch(/\.evidence-row \.kpi-value\s*\{[^}]*overflow-wrap:\s*anywhere/);
});

// #66: the wide one-line row (>=1024px) must not keep `nowrap` either: a long value overflowed its
// tile and overlapped the next one between 1024 and 1440px.
it("evidence 칸은 넓은 화면 규칙에도 nowrap이 없다", () => {
  const css = readFileSync(join(__dirname, "styles.css"), "utf8");
  const rules = [...css.matchAll(/(\.evidence[^{,]*)\{([^{}]*)\}/g)];
  expect(rules.length).toBeGreaterThan(0);
  for (const [, selector, body] of rules) {
    expect(body, selector).not.toMatch(/white-space:\s*nowrap/);
  }
});
