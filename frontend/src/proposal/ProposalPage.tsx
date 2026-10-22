import { Wordmark } from "../brand/Logo";
import { ProposalDocument } from "./ProposalDocument";
import type { ProposalData } from "./types";

/** The document screen. On the customer page (`lockAction` set) the masthead has 「잠금」. */
export function ProposalPage({ data, lockAction }: { data: ProposalData; lockAction?: string }) {
  return (
    <>
      <header className="masthead">
        <div className="masthead-inner">
          <Wordmark />
          {lockAction && data.csrf_token && (
            <form className="lock-form" method="post" action={lockAction}>
              <input type="hidden" name="csrfmiddlewaretoken" value={data.csrf_token} />
              {data.revision && <span className="lock-doc">{data.revision.doc_number}</span>}
              <button type="submit" title="이 브라우저에서 다시 코드를 묻게 합니다">
                잠금
              </button>
            </form>
          )}
        </div>
      </header>
      <main className="page proposal-page">
        <div className="sheet">
          <ProposalDocument data={data} />
        </div>
      </main>
    </>
  );
}
