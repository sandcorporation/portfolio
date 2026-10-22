import { Wordmark } from "../brand/Logo";
import { ProposalDocument } from "./ProposalDocument";
import type { ProposalData } from "./types";

export function ProposalPage({ data }: { data: ProposalData }) {
  return (
    <>
      <header className="masthead">
        <div className="masthead-inner">
          <Wordmark />
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
