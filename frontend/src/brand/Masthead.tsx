import type { ReactNode } from "react";
import { linkAttrs } from "../links";
import type { Availability, Business, SiteVisits } from "../home/types";
import { Wordmark } from "./Logo";

export const GITHUB_URL = "https://github.com/sandcorporation";

/**
 * The band on top of every public page: wordmark and a mono line on the left, mono meta (or the
 * proposal's lock form) on the right.
 */
export function Masthead({ children }: { children?: ReactNode }) {
  return (
    <header className="masthead">
      <div className="masthead-inner">
        <div className="masthead-brand">
          <Wordmark />
          <span className="masthead-desc">샌드코프 · 웹·AI 제품 개발</span>
        </div>
        {children}
      </div>
    </header>
  );
}

const NUMBER = new Intl.NumberFormat("ko-KR");

/** 「● 누적 방문 N명」: the accent dot, the cumulative visitors of the whole site. */
export function VisitCounts({ visits }: { visits: SiteVisits }) {
  return (
    <span className="visit-counts">
      <span className="visit-dot" aria-hidden="true">
        ●
      </span>{" "}
      누적 방문 {NUMBER.format(visits.total)}
      <span className="visit-unit">명</span>
    </span>
  );
}

/** 「● 새 프로젝트 받는 중 · 갱신 2026.10」: the accent dot, the profile's text, its month. */
export function AvailabilityBadge({ availability }: { availability: Availability }) {
  return (
    <span className="availability">
      <span className="availability-dot" aria-hidden="true">
        ●
      </span>{" "}
      {availability.text}
      {availability.updated && (
        <span className="availability-updated"> · 갱신 {availability.updated}</span>
      )}
    </span>
  );
}

/** The site meta on the right of the masthead (every public page). */
export function SiteMeta({
  visits,
  availability,
}: {
  visits?: SiteVisits | null;
  availability?: Availability | null;
}) {
  return (
    <p className="masthead-meta">
      {visits && <VisitCounts visits={visits} />}
      {availability && availability.text && <AvailabilityBadge availability={availability} />}
      <span>sandcorp.co.kr</span>
      <a href={GITHUB_URL} {...linkAttrs(GITHUB_URL)}>
        GitHub
      </a>
    </p>
  );
}

/** The privacy policy (issue 201), linked from every footer. */
export const PRIVACY_PATH = "/privacy";

export const FORESIGHT_NAV_URL = "https://news.sandcorp.co.kr/?utm_source=sandcorp&utm_medium=nav";

const SITE_NAV = [
  { key: "company", href: "/#home-company", label: "회사 소개" },
  { key: "services", href: "/#home-services", label: "서비스" },
  { key: "blog", href: "/blog", label: "기록" },
  { key: "tips", href: "/tips", label: "팁" },
  { key: "foresight", href: FORESIGHT_NAV_URL, label: "Foresight ↗" },
  { key: "work", href: "/#home-portfolio", label: "포트폴리오" },
  { key: "inquiry", href: "/#home-inquiry", label: "문의" },
] as const;

/** The mono row under the masthead; the current item carries the accent square. */
export function SiteNav({ current }: { current?: "company" | "services" | "blog" | "tips" | "work" | "inquiry" }) {
  return (
    <nav className="site-nav" aria-label="사이트">
      <ul>
        {SITE_NAV.map((item) => (
          <li key={item.key}>
            <a
              href={item.href}
              {...linkAttrs(item.href)}
              aria-current={item.key === current ? "page" : undefined}
            >
              {item.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** The business line of the footer: only the filled items, in this order. */
export function businessItems(business: Business): string[] {
  const items: [string, string][] = [
    ["상호", business.name],
    ["대표", business.representative],
    ["사업자등록번호", business.number],
    ["주소", business.address],
  ];
  return items.filter(([, value]) => value).map(([label, value]) => `${label} ${value}`);
}

/** The footer: a strong rule, the business details, mono links, mono copyright. */
export function SiteFooter({ business }: { business?: Business | null }) {
  const items = business ? businessItems(business) : [];
  return (
    <footer className="site-footer">
      {items.length > 0 && (
        <ul className="site-footer-business" aria-label="사업자 정보">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      <p className="site-footer-links">
        <a href="/">홈</a>
        <a href={GITHUB_URL} {...linkAttrs(GITHUB_URL)}>
          GitHub
        </a>
        <a href={PRIVACY_PATH}>개인정보처리방침</a>
      </p>
      <p className="site-footer-copy">© Sandcorp</p>
    </footer>
  );
}
