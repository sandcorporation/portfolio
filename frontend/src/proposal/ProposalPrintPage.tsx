import { useEffect } from "react";
import { ProposalDocument } from "./ProposalDocument";
import type { ProposalData } from "./types";

/** `document.body.dataset.printReady`: "true" once fonts and images are in (or "timeout"). */
export const PRINT_READY_TIMEOUT_MS = 20000;

function imageSettled(image: HTMLImageElement): Promise<void> {
  if (image.complete) return Promise.resolve();
  return new Promise((resolve) => {
    image.addEventListener("load", () => resolve(), { once: true });
    image.addEventListener("error", () => resolve(), { once: true });
  });
}

/**
 * The page the PDF renderer opens (/print/<token>): the cover, contents and every tab, no
 * masthead or buttons. It tells the renderer when everything is drawn through
 * `document.body.dataset.printReady`.
 */
export function ProposalPrintPage({ data }: { data: ProposalData }) {
  useEffect(() => {
    const body = window.document.body;
    delete body.dataset.printReady;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (!cancelled && !body.dataset.printReady) body.dataset.printReady = "timeout";
    }, PRINT_READY_TIMEOUT_MS);
    const settle = async () => {
      await window.document.fonts?.ready;
      await Promise.all(Array.from(window.document.images).map(imageSettled));
      if (!cancelled) body.dataset.printReady = "true";
    };
    void settle();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  return (
    <main className="print-page">
      <ProposalDocument data={data} />
    </main>
  );
}
