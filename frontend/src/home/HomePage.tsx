import { GITHUB_URL, Masthead, SiteFooter, SiteMeta, SiteNav } from "../brand/Masthead";
import { DocumentView } from "../blocks/DocumentView";
import { PostRows } from "../blog/PostRows";
import { PortfolioCards } from "../work/PortfolioCards";
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
      {more && <a href={more.href}>{more.text}</a>}
    </p>
  );
}

/** The hero's left sentence; kept in code with GITHUB_URL until the profile carries it. */
const HERO_LEAD =
  "웹·모바일 서비스를 기획부터 설계·개발·배포·운영까지 한 번에 맡는 1인 개발사. 재하청 없이 대표가 직접 합니다.";

const FORESIGHT_URL = "https://news.sandcorp.co.kr/?utm_source=sandcorp&utm_medium=home";

export function HomePage({ data }: { data: HomeData }) {
  const { contact } = data;
  const hasContact = Boolean(contact.email || contact.phone || contact.address);
  const hasPortfolio = data.portfolio.length > 0;
  const posts = data.posts ?? [];
  const news = data.news ?? [];
  const hasPosts = posts.length > 0;
  const hasNews = news.length > 0;
  // The mono numbers count only the sections that are shown.
  const shown = [
    "company",
    ...(hasPosts ? ["notes"] : []),
    ...(hasNews ? ["news"] : []),
    ...(hasPortfolio ? ["work"] : []),
    "contact",
  ];
  const no = (key: string) => String(shown.indexOf(key) + 1).padStart(2, "0");
  const stack = data.stack ?? [];
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
            <section className="page-section" aria-labelledby="home-company">
              <SectionHead index={no("company")} label="Company" />
              <h2 id="home-company" className="page-section-title">
                회사 소개
              </h2>
              <DocumentView document={data.company_intro} idPrefix="company-" hideToc />
            </section>
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
                <SectionHead index={no("work")} label="Work" meta={`${data.portfolio.length} projects`} />
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
                    <a href={GITHUB_URL} rel="noopener">
                      GitHub
                    </a>
                  </p>
                </div>
                <div className="inquiry-body">
                  <InquiryForm />
                </div>
              </div>
            </section>
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
