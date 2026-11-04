import { postDate } from "../blog/format";
import { tipPath, type TipCard } from "./types";

/** Tip list: one hairline row per tip — title → · mono date and categories · one-line summary
 * (the blog's rows, core/templates/core/public/_tip_rows.html on the server). */
export function TipRows({ tips }: { tips: TipCard[] }) {
  return (
    <ul className="work-list feed-list tip-list">
      {tips.map((tip) => (
        <li key={tip.slug}>
          <a className="work-row" href={tipPath(tip.slug)}>
            <span className="work-row-body">
              <span className="work-row-title">{tip.title} →</span>
              <span className="work-row-meta feed-meta">
                <time dateTime={tip.published_at}>{postDate(tip.published_at)}</time>
                {tip.categories.map((category) => (
                  <span key={category.value}>{category.label}</span>
                ))}
              </span>
              {tip.summary && <span className="work-row-summary feed-summary">{tip.summary}</span>}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}
