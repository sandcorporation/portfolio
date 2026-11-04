import type { TipCard } from "../tips/types";

export const HOME_TIP_COUNT = 3;

/** `count` tips drawn at random from the pool (fewer if the pool is smaller; none if empty).
 * `random` is injected so tests can pin the draw; the home passes Math.random after mount. */
export function pickTips(
  pool: TipCard[],
  random: () => number = Math.random,
  count: number = HOME_TIP_COUNT,
): TipCard[] {
  const rest = [...pool];
  const picked: TipCard[] = [];
  while (picked.length < count && rest.length > 0) {
    const i = Math.min(Math.floor(random() * rest.length), rest.length - 1);
    const [one] = rest.splice(i, 1);
    if (one) picked.push(one);
  }
  return picked;
}
