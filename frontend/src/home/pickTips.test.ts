import { expect, test } from "vitest";
import type { TipCard } from "../tips/types";
import { pickTips } from "./pickTips";

const tip = (n: number): TipCard => ({
  slug: `t${n}`,
  title: `팁 ${n}`,
  summary: "",
  categories: [],
  published_at: "2026-11-01T00:00:00+00:00",
});
const pool = (n: number) => Array.from({ length: n }, (_, i) => tip(i));

test("풀이 3개를 넘으면 겹침 없이 3개만 뽑는다", () => {
  const picked = pickTips(pool(12), () => 0.5);
  expect(picked).toHaveLength(3);
  expect(new Set(picked.map((t) => t.slug)).size).toBe(3);
});

test("풀이 3개 미만이면 있는 만큼, 0이면 빈 목록", () => {
  expect(pickTips(pool(2))).toHaveLength(2);
  expect(pickTips([])).toEqual([]);
});

test("주입한 난수에 따라 구성이 바뀐다", () => {
  const first = pickTips(pool(12), () => 0).map((t) => t.slug);
  const last = pickTips(pool(12), () => 0.999).map((t) => t.slug);
  expect(first).toEqual(["t0", "t1", "t2"]);
  expect(last).not.toEqual(first);
  expect(pickTips(pool(5), () => 1)).toHaveLength(3); // random() never reaches 1, but stay in range
});
