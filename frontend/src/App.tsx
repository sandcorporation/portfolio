import { HomePage } from "./home/HomePage";
import { isHomeData } from "./home/types";
import { ProposalCodeScreen, ProposalExpiredScreen } from "./proposal/ProposalGate";
import { ProposalPage } from "./proposal/ProposalPage";
import { isCodeScreen, isExpiredScreen, isProposalData } from "./proposal/types";
import { WorkPage } from "./work/WorkPage";
import { isWorkData } from "./work/types";

/** Picks the page for the current path. `data` is the shell's #page-data. */
export function App({ path, data }: { path: string; data: unknown }) {
  if (path === "/" && isHomeData(data)) return <HomePage data={data} />;
  if (path.startsWith("/work/") && isWorkData(data)) return <WorkPage data={data} />;
  if (path.startsWith("/p/")) {
    if (isCodeScreen(data)) return <ProposalCodeScreen data={data} action={path} />;
    if (isExpiredScreen(data)) return <ProposalExpiredScreen data={data} />;
    if (isProposalData(data)) return <ProposalPage data={data} lockAction={`${path}/lock`} />;
  }
  if (path.startsWith("/preview/") && isProposalData(data)) return <ProposalPage data={data} />;
  return (
    <main className="placeholder">
      <h1>Sandcorp</h1>
      <p>사이트를 준비하고 있습니다.</p>
    </main>
  );
}
