import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { startErrorReporting } from "./observability";
import { readPageData } from "./pageData";
// Shared design first (tokens, base, .sc-prose; issue 150), then portfolio tokens and components
// so portfolio rules win where they differ.
import "sandcorp-design/fonts.css";
import "sandcorp-design/css";
import "./tokens.css";
import "./styles.css";

// GlitchTip (issue 235): only when the shell handed over a DSN; the SDK loads as its own chunk.
void startErrorReporting();

// Public pages arrive with a server HTML copy in #root (issue 109, docs/adr/0002): createRoot renders
// over it on purpose — no hydration, so no hydration mismatches.
const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App path={window.location.pathname} data={readPageData()} />
    </StrictMode>,
  );
}
