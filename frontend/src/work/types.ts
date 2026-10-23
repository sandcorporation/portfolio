import type { Document } from "../blocks/types";

/** One portfolio card. Mirrors PortfolioCard in backend/services/portfolio.py. */
export interface PortfolioCard {
  slug: string;
  title: string;
  summary: string;
  cover_url: string;
  tags: string[];
  period: string;
}

/** The shell's #page-data on `/work/<slug>`. Mirrors PortfolioDetail in the backend. */
export interface WorkData {
  card: PortfolioCard;
  service_url: string;
  body: Document;
}

export function isWorkData(value: unknown): value is WorkData {
  if (typeof value !== "object" || value === null) return false;
  return "card" in value && "body" in value;
}

export const workPath = (slug: string) => `/work/${slug}`;
