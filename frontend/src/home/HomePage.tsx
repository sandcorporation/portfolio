import { DocumentView } from "../blocks/DocumentView";
import type { HomeData } from "./types";

export function HomePage({ data }: { data: HomeData }) {
  const { contact } = data;
  const hasContact = Boolean(contact.email || contact.phone || contact.address);
  return (
    <main className="page home">
      <section aria-labelledby="home-company">
        <h2 id="home-company" className="page-section-title">
          회사 소개
        </h2>
        <DocumentView document={data.company_intro} idPrefix="company-" />
      </section>
      <section aria-labelledby="home-ceo">
        <h2 id="home-ceo" className="page-section-title">
          대표 소개
        </h2>
        <DocumentView document={data.ceo_intro} idPrefix="ceo-" />
      </section>
      {hasContact && (
        <section aria-labelledby="home-contact">
          <h2 id="home-contact" className="page-section-title">
            연락처
          </h2>
          <dl className="contact">
            {contact.email && (
              <>
                <dt>이메일</dt>
                <dd>
                  <a href={`mailto:${contact.email}`}>{contact.email}</a>
                </dd>
              </>
            )}
            {contact.phone && (
              <>
                <dt>전화</dt>
                <dd>
                  <a href={`tel:${contact.phone.replace(/[^0-9+]/g, "")}`}>{contact.phone}</a>
                </dd>
              </>
            )}
            {contact.address && (
              <>
                <dt>주소</dt>
                <dd>{contact.address}</dd>
              </>
            )}
          </dl>
        </section>
      )}
    </main>
  );
}
