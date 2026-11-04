import { Masthead, SiteFooter, SiteMeta, SiteNav } from "../brand/Masthead";
import { linkAttrs } from "../links";
import { ZoomImage } from "./ZoomImage";
import type { OfferingImage, ServiceData } from "./types";

/** `width`/`height` keep the original ratio while loading; an upload of unknown size has none. */
function sizeAttrs(image: OfferingImage) {
  return image.width && image.height ? { width: image.width, height: image.height } : {};
}

/** A mono label over a section title, as on the home (01 — For, …). */
function Head({ index, label, id, title }: { index: string; label: string; id: string; title: string }) {
  return (
    <>
      <p className="section-head">
        <span aria-hidden="true">
          {index} — {label}
        </span>
      </p>
      <h2 id={id} className="page-section-title">
        {title}
      </h2>
    </>
  );
}

/** /services/<slug> (issue 163): who it is for → what we do → how it goes → real cases → one
 * 「견적 문의」 button to the home's form. The copy comes from #page-data only. */
export function ServicePage({ data }: { data: ServiceData }) {
  const o = data.offering;
  return (
    <>
      <Masthead>
        <SiteMeta availability={data.availability} />
      </Masthead>
      <SiteNav current="services" />
      <main className="page work service">
        <a className="back-link" href="/#home-services">
          ← 서비스
        </a>
        <article aria-labelledby="service-title">
          <header className="work-head">
            <p className="meta-row">
              <span>Service</span>
            </p>
            <h1 id="service-title" className="work-title">
              {o.name}
            </h1>
            <p className="work-summary">{o.lead}</p>
            <div className="accent-rule" aria-hidden="true" />
          </header>
          {o.cover && (
            <ZoomImage className="work-cover sc-prose-cover" src={o.cover.url} alt={o.cover.alt} {...sizeAttrs(o.cover)} />
          )}
          <section className="page-section" aria-labelledby="service-audience">
            <Head index="01" label="For" id="service-audience" title="이런 분께 맞습니다" />
            <div className="prose sc-prose">
              <ul>
                {o.audience.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          </section>
          <section className="page-section" aria-labelledby="service-scope">
            <Head index="02" label="What" id="service-scope" title="해 드리는 일" />
            <div className="prose sc-prose">
              <ul>
                {o.deliverables.map((item) => (
                  <li key={item.title}>
                    <strong>{item.title}</strong> — {item.text}
                  </li>
                ))}
              </ul>
            </div>
          </section>
          {o.figure && (
            <figure className="service-figure">
              <ZoomImage className="sc-prose-cover" src={o.figure.url} alt={o.figure.alt} loading="lazy" {...sizeAttrs(o.figure)} />
              {o.figure.caption && <figcaption>{o.figure.caption}</figcaption>}
            </figure>
          )}
          <section className="page-section" aria-labelledby="service-process">
            <Head index="03" label="Process" id="service-process" title="진행 방식" />
            <div className="prose sc-prose">
              <ol>
                {o.steps.map((item) => (
                  <li key={item.title}>
                    <strong>{item.title}</strong> — {item.text}
                  </li>
                ))}
              </ol>
            </div>
          </section>
          <section className="page-section" aria-labelledby="service-cases">
            <Head index="04" label="Cases" id="service-cases" title="실제 사례" />
            <ul className="work-list feed-list">
              {o.cases.map((item) => (
                <li key={item.href}>
                  <a className="work-row" href={item.href} {...linkAttrs(item.href)}>
                    <span className="work-row-body">
                      <span className="work-row-title">{item.title} →</span>
                      <span className="work-row-meta feed-meta">
                        <span>{item.kind}</span>
                      </span>
                      <span className="work-row-summary">{item.note}</span>
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </section>
          <section className="page-section" aria-labelledby="service-contact">
            <Head index="05" label="Contact" id="service-contact" title="문의" />
            <p className="section-lead">{o.contact}</p>
            <p className="post-cta">
              <a className="cta-button" data-style="primary" href={`/?inquiry=${o.slug}#home-inquiry`}>
                견적 문의 →
              </a>
            </p>
          </section>
        </article>
      </main>
      <SiteFooter business={data.business} />
    </>
  );
}
