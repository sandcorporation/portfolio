import { Masthead, SiteFooter, SiteMeta, SiteNav } from "../brand/Masthead";
import { PostRows } from "./PostRows";
import { blogIndexHref, type BlogIndexData } from "./types";

/** /blog: the newest-first list, a mono tab per tag, pages of twenty. */
export function BlogIndexPage({ data }: { data: BlogIndexData }) {
  const { tag, page, pages } = data;
  return (
    <>
      <Masthead>
        <SiteMeta />
      </Masthead>
      <SiteNav current="blog" />
      <main className="page blog-index">
        <section className="page-section" aria-labelledby="blog-title">
          <p className="section-head">
            <span aria-hidden="true">Notes — 기록</span>
            <span aria-hidden="true">{data.total} posts</span>
          </p>
          <h1 id="blog-title" className="page-section-title">
            만들면서 남긴 기록
          </h1>
          {data.tags.length > 0 && (
            <nav className="tag-filter" aria-label="태그">
              <a href={blogIndexHref("")} aria-current={tag === "" ? "page" : undefined}>
                전체
              </a>
              {data.tags.map((item) => (
                <a
                  key={item.tag}
                  href={blogIndexHref(item.tag)}
                  aria-current={tag === item.tag ? "page" : undefined}
                >
                  {item.tag} <span aria-hidden="true">{item.count}</span>
                </a>
              ))}
            </nav>
          )}
          {data.posts.length > 0 ? (
            <PostRows posts={data.posts} />
          ) : (
            <p className="section-lead feed-empty">
              {tag ? `「${tag}」 태그의 글이 없습니다.` : "아직 올린 글이 없습니다."}
            </p>
          )}
          {pages > 1 && (
            <nav className="pager" aria-label="쪽">
              {page > 1 ? <a href={blogIndexHref(tag, page - 1)}>← 이전</a> : <span aria-hidden="true" />}
              <span>
                {page} / {pages}
              </span>
              {page < pages ? <a href={blogIndexHref(tag, page + 1)}>다음 →</a> : <span aria-hidden="true" />}
            </nav>
          )}
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
