import type { NewsItem } from "./types";

/** Foresight's newest articles: one hairline row each — mono category and age · title → · one
 * line of summary, a small thumbnail on the left when the article has one. */
export function NewsRows({ items }: { items: NewsItem[] }) {
  const hasThumbs = items.some((item) => item.image_url);
  return (
    <ul className={`work-list feed-list news-list${hasThumbs ? " has-thumbs" : ""}`}>
      {items.map((item) => (
        <li key={item.url}>
          <a className="work-row" href={item.url}>
            {hasThumbs && (
              <span className="work-row-thumb" aria-hidden="true">
                {item.image_url && <img src={item.image_url} alt="" loading="lazy" />}
              </span>
            )}
            <span className="work-row-body">
              <span className="work-row-meta feed-meta">
                {item.category && <span>{item.category}</span>}
                <time dateTime={item.published_at}>{item.when}</time>
              </span>
              <span className="work-row-title">{item.title} →</span>
              {item.summary && <span className="work-row-summary feed-summary feed-summary-one">{item.summary}</span>}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}
