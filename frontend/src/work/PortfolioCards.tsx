import { linkAttrs } from "../links";
import type { PortfolioCard } from "./types";
import { workPath } from "./types";

const NUMBER = new Intl.NumberFormat("ko-KR");

/** Portfolio list: one hairline row per item. From 1024px three columns — [thumbnail] · period and
 * status / title → and the result line (the summary without one) / visit counts and up to four
 * tags, right-aligned. Narrower, one stack in the same order. */
export function PortfolioCards({ cards }: { cards: PortfolioCard[] }) {
  return (
    <ul className="work-list">
      {cards.map((card) => (
        <li key={card.slug}>
          <a className="work-row portfolio-row" href={workPath(card.slug)}>
            {/* The thumbnail cell and the side columns stay (empty, no placeholder image) so the
                titles line up from row to row. */}
            <span className="portfolio-row-thumb" aria-hidden="true">
              {card.cover_url && <img src={card.cover_url} alt="" loading="lazy" />}
            </span>
            <span className="portfolio-row-when">
              {card.period && <span className="work-row-meta">{card.period}</span>}
              {card.status_label && (
                <span
                  className={`work-row-meta portfolio-row-status${card.status === "live" ? " is-live" : ""}`}
                >
                  {card.status_label}
                </span>
              )}
            </span>
            <span className="work-row-body">
              <span className="work-row-title">{card.title} →</span>
              {(card.outcome || card.summary) && (
                <span className="work-row-summary">{card.outcome || card.summary}</span>
              )}
            </span>
            <span className="portfolio-row-side">
                {card.visits && card.visits.total > 0 && (
                  <span className="work-row-meta work-row-visits">
                    누적 {NUMBER.format(card.visits.total)}
                  </span>
                )}
                {card.tags.length > 0 && (
                  <span className="work-row-tags">
                    {card.tags.slice(0, 4).map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </span>
                )}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

/** https://classroom.codemit.kr/join/x?y -> classroom.codemit.kr (host and port only; the href keeps the full address). */
export function serviceHost(url: string): string {
  return url.replace(/^https?:\/\//, "").split(/[/?#]/, 1)[0] ?? "";
}

/** The mono meta row of a work page: period · service address · tags. */
export function CardMeta({ card, serviceUrl }: { card: PortfolioCard; serviceUrl?: string }) {
  const parts = [
    card.status_label && (
      <span key="status" className="status-badge">
        {card.status_label}
      </span>
    ),
    card.period && <span key="period">{card.period}</span>,
    serviceUrl && (
      <a key="url" href={serviceUrl} rel="noopener" {...linkAttrs(serviceUrl)}>
        {serviceHost(serviceUrl)}
      </a>
    ),
    ...card.tags.map((tag) => <span key={`tag-${tag}`}>{tag}</span>),
  ].filter(Boolean);
  if (parts.length === 0) return null;
  return <p className="meta-row">{parts}</p>;
}
