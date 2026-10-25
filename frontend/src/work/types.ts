import type { Document } from "../blocks/types";
import type { Availability, Business } from "../home/types";

/** One portfolio card. Mirrors PortfolioCard in backend/services/portfolio.py. */
export interface PortfolioCard {
  slug: string;
  title: string;
  summary: string;
  cover_url: string;
  tags: string[];
  period: string;
  /** "live" | "building" | "ended"; "" shows no status. */
  status?: string;
  /** The Korean label of `status`. */
  status_label?: string;
  /** One line under the row title instead of the summary. */
  outcome?: string;
  /** Visitors today / since the count began; null leaves the row without numbers. */
  visits?: { today: number; total: number } | null;
}

/** The shell's #page-data on `/work/<slug>`. Mirrors PortfolioDetail in the backend. */
export interface WorkData {
  card: PortfolioCard;
  service_url: string;
  body: Document;
  availability?: Availability | null;
  business?: Business | null;
}

export function isWorkData(value: unknown): value is WorkData {
  if (typeof value !== "object" || value === null) return false;
  return "card" in value && "body" in value;
}

export const workPath = (slug: string) => `/work/${slug}`;

/** The section head's meta: "N projects", plus "운영 중 N" when any item is live. */
export function portfolioMeta(cards: PortfolioCard[]): string {
  const live = cards.filter((card) => card.status === "live").length;
  return live > 0 ? `${cards.length} projects · 운영 중 ${live}` : `${cards.length} projects`;
}
