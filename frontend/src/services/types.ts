import type { Availability, Business } from "../home/types";

export interface OfferingItem {
  title: string;
  text: string;
}

export interface OfferingCase {
  title: string;
  /** a page of this site */
  href: string;
  /** the row's mono label: 「기록」 or 「포트폴리오」 */
  kind: string;
  note: string;
}

/** One service page's copy. Mirrors Offering in backend/services/offerings.py (the only copy). */
export interface Offering {
  slug: string;
  name: string;
  summary: string;
  lead: string;
  service_type: string;
  audience: string[];
  deliverables: OfferingItem[];
  steps: OfferingItem[];
  cases: OfferingCase[];
  contact: string;
}

/** One home row. Mirrors OfferingCard in the backend. */
export interface OfferingCard {
  slug: string;
  name: string;
  summary: string;
  /** Its value in the inquiry form's 구분 (Inquiry.Kind). */
  inquiry_kind: string;
}

/** The shell's #page-data on `/services/<slug>`. */
export interface ServiceData {
  offering: Offering;
  availability?: Availability | null;
  business?: Business | null;
}

export function isServiceData(value: unknown): value is ServiceData {
  if (typeof value !== "object" || value === null) return false;
  return "offering" in value;
}

export const servicePath = (slug: string) => `/services/${slug}`;
