import type { Document } from "../blocks/types";

export interface Supplier {
  name: string;
  email: string;
  phone: string;
  address: string;
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
}

export function isProposalData(value: unknown): value is ProposalData {
  if (typeof value !== "object" || value === null) return false;
  return "document" in value && "supplier" in value && "quote_date" in value;
}
