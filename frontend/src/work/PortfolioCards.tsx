import type { PortfolioCard } from "./types";
import { workPath } from "./types";

const NUMBER = new Intl.NumberFormat("ko-KR");

/** Portfolio list: one hairline row per item — thumbnail · mono № · title → · meta · summary,
 * tags stacked on the right on wide screens. */
export function PortfolioCards({ cards }: { cards: PortfolioCard[] }) {
  return (
    <ul className="work-list">
      {cards.map((card, index) => (
        <li key={card.slug}>
          <a className="work-row" href={workPath(card.slug)}>
            <span className="work-row-thumb" aria-hidden="true">
              {card.cover_url && <img src={card.cover_url} alt="" loading="lazy" />}
            </span>
            <span className="work-row-body">
              <span className="work-row-no">№ {String(index + 1).padStart(2, "0")}</span>
              <span className="work-row-title">{card.title} →</span>
              {card.period && <span className="work-row-meta">{card.period}</span>}
              {card.visits && (
                <span className="work-row-meta work-row-visits">
                  오늘 {NUMBER.format(card.visits.today)} · 누적 {NUMBER.format(card.visits.total)}
                </span>
              )}
              {card.summary && <span className="work-row-summary">{card.summary}</span>}
            </span>
            {card.tags.length > 0 && (
              <span className="work-row-tags">
                {card.tags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </span>
            )}
          </a>
        </li>
      ))}
    </ul>
  );
}

/** The mono meta row of a work page: period · service address · tags. */
export function CardMeta({ card, serviceUrl }: { card: PortfolioCard; serviceUrl?: string }) {
  const parts = [
    card.period && <span key="period">{card.period}</span>,
    serviceUrl && (
      <a key="url" href={serviceUrl} rel="noopener">
        {serviceUrl.replace(/^https?:\/\//, "").replace(/\/$/, "")}
      </a>
    ),
    ...card.tags.map((tag) => <span key={`tag-${tag}`}>{tag}</span>),
  ].filter(Boolean);
  if (parts.length === 0) return null;
  return <p className="meta-row">{parts}</p>;
}
