import { Heading } from "./Heading";
import { useRenderMode } from "./mode";
import type { CaseRefBlock } from "./types";

/**
 * Portfolio cases. An item without `case` is a bare reference the server has not filled
 * (or whose portfolio item is gone): there is nothing to show, so it is skipped. A published
 * revision carries `case` frozen in; a draft or preview gets it filled from the live portfolio.
 */
export function CaseRef({ block, anchor }: { block: CaseRefBlock; anchor: string }) {
  const { print } = useRenderMode();
  const shown = block.items.flatMap((item) => (item.case ? [{ ...item, case: item.case }] : []));
  if (shown.length === 0) return null;
  return (
    <section className="block-case-ref" aria-labelledby={block.title ? anchor : undefined}>
      {block.title && (
        <Heading level={3} id={anchor}>
          {block.title}
        </Heading>
      )}
      <ul className="case-cards">
        {shown.map((item) => {
          const c = item.case;
          const tags = c.tags ?? [];
          const text = item.highlight || c.summary;
          return (
            <li key={item.item_id} className="case-card">
              {c.cover_url && <img className="case-cover" src={c.cover_url} alt="" loading={print ? "eager" : "lazy"} />}
              <div className="case-body">
                <strong className="case-title">{c.title}</strong>
                {c.period && <span className="case-period">{c.period}</span>}
                {text && (
                  <p className={item.highlight ? "case-text case-highlight" : "case-text"}>{text}</p>
                )}
                {tags.length > 0 && (
                  <ul className="case-tags" aria-label="태그">
                    {tags.map((tag) => (
                      <li key={tag}>{tag}</li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
