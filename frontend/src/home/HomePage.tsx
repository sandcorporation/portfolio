import { useState } from "react";
import { Masthead, SiteFooter, SiteMeta, SiteNav } from "../brand/Masthead";
import { DocumentView } from "../blocks/DocumentView";
import type { TocEntry } from "../blocks/toc";
import { PortfolioCards } from "../work/PortfolioCards";
import { InquiryForm } from "./InquiryForm";
import { PageToc } from "./PageToc";
import type { HomeData } from "./types";

/** Mono label (left) and optional meta (right) over a section title. */
function SectionHead({ index, label, meta }: { index: string; label: string; meta?: string }) {
  return (
    <p className="section-head" aria-hidden="true">
      <span>
        {index} — {label}
      </span>
      {meta && <span>{meta}</span>}
    </p>
  );
}

export function HomePage({ data }: { data: HomeData }) {
  const { contact } = data;
  const hasContact = Boolean(contact.email || contact.phone || contact.address);
  const [companyToc, setCompanyToc] = useState<TocEntry[]>([]);
  const [ceoToc, setCeoToc] = useState<TocEntry[]>([]);
  const section = (text: string, anchor: string): TocEntry => ({ text, level: 1, anchor });
  const hasPortfolio = data.portfolio.length > 0;
  // One contents for the whole page: each section title, then the open tab of its document.
  const entries: TocEntry[] = [
    section("회사 소개", "home-company"),
    ...companyToc,
    section("대표 소개", "home-ceo"),
    ...ceoToc,
    ...(hasPortfolio ? [section("포트폴리오", "home-portfolio")] : []),
    section("문의·제안", "home-inquiry"),
    ...(hasContact ? [section("연락처", "home-contact")] : []),
  ];
  const stack = data.stack ?? [];
  return (
    <>
      <Masthead>
        <SiteMeta />
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
              웹·모바일 서비스를 기획부터 설계·개발·배포·운영까지 한 번에 맡습니다. 만든 사람이
              운영까지 책임집니다.
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
            {hasPortfolio && <a href="#home-portfolio">포트폴리오 →</a>}
            <a href="#home-inquiry">문의 →</a>
          </p>
        </section>
        <div className="page-body">
          <PageToc entries={entries} />
          <div className="page-sections">
            <section className="page-section" aria-labelledby="home-company">
              <SectionHead index="01" label="Company" />
              <h2 id="home-company" className="page-section-title">
                회사 소개
              </h2>
              <DocumentView document={data.company_intro} idPrefix="company-" onToc={setCompanyToc} />
            </section>
            <section className="page-section" aria-labelledby="home-ceo">
              <SectionHead index="02" label="CEO" />
              <h2 id="home-ceo" className="page-section-title">
                대표 소개
              </h2>
              <DocumentView document={data.ceo_intro} idPrefix="ceo-" onToc={setCeoToc} />
            </section>
            {hasPortfolio && (
              <section className="page-section" aria-labelledby="home-portfolio">
                <SectionHead index="03" label="Work" meta={`${data.portfolio.length} projects`} />
                <h2 id="home-portfolio" className="page-section-title">
                  포트폴리오
                </h2>
                <PortfolioCards cards={data.portfolio} />
              </section>
            )}
            <section className="page-section inquiry-section" aria-labelledby="home-inquiry">
              <SectionHead index={hasPortfolio ? "04" : "03"} label="Contact" />
              <h2 id="home-inquiry" className="page-section-title">
                문의·제안
              </h2>
              <p className="section-lead">프로젝트 문의나 제안을 남겨 주시면 확인 후 답변드립니다.</p>
              <InquiryForm />
            </section>
          </div>
        </div>
      </main>
      <SiteFooter>
        {hasContact && (
          <section className="site-contact" aria-labelledby="home-contact">
            <h2 id="home-contact" className="site-contact-title">
              연락처
            </h2>
            {contact.email && (
              <p className="site-contact-email">
                <a href={`mailto:${contact.email}`}>{contact.email}</a>
              </p>
            )}
            <dl className="contact">
              {contact.phone && (
                <>
                  <dt>전화</dt>
                  <dd>
                    <a href={`tel:${contact.phone.replace(/[^0-9+]/g, "")}`}>{contact.phone}</a>
                  </dd>
                </>
              )}
              {contact.address && (
                <>
                  <dt>주소</dt>
                  <dd>{contact.address}</dd>
                </>
              )}
            </dl>
          </section>
        )}
      </SiteFooter>
    </>
  );
}
