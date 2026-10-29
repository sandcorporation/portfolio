import { DocumentView } from "../blocks/DocumentView";
import { Masthead, SiteFooter, SiteMeta, SiteNav } from "../brand/Masthead";
import { CardMeta } from "./PortfolioCards";
import type { WorkData } from "./types";

export function WorkPage({ data }: { data: WorkData }) {
  const { card } = data;
  return (
    <>
      <Masthead>
        <SiteMeta availability={data.availability} />
      </Masthead>
      <SiteNav current="work" />
      <main className="page work">
        <a className="back-link" href="/">
          ← 포트폴리오 목록
        </a>
        <article aria-labelledby="work-title">
          <header className="work-head">
            <CardMeta card={card} serviceUrl={data.service_url} />
            <h1 id="work-title" className="work-title">
              {card.title}
            </h1>
            {card.summary && <p className="work-summary">{card.summary}</p>}
            {card.outcome && <p className="work-outcome">{card.outcome}</p>}
            <div className="accent-rule" aria-hidden="true" />
          </header>
          {card.cover_url && <img className="work-cover sc-prose-cover" src={card.cover_url} alt="" />}
          <DocumentView document={data.body} idPrefix="work-" />
        </article>
      </main>
      <SiteFooter business={data.business} />
    </>
  );
}
