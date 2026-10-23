import type { ReactNode } from "react";
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

/** The site meta on the right of the masthead (home and work pages). */
export function SiteMeta() {
  return (
    <p className="masthead-meta">
      <span>sandcorp.co.kr</span>
      <a href={GITHUB_URL} rel="noopener">
        GitHub
      </a>
    </p>
  );
}

const SITE_NAV = [
  { key: "company", href: "/#home-company", label: "회사 소개" },
  { key: "work", href: "/#home-portfolio", label: "포트폴리오" },
  { key: "inquiry", href: "/#home-inquiry", label: "문의" },
] as const;

/** The mono row under the masthead; the current item carries the accent square. */
export function SiteNav({ current }: { current?: (typeof SITE_NAV)[number]["key"] }) {
  return (
    <nav className="site-nav" aria-label="사이트">
      <ul>
        {SITE_NAV.map((item) => (
          <li key={item.key}>
            <a href={item.href} aria-current={item.key === current ? "page" : undefined}>
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
