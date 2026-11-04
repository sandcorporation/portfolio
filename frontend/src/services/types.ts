import type { Availability, Business } from "../home/types";

export interface OfferingItem {
  title: string;
  text: string;
}

export interface OfferingCase {
  title: string;
  /** a page of this site, or another site's https address (opens in a new tab) */
  href: string;
  /** the row's mono label: 「기록」 or 「포트폴리오」 */
  kind: string;
  note: string;
}

/** A public image of a service (issue 219). The card ignores `alt` (the name beside it says it). */
export interface OfferingImage {
  url: string;
  /** null: the size is unknown (an old upload) */
  width: number | null;
  height: number | null;
  alt: string;
  caption: string;
}

/** One service page's copy (content.Service, issue 215). Mirrors Offering in backend/services/offerings.py. */
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
  /** under the title and lead */
  cover?: OfferingImage | null;
  /** between 02 What and 03 Process */
  figure?: OfferingImage | null;
}

/** One home row. Mirrors OfferingCard in the backend. */
export interface OfferingCard {
  slug: string;
  name: string;
  summary: string;
  /** Its value in the inquiry form's 구분 (Inquiry.Kind). */
  inquiry_kind: string;
  /** The service page, or the inquiry form for a card without a page. */
  href: string;
  /** cropped into the card's thumbnail */
  cover?: OfferingImage | null;
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
