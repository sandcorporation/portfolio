import type { ReactNode } from "react";
import type { SiteVisits } from "../home/types";
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

/** 「● 지금 N · 오늘 N명 · 누적 N명」: the dot is muted when nobody is on right now. */
export function VisitCounts({ visits }: { visits: SiteVisits }) {
  return (
    <span className="visit-counts">
      <span className={visits.live > 0 ? "visit-dot" : "visit-dot visit-dot-idle"} aria-hidden="true">
        ●
      </span>{" "}
      지금 {NUMBER.format(visits.live)} · 오늘 {NUMBER.format(visits.today)}
      <span className="visit-unit">명</span> · 누적 {NUMBER.format(visits.total)}
      <span className="visit-unit">명</span>
    </span>
  );
}

/** The site meta on the right of the masthead (home and work pages). */
export function SiteMeta({ visits }: { visits?: SiteVisits | null }) {
  return (
    <p className="masthead-meta">
      {visits && <VisitCounts visits={visits} />}
      <span>sandcorp.co.kr</span>
      <a href={GITHUB_URL} rel="noopener">
        GitHub
      </a>
    </p>
  );
}

export const FORESIGHT_NAV_URL = "https://news.sandcorp.co.kr/?utm_source=sandcorp&utm_medium=nav";

const SITE_NAV = [
  { key: "company", href: "/#home-company", label: "회사 소개" },
  { key: "blog", href: "/blog", label: "기록" },
  { key: "foresight", href: FORESIGHT_NAV_URL, label: "Foresight ↗", external: true },
  { key: "work", href: "/#home-portfolio", label: "포트폴리오" },
  { key: "inquiry", href: "/#home-inquiry", label: "문의" },
] as const;

/** The mono row under the masthead; the current item carries the accent square. */
export function SiteNav({ current }: { current?: "company" | "blog" | "work" | "inquiry" }) {
  return (
    <nav className="site-nav" aria-label="사이트">
      <ul>
        {SITE_NAV.map((item) => (
          <li key={item.key}>
            <a
              href={item.href}
              rel={"external" in item ? "noopener" : undefined}
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

/** The footer: a strong rule, the contact in large type, mono links, mono copyright. */
export function SiteFooter({ children }: { children?: ReactNode }) {
  return (
    <footer className="site-footer">
      {children}
      <p className="site-footer-links">
        <a href="/">홈</a>
        <a href={GITHUB_URL} rel="noopener">
          GitHub
        </a>
      </p>
      <p className="site-footer-copy">© Sandcorp</p>
    </footer>
  );
}
