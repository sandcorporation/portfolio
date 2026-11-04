import type { Availability, Business } from "../home/types";

/** A category a tip is filed under. Mirrors CategoryRef in backend/services/tips.py. */
export interface CategoryRef {
  value: string;
  label: string;
}

export interface CategoryCount extends CategoryRef {
  count: number;
}

/** One tip in a list. Mirrors TipCard in backend/services/tips.py. */
export interface TipCard {
  slug: string;
  title: string;
  summary: string;
  categories: CategoryRef[];
  /** ISO 8601 */
  published_at: string;
}

/** The shell's #page-data on `/tips`. Mirrors TipListing in the backend. */
export interface TipsIndexData {
  tips: TipCard[];
  categories: CategoryCount[];
  /** null for every tip */
  category: CategoryRef | null;
  page: number;
  pages: number;
  total: number;
  availability?: Availability | null;
  business?: Business | null;
}

/** The shell's #page-data on `/tips/<slug>` and its preview. Mirrors TipDetail in the backend.
 * `body` is markdown; `related` holds up to three other tips of the same categories. */
export interface TipData {
  card: TipCard;
  body: string;
  related: TipCard[];
  availability?: Availability | null;
  business?: Business | null;
}

export function isTipsIndexData(value: unknown): value is TipsIndexData {
  if (typeof value !== "object" || value === null) return false;
  return "tips" in value && "categories" in value && "pages" in value;
}

export function isTipData(value: unknown): value is TipData {
  if (typeof value !== "object" || value === null) return false;
  return "card" in value && "related" in value && "body" in value && typeof value.body === "string";
}

export const tipPath = (slug: string) => `/tips/${slug}`;

/** `/tips` with the category and page the list is on (the first page and "all" leave no query). */
export function tipsIndexHref(category: string, page = 1): string {
  const query = new URLSearchParams();
  if (category) query.set("category", category);
  if (page > 1) query.set("page", String(page));
  const text = query.toString();
  return text ? `/tips?${text}` : "/tips";
}
