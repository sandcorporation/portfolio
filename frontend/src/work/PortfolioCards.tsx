import type { PortfolioCard } from "./types";
import { workPath } from "./types";

export function PortfolioCards({ cards }: { cards: PortfolioCard[] }) {
  return (
    <ul className="portfolio-cards">
      {cards.map((card) => (
        <li key={card.slug}>
          <a className="portfolio-card" href={workPath(card.slug)}>
            {card.cover_url && (
              <img className="portfolio-card-cover" src={card.cover_url} alt="" loading="lazy" />
            )}
            <span className="portfolio-card-body">
              <span className="portfolio-card-title">{card.title}</span>
              {card.summary && <span className="portfolio-card-summary">{card.summary}</span>}
              <CardMeta card={card} />
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

export function CardMeta({ card }: { card: PortfolioCard }) {
  if (!card.period && card.tags.length === 0) return null;
  return (
    <span className="portfolio-meta">
      {card.period && <span className="portfolio-period">{card.period}</span>}
      {card.tags.map((tag) => (
        <span key={tag} className="portfolio-tag">
          {tag}
        </span>
      ))}
    </span>
  );
}
