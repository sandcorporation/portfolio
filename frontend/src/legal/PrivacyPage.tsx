import { Masthead, SiteFooter, SiteMeta, SiteNav } from "../brand/Masthead";
import { linkAttrs } from "../links";
import type { PolicyBlock, PrivacyData } from "./types";

function Block({ block }: { block: PolicyBlock }) {
  switch (block.kind) {
    case "p":
      return <p>{block.text}</p>;
    case "ul":
      return (
        <ul>
          {block.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      );
    case "table":
      return (
        <div className="sc-prose-table-scroll">
          <table>
            <thead>
              <tr>
                {block.head.map((cell) => (
                  <th key={cell} scope="col">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row) => (
                <tr key={row.join("|")}>
                  {row.map((cell, i) => (
                    <td key={i}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "links":
      return (
        <ul className="privacy-links">
          {block.items.map((link) => (
            <li key={link.href}>
              <a href={link.href} {...linkAttrs(link.href)}>
                {link.label}
              </a>
            </li>
          ))}
        </ul>
      );
  }
}

/** /privacy (issue 201): summary box, operator line, the numbered sections. The copy comes from
 * #page-data only (backend/services/legal.py). */
export function PrivacyPage({ data }: { data: PrivacyData }) {
  const p = data.policy;
  return (
    <>
      <Masthead>
        <SiteMeta availability={data.availability} />
      </Masthead>
      <SiteNav />
      <main className="page work privacy">
        <article aria-labelledby="privacy-title">
          <header className="work-head">
            <p className="meta-row">
              <span>Privacy</span>
              <span>시행 {p.effective_on}</span>
            </p>
            <h1 id="privacy-title" className="work-title">
              {p.title}
            </h1>
            <div className="accent-rule" aria-hidden="true" />
          </header>
          <div className="prose sc-prose privacy-body">
            <aside className="sc-prose-callout privacy-summary" data-kind="info" aria-label="요약">
              <p className="sc-prose-callout-title">
                <span className="sc-prose-callout-kind">요약</span>
                <strong>한눈에 보기</strong>
              </p>
              {p.summary.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </aside>
            <p>{p.intro}</p>
            <p className="privacy-operator">{p.operator}</p>
            {p.sections.map((s) => (
              <section key={s.id} aria-labelledby={`privacy-${s.id}`}>
                <h2 id={`privacy-${s.id}`}>{s.title}</h2>
                {s.blocks.map((block, i) => (
                  <Block key={i} block={block} />
                ))}
              </section>
            ))}
          </div>
        </article>
      </main>
      <SiteFooter business={data.business} />
    </>
  );
}
