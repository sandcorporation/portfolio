import { DocumentView } from "../blocks/DocumentView";
import { Wordmark } from "../brand/Logo";
import { CardMeta } from "./PortfolioCards";
import type { WorkData } from "./types";

export function WorkPage({ data }: { data: WorkData }) {
  const { card } = data;
  return (
    <>
      <header className="masthead">
        <div className="masthead-inner">
          <Wordmark />
        </div>
      </header>
      <main className="page work">
        <a className="back-link" href="/">
          ← 포트폴리오 목록
        </a>
        <article className="sheet" aria-labelledby="work-title">
          <header className="work-head">
            <h1 id="work-title">{card.title}</h1>
            {card.summary && <p className="work-summary">{card.summary}</p>}
            <CardMeta card={card} />
          </header>
          {card.cover_url && <img className="work-cover" src={card.cover_url} alt="" />}
          <DocumentView document={data.body} idPrefix="work-" />
        </article>
      </main>
    </>
  );
}
