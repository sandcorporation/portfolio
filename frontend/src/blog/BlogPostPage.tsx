import { DocumentView } from "../blocks/DocumentView";
import { Masthead, SiteFooter, SiteMeta, SiteNav } from "../brand/Masthead";
import { postDate } from "./format";
import { blogIndexHref, blogPath, type BlogPostData } from "./types";

/** /blog/<slug>: mono meta → big title → lead → cover → the block document → previous / next →
 * one inquiry button. */
export function BlogPostPage({ data }: { data: BlogPostData }) {
  const { card, prev, next } = data;
  return (
    <>
      <Masthead>
        <SiteMeta availability={data.availability} />
      </Masthead>
      <SiteNav current="blog" />
      <main className="page work post">
        <a className="back-link" href={blogIndexHref("")}>
          ← 기록
        </a>
        <article aria-labelledby="post-title">
          <header className="work-head">
            <p className="meta-row">
              <time dateTime={card.published_at}>{postDate(card.published_at)}</time>
              {card.tags.map((tag) => (
                <a key={tag} href={blogIndexHref(tag)}>
                  {tag}
                </a>
              ))}
            </p>
            <h1 id="post-title" className="work-title">
              {card.title}
            </h1>
            {card.summary && <p className="work-summary">{card.summary}</p>}
            <div className="accent-rule" aria-hidden="true" />
          </header>
          {card.cover_url && <img className="work-cover" src={card.cover_url} alt="" />}
          <DocumentView document={data.body} idPrefix="post-" />
        </article>
        {(prev || next) && (
          <nav className="post-nav" aria-label="이전·다음 글">
            {prev ? (
              <a href={blogPath(prev.slug)} rel="prev">
                <span className="post-nav-label">← 이전 글</span>
                <span className="post-nav-title">{prev.title}</span>
              </a>
            ) : (
              <span aria-hidden="true" />
            )}
            {next ? (
              <a href={blogPath(next.slug)} rel="next" className="post-nav-next">
                <span className="post-nav-label">다음 글 →</span>
                <span className="post-nav-title">{next.title}</span>
              </a>
            ) : (
              <span aria-hidden="true" />
            )}
          </nav>
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
