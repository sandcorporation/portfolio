import { servicePath, type OfferingCard } from "./types";

/** The home's 「서비스」 rows: one hairline row per service page — name → · one line. */
export function ServiceRows({ services }: { services: OfferingCard[] }) {
  return (
    <ul className="work-list feed-list">
      {services.map((card) => (
        <li key={card.slug}>
          <a className="work-row" href={servicePath(card.slug)}>
            <span className="work-row-body">
              <span className="work-row-title">{card.name} →</span>
              <span className="work-row-summary">{card.summary}</span>
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}
