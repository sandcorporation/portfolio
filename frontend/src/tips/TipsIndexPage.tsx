import { Masthead, SiteFooter, SiteMeta, SiteNav } from "../brand/Masthead";
import { TipRows } from "./TipRows";
import { tipsIndexHref, type TipsIndexData } from "./types";

export const TIPS_LEAD = "프로젝트와 상관없이 다시 쓸 수 있는 요령을 문제·원인·해법·코드 예시로 짧게 적습니다.";

/** /tips: newest-first rows, a mono chip per category in use, pages of twenty. */
export function TipsIndexPage({ data }: { data: TipsIndexData }) {
  const { category, page, pages } = data;
  const current = category?.value ?? "";
  return (
    <>
      <Masthead>
        <SiteMeta availability={data.availability} />
      </Masthead>
      <SiteNav current="tips" />
      <main className="page tips-index">
        <section className="page-section" aria-labelledby="tips-title">
          <p className="section-head">
            <span aria-hidden="true">Tips — 팁</span>
            <span aria-hidden="true">{data.total} tips</span>
          </p>
          <h1 id="tips-title" className="page-section-title">
            개발 팁
          </h1>
          <p className="section-lead">{TIPS_LEAD}</p>
          {data.categories.length > 0 && (
            <nav className="tag-filter" aria-label="분류">
              <a href={tipsIndexHref("")} aria-current={current === "" ? "page" : undefined}>
                전체
              </a>
              {data.categories.map((item) => (
                <a
                  key={item.value}
                  href={tipsIndexHref(item.value)}
                  aria-current={current === item.value ? "page" : undefined}
                >
                  {item.label} <span aria-hidden="true">{item.count}</span>
                </a>
              ))}
            </nav>
          )}
          {data.tips.length > 0 ? (
            <TipRows tips={data.tips} />
          ) : (
            <p className="section-lead feed-empty">
              {category ? `「${category.label}」 분류의 팁이 없습니다.` : "아직 올린 팁이 없습니다."}
            </p>
          )}
          {pages > 1 && (
            <nav className="pager" aria-label="쪽">
              {page > 1 ? <a href={tipsIndexHref(current, page - 1)}>← 이전</a> : <span aria-hidden="true" />}
              <span>
                {page} / {pages}
              </span>
              {page < pages ? <a href={tipsIndexHref(current, page + 1)}>다음 →</a> : <span aria-hidden="true" />}
            </nav>
          )}
        </section>
      </main>
      <SiteFooter business={data.business} />
    </>
  );
}
