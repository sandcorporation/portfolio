import { useMemo } from "react";
import { DocumentView } from "../blocks/DocumentView";
import { MediaUrlContext, endpointRefresher } from "../blocks/media";
import { RenderModeContext, screenMode, type RenderMode } from "../blocks/mode";
import type { Document } from "../blocks/types";
import type { ProposalData } from "./types";

/** "2026-10-01" -> "2026.10.01". Anything else is shown as written. */
export function formatDate(iso: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso.replaceAll("-", ".") : iso;
}

/** The cover comes from the proposal's own fields, so a cover block in a tab would repeat it. */
function withoutCoverBlocks(document: Document): Document {
  return {
    tabs: document.tabs.map((tab) => ({
      ...tab,
      blocks: tab.blocks.filter((block) => block.type !== "cover"),
    })),
  };
}

/**
 * The proposal document screen: cover (recipient, title, subtitle, quote date, supplier), then the
 * tabs with their table of contents. The owner's preview and the customer page both render this.
 */
export function ProposalDocument({ data }: { data: ProposalData }) {
  const { supplier } = data;
  const contact = [supplier.email, supplier.phone, supplier.address].filter(Boolean);
  const endpoint = data.media_endpoint;
  const refreshMedia = useMemo(() => (endpoint ? endpointRefresher(endpoint) : null), [endpoint]);
  const mode: RenderMode = useMemo(
    () => (data.print_mode ? { print: true, shareUrl: data.public_url ?? null } : screenMode),
    [data.print_mode, data.public_url],
  );
  return (
    <article className={data.print_mode ? "proposal proposal-print" : "proposal"} aria-labelledby="proposal-title">
      {data.preview && (
        <p className="proposal-preview-note" role="status">
          초안 미리보기 · 고객에게 공개되지 않은 화면입니다
        </p>
      )}
      <header className="proposal-cover">
        {data.recipient && <p className="cover-recipient">{data.recipient}</p>}
        <h1 id="proposal-title">{data.title}</h1>
        {data.subtitle && <p className="cover-subtitle">{data.subtitle}</p>}
        <dl className="proposal-facts">
          <div>
            <dt>견적 기준일</dt>
            <dd>{formatDate(data.quote_date)}</dd>
          </div>
          {data.valid_until && (
            <div>
              <dt>유효기간</dt>
              <dd>{formatDate(data.valid_until)}까지</dd>
            </div>
          )}
          {data.revision && (
            <div>
              <dt>문서번호</dt>
              <dd>
                {data.revision.doc_number}
                <span className="proposal-contact">{data.revision.number}차 발행본</span>
              </dd>
            </div>
          )}
          <div>
            <dt>공급자</dt>
            <dd>
              {supplier.name}
              {contact.length > 0 && <span className="proposal-contact">{contact.join(" · ")}</span>}
            </dd>
          </div>
        </dl>
      </header>
      <RenderModeContext.Provider value={mode}>
        <MediaUrlContext.Provider value={refreshMedia}>
          <DocumentView document={withoutCoverBlocks(data.document)} idPrefix="proposal-" />
        </MediaUrlContext.Provider>
      </RenderModeContext.Provider>
    </article>
  );
}
