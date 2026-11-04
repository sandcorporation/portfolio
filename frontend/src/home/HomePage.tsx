import { useEffect, useState, type CSSProperties } from "react";
import { linkAttrs } from "../links";
import { GITHUB_URL, Masthead, SiteFooter, SiteMeta, SiteNav } from "../brand/Masthead";
import { DocumentView } from "../blocks/DocumentView";
import { PostRows } from "../blog/PostRows";
import { PortfolioCards } from "../work/PortfolioCards";
import { portfolioMeta } from "../work/types";
import { TipRows } from "../tips/TipRows";
import { HOME_TIP_COUNT, pickTips } from "./pickTips";
import { ServiceRows } from "../services/ServiceRows";
import { InquiryEmail } from "./InquiryEmail";
import { InquiryForm } from "./InquiryForm";
import { NewsRows } from "./NewsRows";
import type { HomeData } from "./types";

/** Mono label (left) over a section title; on the right a meta text or a link to the whole list. */
function SectionHead({
  index,
  label,
  meta,
  more,
}: {
  index: string;
  label: string;
  meta?: string;
  more?: { href: string; text: string };
}) {
  return (
    <p className="section-head">
      <span aria-hidden="true">
        {index} — {label}
      </span>
      {meta && <span aria-hidden="true">{meta}</span>}
      {more && <a href={more.href} {...linkAttrs(more.href)}>{more.text}</a>}
    </p>
  );
}

/** The hero's left sentence; kept in code with GITHUB_URL until the profile carries it. */
const HERO_LEAD =
  "웹·모바일 서비스를 기획부터 설계·개발·배포·운영까지 한 번에 맡는 1인 개발사. 재하청 없이 대표가 직접 합니다.";

const FORESIGHT_URL = "https://news.sandcorp.co.kr/?utm_source=sandcorp&utm_medium=home";

export function HomePage({ data }: { data: HomeData }) {
  const { contact } = data;
  const hasPortfolio = data.portfolio.length > 0;
  const posts = data.posts ?? [];
  const news = data.news ?? [];
  const tipPool = data.tips ?? [];
  const hasTips = tipPool.length > 0;
  // The server HTML (and so the first paint) shows the newest three; after mount the browser
  // draws three at random from the pool, so every visit differs without touching the cache.
  const [tips, setTips] = useState(() => tipPool.slice(0, HOME_TIP_COUNT));
  useEffect(() => {
    // Random on purpose after mount (not during render), so the first paint matches the server HTML.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTips(pickTips(tipPool));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per mount
  }, []);
  const hasPosts = posts.length > 0;
  const hasNews = news.length > 0;
  const services = data.services ?? [];
  const hasServices = services.length > 0;
  // The mono numbers count only the sections that are shown.
  const shown = [
    "company",
    ...(hasServices ? ["services"] : []),
    ...(hasPosts ? ["notes"] : []),
    ...(hasTips ? ["tips"] : []),
    ...(hasNews ? ["news"] : []),
    ...(hasPortfolio ? ["work"] : []),
    "contact",
  ];
  const no = (key: string) => String(shown.indexOf(key) + 1).padStart(2, "0");
  const stack = data.stack ?? [];
  const evidence = data.evidence ?? [];
  return (
    <>
      <Masthead>
        <SiteMeta visits={data.visits} availability={data.availability} />
      </Masthead>
      <SiteNav />
      <main className="page home">
        <section className="hero" aria-labelledby="home-hero-title">
          <h1 id="home-hero-title" className="display">
            SANDCORP
          </h1>
          <div className="accent-rule" aria-hidden="true" />
          <div className="hero-grid">
            <p className="hero-lead">
              {HERO_LEAD}
            </p>
            {data.tagline && <p className="hero-claim">{data.tagline}</p>}
          </div>
          {stack.length > 0 && (
            <ul className="tag-line" aria-label="기술 스택">
              {stack.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          )}
          <p className="link-row">
            <a href="#home-company">회사 소개 →</a>
            {hasPosts && <a href="#home-notes">기록 →</a>}
            {hasPortfolio && <a href="#home-portfolio">포트폴리오 →</a>}
            <a href="#home-inquiry">문의 →</a>
          </p>
        </section>
        {evidence.length > 0 && (
          <section className="evidence" aria-label="한눈에 보는 실적">
            <ul
              className="kpi-cards evidence-row"
              data-count={evidence.length}
              style={{ "--evidence-count": evidence.length } as CSSProperties}
            >
              {evidence.map((item) => (
                <li key={item.key} className="kpi-card">
                  <span className="kpi-label">{item.label}</span>
                  <strong className="kpi-value">
                    {item.value}
                    {item.unit && <small className="evidence-unit">{item.unit}</small>}
                  </strong>
                </li>
              ))}
            </ul>
          </section>
        )}
            <section className="page-section" aria-labelledby="home-company">
              <SectionHead index={no("company")} label="Company" />
              <h2 id="home-company" className="page-section-title">
                회사 소개
              </h2>
              <DocumentView document={data.company_intro} idPrefix="company-" hideToc />
            </section>
            {hasServices && (
              <section className="page-section" aria-labelledby="home-services">
                <SectionHead index={no("services")} label="Services" />
                <h2 id="home-services" className="page-section-title">
                  서비스
                </h2>
                <ServiceRows services={services} />
              </section>
            )}
            {hasPosts && (
              <section className="page-section" aria-labelledby="home-notes">
                <SectionHead
                  index={no("notes")}
                  label="Notes"
                  more={{ href: "/blog", text: "모든 기록 보기 →" }}
                />
                <h2 id="home-notes" className="page-section-title">
                  만들면서 남긴 기록
                </h2>
                <PostRows posts={posts} />
              </section>
            )}
            {hasTips && (
              <section className="page-section" aria-labelledby="home-tips">
                <SectionHead
                  index={no("tips")}
                  label="Tips"
                  more={{ href: "/tips", text: "팁 더 보기 →" }}
                />
                <h2 id="home-tips" className="page-section-title">
                  개발 팁
                </h2>
                <TipRows tips={tips} compact />
              </section>
            )}
            {hasNews && (
              <section className="page-section" aria-labelledby="home-news">
                <SectionHead
                  index={no("news")}
                  label="Foresight"
                  more={{ href: FORESIGHT_URL, text: "Foresight 보기 →" }}
                />
                <h2 id="home-news" className="page-section-title">
                  Foresight · 최근 뉴스
                </h2>
                <NewsRows items={news} />
              </section>
            )}
            {hasPortfolio && (
              <section className="page-section" aria-labelledby="home-portfolio">
                <SectionHead index={no("work")} label="Work" meta={portfolioMeta(data.portfolio)} />
                <h2 id="home-portfolio" className="page-section-title">
                  포트폴리오
                </h2>
                <PortfolioCards cards={data.portfolio} />
              </section>
            )}
            <section className="page-section inquiry-section" aria-labelledby="home-inquiry">
              <SectionHead index={no("contact")} label="Contact" />
              <div className="inquiry-layout">
                <div className="inquiry-intro">
                  <h2 id="home-inquiry" className="page-section-title">
                    문의·제안
                  </h2>
                  <p className="inquiry-lead">프로젝트 문의나 제안을 남겨 주시면 영업일 1일 안에 답합니다.</p>
                  <InquiryEmail email={contact.email} />
                  <p className="inquiry-links">
                    <a href={GITHUB_URL} {...linkAttrs(GITHUB_URL)}>
                      GitHub
                    </a>
                  </p>
                </div>
                <div className="inquiry-body">
                  <InquiryForm offerings={services} />
                </div>
              </div>
            </section>
      </main>
      <SiteFooter business={data.business} />
    </>
  );
}
