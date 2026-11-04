import type { Availability, Business } from "../home/types";

export interface PolicyLink {
  label: string;
  href: string;
}

/** One piece of a section. Mirrors Block in backend/services/legal.py (the only copy). */
export type PolicyBlock =
  | { kind: "p"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "table"; head: string[]; rows: string[][] }
  | { kind: "links"; items: PolicyLink[] };

export interface PolicySection {
  /** the anchor: /privacy#privacy-<id> */
  id: string;
  /** 「1. 수집하는 항목」, the number included */
  title: string;
  blocks: PolicyBlock[];
}

/** The privacy policy. Mirrors Policy in backend/services/legal.py. */
export interface Policy {
  title: string;
  effective_on: string;
  summary: string[];
  intro: string;
  operator: string;
  sections: PolicySection[];
}

/** The shell's #page-data on `/privacy`. */
export interface PrivacyData {
  policy: Policy;
  availability?: Availability | null;
  business?: Business | null;
}

export function isPrivacyData(value: unknown): value is PrivacyData {
  if (typeof value !== "object" || value === null) return false;
  return "policy" in value;
}
