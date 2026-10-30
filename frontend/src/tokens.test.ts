import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC = __dirname;

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  });
}

/** Every source file's text, keyed by path (tests excluded). */
const sources: Record<string, string> = Object.fromEntries(
  walk(SRC)
    .filter((file) => /\.(css|tsx?)$/.test(file) && !/\.test\.tsx?$/.test(file))
    .map((file) => [file, readFileSync(file, "utf8")]),
);

const RAW_COLOR = /#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla|oklch|oklab|lab|lch)\(/;

describe("design tokens", () => {
  it("shared colors come from sandcorp-design, not from a copy here", () => {
    expect(tokens("light")["color-canvas"]).toBeTruthy();
    expect(sources[join(SRC, "tokens.css")]).not.toMatch(/--color-(canvas|ink|text|accent):/);
  });

  it("font stacks and their metric-matched fallback faces come from sandcorp-design (issue 155)", () => {
    const here = sources[join(SRC, "tokens.css")];
    expect(here).not.toMatch(/@font-face|--font-(sans|mono):/);
    const fallback = readFileSync(
      join(dirname(fileURLToPath(import.meta.resolve("sandcorp-design/tokens.css"))), "fallback.css"),
      "utf8",
    );
    for (const family of ["Pretendard Fallback", "Pretendard Fallback Apple", "Pretendard Fallback Win", "JetBrains Mono Fallback"]) {
      expect(fallback).toContain(`font-family: "${family}";`);
    }
  });

  it("raw color values live only in tokens.css", () => {
    const offenders = Object.entries(sources)
      .filter(([file]) => !file.endsWith("tokens.css") && !file.endsWith("types.gen.ts"))
      .filter(([, text]) => RAW_COLOR.test(text))
      .map(([file]) => file);
    expect(Object.keys(sources).length).toBeGreaterThan(10);
    expect(offenders).toEqual([]);
  });
});

// WCAG relative luminance and contrast ratio.
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

// The shared palette lives in sandcorp-design (issue 150); portfolio's tokens.css may override it.
const DESIGN_TOKENS = readFileSync(
  fileURLToPath(import.meta.resolve("sandcorp-design/tokens.css")),
  "utf8",
);

/** Hex token values of one scheme in one file: light is the first `:root`, dark the media query. */
function hexTokens(css: string, scheme: "light" | "dark"): Record<string, string> {
  const [light = "", dark = ""] = css.split("@media screen and (prefers-color-scheme: dark)");
  const block = scheme === "light" ? light : dark;
  const values: Record<string, string> = {};
  for (const [, name, value] of block.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    if (name && value) values[name] = value;
  }
  return values;
}

/** Effective token values of one scheme: design first, then portfolio's tokens.css. */
function tokens(scheme: "light" | "dark"): Record<string, string> {
  const own = sources[join(SRC, "tokens.css")] ?? "";
  return { ...hexTokens(DESIGN_TOKENS, scheme), ...hexTokens(own, scheme) };
}

describe.each(["light", "dark"] as const)("contrast (%s)", (scheme) => {
  const light = tokens("light");
  const t = { ...light, ...tokens(scheme) };
  const get = (name: string) => t[name] ?? "";
  const surfaces = ["color-canvas", "color-paper", "color-tint"];

  it.each(["color-text", "color-ink", "color-muted"])("%s is >= 4.5:1 on every surface", (fg) => {
    for (const bg of surfaces) {
      expect(contrast(get(fg), get(bg)), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("accent is >= 4.5:1 on paper, tint and accent-tint", () => {
    for (const bg of ["color-paper", "color-tint", "color-accent-tint"]) {
      expect(contrast(get("color-accent"), get(bg)), bg).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("text on the accent fill is >= 4.5:1", () => {
    expect(contrast(get("color-on-accent"), get("color-accent"))).toBeGreaterThanOrEqual(4.5);
  });

  it("text stays readable on the accent tint", () => {
    expect(contrast(get("color-text"), get("color-accent-tint"))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(get("color-muted"), get("color-accent-tint"))).toBeGreaterThanOrEqual(4.5);
  });
});
