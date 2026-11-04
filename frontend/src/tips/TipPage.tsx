import { useEffect, useState } from "react";
import type { Components } from "react-markdown";
import { Prose } from "../blocks/Prose";
import { postDate } from "../blog/format";
import { Masthead, SiteFooter, SiteMeta, SiteNav } from "../brand/Masthead";
import { TipRows } from "./TipRows";
import { tipsIndexHref, type TipData } from "./types";

type CodeComponent = Components["code"];

/** The code renderer that colours fenced blocks, loaded only when the body has one: highlight.js
 * is its own chunk (issue 203), so no other page pays for it. Plain code until it arrives. */
function useHighlightedCode(markdown: string): CodeComponent | undefined {
  const [code, setCode] = useState<CodeComponent>();
  const fenced = /^\s*(```|~~~)/m.test(markdown);
  useEffect(() => {
    if (!fenced) return;
    let live = true;
    void import("./highlight").then((module) => {
      if (live) setCode(() => module.highlightedCode);
    });
    return () => {
      live = false;
    };
  }, [fenced]);
  return code;
}

/** /tips/<slug> (and its preview): the blog post's layout (.page.post: the measure, wide head) —
 * mono meta → big title → one-line summary → the markdown with coloured code → other tips of the
 * same categories → one inquiry button. */
export function TipPage({ data }: { data: TipData }) {
  const { card, related } = data;
  const code = useHighlightedCode(data.body);
  return (
    <>
      <Masthead>
        <SiteMeta availability={data.availability} />
      </Masthead>
      <SiteNav current="tips" />
      <main className="page work post tip">
        <a className="back-link" href={tipsIndexHref("")}>
          ← 팁
        </a>
        <article aria-labelledby="tip-title">
          <header className="work-head">
            <p className="meta-row">
              <time dateTime={card.published_at}>{postDate(card.published_at)}</time>
              {card.categories.map((category) => (
                <a key={category.value} href={tipsIndexHref(category.value)}>
                  {category.label}
                </a>
              ))}
            </p>
            <h1 id="tip-title" className="work-title">
              {card.title}
            </h1>
            {card.summary && <p className="work-summary">{card.summary}</p>}
            <div className="accent-rule" aria-hidden="true" />
          </header>
          <Prose source={data.body} code={code} />
        </article>
        {related.length > 0 && (
          <section className="tip-related" aria-labelledby="tip-related-title">
            <h2 id="tip-related-title" className="section-head">
              <span>같은 분류의 다른 팁</span>
            </h2>
            <TipRows tips={related} />
          </section>
        )}
        <p className="post-cta">
          <a className="cta-button" data-style="primary" href="/#home-inquiry">
            문의 →
          </a>
        </p>
      </main>
      <SiteFooter business={data.business} />
    </>
  );
}
