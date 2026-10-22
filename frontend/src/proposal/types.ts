import type { Document } from "../blocks/types";

export interface Supplier {
  name: string;
  email: string;
  phone: string;
  address: string;
}

/** The published revision the customer is reading. */
export interface RevisionMeta {
  number: number;
  /** SC-{YYYYMMDD}-{client code}-{serial}. */
  doc_number: string;
  published_at: string;
}

/** The shell's #page-data for a proposal. Mirrors ProposalPageData in backend/services/proposals.py. */
export interface ProposalData {
  /** True on the owner's signed preview; the screen says so. */
  preview: boolean;
  recipient: string;
  title: string;
  subtitle: string;
  /** ISO date (YYYY-MM-DD). */
  quote_date: string;
  valid_until: string | null;
  supplier: Supplier;
  document: Document;
  /** Customer page only (absent on the preview). */
  revision?: RevisionMeta | null;
  /** Customer page only: for the lock button's form. */
  csrf_token?: string | null;
  /** Where to ask for a fresh private media URL: GET {media_endpoint}/{media_id} -> {url}. */
  media_endpoint?: string | null;
}

/** /p/<slug> before the code. Mirrors CodeScreenData. */
export interface CodeScreenData {
  screen: "code";
  /** Why the last try failed: a wrong code, or too many of them (blocked for a while). */
  error: "wrong" | "blocked" | null;
  csrf_token: string;
}

/** /p/<slug> past its validity date. Mirrors ExpiredScreenData. */
export interface ExpiredScreenData {
  screen: "expired";
  valid_until: string;
  supplier: Supplier;
}

function hasScreen(value: unknown, screen: string): boolean {
  return typeof value === "object" && value !== null && "screen" in value && value.screen === screen;
}

export function isCodeScreen(value: unknown): value is CodeScreenData {
  return hasScreen(value, "code");
}

export function isExpiredScreen(value: unknown): value is ExpiredScreenData {
  return hasScreen(value, "expired");
}

export function isProposalData(value: unknown): value is ProposalData {
  if (typeof value !== "object" || value === null) return false;
  return "document" in value && "supplier" in value && "quote_date" in value;
}
