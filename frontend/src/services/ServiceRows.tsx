import type { OfferingCard } from "./types";

/** The home's 「외주로 맡는 일」 rows: one hairline row per card — name → · one line. */
export function ServiceRows({ services }: { services: OfferingCard[] }) {
  return (
    <ul className="work-list feed-list">
      {services.map((card) => (
        <li key={card.slug}>
          <a className="work-row" href={card.href}>
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
