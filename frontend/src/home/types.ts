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

export interface HomeData {
  tagline: string;
  /** The GitHub profile's stack badges: the hero's tag line. */
  stack: string[];
  company_intro: Document;
  ceo_intro: Document;
  portfolio: PortfolioCard[];
  /** Newest published blog posts; empty hides the section. */
  posts: PostCard[];
  /** Newest Foresight articles; empty hides the section. */
  news: NewsItem[];
  contact: { email: string; phone: string; address: string };
}

export function isHomeData(value: unknown): value is HomeData {
  if (typeof value !== "object" || value === null) return false;
  return "company_intro" in value && "ceo_intro" in value && "contact" in value && "portfolio" in value;
}
