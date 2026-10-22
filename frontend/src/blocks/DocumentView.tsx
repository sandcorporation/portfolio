import { useEffect, useId, useState } from "react";
import { useRenderMode } from "./mode";
import { entryFor } from "./registry";
import { anchorFor, tableOfContents } from "./toc";
import type { Document, Tab } from "./types";

interface Props {
  document: Document;
  /** Prefixes heading ids so two documents on one page never share an anchor. */
  idPrefix?: string;
}

/**
 * The block renderer: document JSON in, screen out. Unknown block types are skipped. In print mode
 * (see ./mode) every tab is laid out in order under one table of contents, with no tab buttons.
 */
export function DocumentView({ document, idPrefix = "" }: Props) {
  const { print } = useRenderMode();
  return print ? (
    <PrintView document={document} idPrefix={idPrefix} />
  ) : (
    <TabbedView document={document} idPrefix={idPrefix} />
  );
}

function Blocks({ tab, prefix }: { tab: Tab; prefix: string }) {
  return tab.blocks.map((block) => {
    const entry = entryFor(block);
    if (!entry) return null;
    return (
      <div key={block.id} className="block-slot" data-block-id={block.id}>
        <entry.Render block={block} anchor={anchorFor(prefix, block.id)} />
      </div>
    );
  });
}

/** The tab holding the block that `#<block id>` names, if any. */
function tabOfHash(document: Document, hash: string): number | null {
  const id = decodeHash(hash);
  if (!id) return null;
  const index = document.tabs.findIndex((tab) => tab.blocks.some((block) => block.id === id));
  return index < 0 ? null : index;
}

function decodeHash(hash: string): string {
  const raw = hash.replace(/^#/, "");
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

function TabbedView({ document, idPrefix }: { document: Document; idPrefix: string }) {
  const [active, setActive] = useState(() => tabOfHash(document, window.location.hash) ?? 0);
  // Bumped on every jump to a block, so a second jump to the same block scrolls again.
  const [jump, setJump] = useState(0);
  const tabsId = useId();

  // A link `…/p/<slug>#<block id>` (the print QR codes) opens the tab holding that block and
  // scrolls to it; so does the address changing while the page is open.
  useEffect(() => {
    const onHashChange = () => {
      const index = tabOfHash(document, window.location.hash);
      if (index === null) return;
      setActive(index);
      setJump((n) => n + 1);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [document]);

  useEffect(() => {
    const id = decodeHash(window.location.hash);
    if (!id || tabOfHash(document, window.location.hash) === null) return;
    const slots = window.document.querySelectorAll<HTMLElement>("[data-block-id]");
    Array.from(slots)
      .find((slot) => slot.dataset.blockId === id)
      ?.scrollIntoView?.();
  }, [document, jump]);

  const tab = document.tabs[active] ?? document.tabs[0];
  if (!tab) return null;
  const several = document.tabs.length > 1;

  return (
    <div className="document">
      {several && (
        <div role="tablist" className="document-tabs">
          {document.tabs.map((t, index) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              id={`${tabsId}-tab-${index}`}
              aria-selected={index === active}
              aria-controls={`${tabsId}-panel`}
              onClick={() => setActive(index)}
            >
              {t.title}
            </button>
          ))}
        </div>
      )}
      <div
        id={`${tabsId}-panel`}
        role={several ? "tabpanel" : undefined}
        aria-labelledby={several ? `${tabsId}-tab-${active}` : undefined}
      >
        <Toc entries={tableOfContents(tab, idPrefix)} />
        <Blocks tab={tab} prefix={idPrefix} />
      </div>
    </div>
  );
}

function Toc({ entries }: { entries: { text: string; level: number; anchor: string }[] }) {
  if (entries.length === 0) return null;
  return (
    <nav className="document-toc" aria-label="목차">
      <ul>
        {entries.map((entry) => (
          <li key={entry.anchor} data-level={entry.level}>
            <a href={`#${entry.anchor}`}>{entry.text}</a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function tabAnchor(prefix: string, tab: Tab): string {
  return `${prefix}tab-${tab.id}`;
}

/**
 * Print layout: one table of contents up front, then every tab in order. The contents stop at the
 * second level (tab titles and level-2 headings): a long estimate tab alone has two dozen
 * level-3 lines.
 */
function PrintView({ document, idPrefix }: { document: Document; idPrefix: string }) {
  const several = document.tabs.length > 1;
  const entries = document.tabs.flatMap((tab) => {
    const own = tableOfContents(tab, idPrefix).filter((entry) => entry.level === 2);
    if (!several) return own;
    const head = { text: tab.title, level: 1, anchor: tabAnchor(idPrefix, tab) };
    return [head, ...own];
  });
  return (
    <div className="document document-print">
      <Toc entries={entries} />
      {document.tabs.map((tab) => (
        <section key={tab.id} className="print-tab" aria-labelledby={tabAnchor(idPrefix, tab)}>
          {several && (
            <h2 id={tabAnchor(idPrefix, tab)} className="print-tab-title">
              {tab.title}
            </h2>
          )}
          <Blocks tab={tab} prefix={idPrefix} />
        </section>
      ))}
    </div>
  );
}
