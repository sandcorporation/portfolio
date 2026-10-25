import type { Document } from "../blocks/types";
import type { PostCard } from "../blog/types";
import type { PortfolioCard } from "../work/types";

/** The shell's #page-data on `/`. Mirrors HomeData in backend/services/home.py. */
export interface NewsItem {
  title: string;
  summary: string;
  category: string;
  image_url: string;
  /** The article, utm marks included. */
  url: string;
  /** "3시간 전", worked out by the server. */
  when: string;
  published_at: string;
}

export interface SiteVisits {
  /** People on a site right now. */
  live: number;
  /** Visitors today. */
  today: number;
  /** Visitors since the count began. */
  total: number;
}

/** The masthead's availability. Mirrors Availability in backend/services/home.py. */
export interface Availability {
  text: string;
  /** "YYYY.MM"; "" without a date. */
  updated: string;
}

/** The footer's business details. Mirrors Business in backend/services/home.py. */
export interface Business {
  name: string;
  representative: string;
  number: string;
  address: string;
}

/** One big number of the evidence row under the hero. Mirrors EvidenceItem in services/home.py. */
export interface EvidenceItem {
  key: "services" | "foresight" | "reply" | "career";
  /** Already formatted ("4", "1,234", "1일"). */
  value: string;
  /** Small text after the value ("건/일", "년차"); "" when none. */
  unit: string;
  label: string;
}

export interface HomeData {
  tagline: string;
  /** The GitHub profile's stack badges: the hero's tag line. */
  stack: string[];
  company_intro: Document;
  portfolio: PortfolioCard[];
  /** Newest published blog posts; empty hides the section. */
  posts: PostCard[];
  /** Newest Foresight articles; empty hides the section. */
  news: NewsItem[];
  /** All sites together (sandcorp-metrics); null/absent leaves the masthead without numbers. */
  visits?: SiteVisits | null;
  /** The profile's availability; null/absent leaves it out of the masthead. */
  availability?: Availability | null;
  /** The footer's business details; null/absent leaves the line out. */
  business?: Business | null;
  /** The row under the hero; empty/absent hides it. */
  evidence?: EvidenceItem[];
  contact: { email: string; phone: string; address: string };
}

export function isHomeData(value: unknown): value is HomeData {
  if (typeof value !== "object" || value === null) return false;
  return "company_intro" in value && "contact" in value && "portfolio" in value;
}
