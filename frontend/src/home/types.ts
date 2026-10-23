import type { Document } from "../blocks/types";
import type { PortfolioCard } from "../work/types";

/** The shell's #page-data on `/`. Mirrors HomeData in backend/services/home.py. */
export interface HomeData {
  tagline: string;
  /** The GitHub profile's stack badges: the hero's tag line. */
  stack: string[];
  company_intro: Document;
  ceo_intro: Document;
  portfolio: PortfolioCard[];
  contact: { email: string; phone: string; address: string };
}

export function isHomeData(value: unknown): value is HomeData {
  if (typeof value !== "object" || value === null) return false;
  return "company_intro" in value && "ceo_intro" in value && "contact" in value && "portfolio" in value;
}
