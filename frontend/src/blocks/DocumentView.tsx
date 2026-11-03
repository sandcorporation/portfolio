import { useEffect, useId, useMemo, useRef, useState } from "react";
import { DocumentNavContext, describeTarget, type DocumentNav } from "./nav";
import { useRenderMode } from "./mode";
import { useCurrentAnchor } from "./useCurrentAnchor";
import { entryFor } from "./registry";
import { anchorFor, tableOfContents, type TocEntry } from "./toc";
import type { Document, Tab } from "./types";

interface Props {
  document: Document;
  /** Prefixes heading ids so two documents on one page never share an anchor. */
  idPrefix?: string;
  /** Do not draw the document's own on-screen contents (the home page holds two documents). Print layout ignores it. */
  hideToc?: boolean;
}

/**
 * The block renderer: document JSON in, screen out. Unknown block types are skipped. In print mode
 * (see ./mode) every tab is laid out in order under one table of contents, with no tab buttons.
 */
export function DocumentView({ document, idPrefix = "", hideToc }: Props) {
  const { print } = useRenderMode();
  return print ? (
    <PrintView document={document} idPrefix={idPrefix} />
  ) : (
    <TabbedView document={document} idPrefix={idPrefix} hideToc={hideToc} />
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

/** A move the view still has to scroll to: a block of the open tab, or the top of a tab. */
type Jump = { kind: "block" | "tab"; id: string; n: number };

function TabbedView({
  document,
  idPrefix,
  hideToc,
}: {
  document: Document;
  idPrefix: string;
  hideToc?: boolean;
}) {
  const [active, setActive] = useState(() => tabOfHash(document, window.location.hash) ?? 0);
  // Bumped on every jump, so a second jump to the same place scrolls again.
  const [jump, setJump] = useState<Jump | null>(() =>
    tabOfHash(document, window.location.hash) === null
      ? null
      : { kind: "block", id: decodeHash(window.location.hash), n: 0 },
  );
  const { onTabChange } = useRenderMode();
  const root = useRef<HTMLDivElement>(null);
  const open = (index: number) => {
    setActive(index);
    const id = document.tabs[index]?.id;
    if (id) onTabChange?.(id);
  };
  const tabsId = useId();

  // CTA buttons and `#<block id>` links share one way of moving: open the tab, then scroll.
  const nav = useMemo<DocumentNav>(() => {
    const moveTo = (index: number, kind: Jump["kind"], id: string) => {
      if (index !== active) {
        const tabId = document.tabs[index]?.id;
        if (tabId) onTabChange?.(tabId);
      }
      setActive(index);
      setJump((last) => ({ kind, id, n: (last?.n ?? 0) + 1 }));
    };
    return {
      openBlock: (blockId) => {
        const index = document.tabs.findIndex((t) => t.blocks.some((b) => b.id === blockId));
        if (index >= 0) moveTo(index, "block", blockId);
      },
      openTab: (tabId) => {
        const index = document.tabs.findIndex((t) => t.id === tabId);
        if (index >= 0) moveTo(index, "tab", tabId);
      },
      describe: (target) => describeTarget(document, target),
    };
  }, [document, onTabChange, active]);

  // A link `…/p/<slug>#<block id>` (the print QR codes) opens the tab holding that block and
  // scrolls to it; so does the address changing while the page is open.
  useEffect(() => {
    const onHashChange = () => {
      const id = decodeHash(window.location.hash);
      if (tabOfHash(document, window.location.hash) !== null) nav.openBlock(id);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [document, nav]);

  useEffect(() => {
    if (!jump) return;
    if (jump.kind === "tab") {
      root.current?.scrollIntoView?.();
      return;
    }
    const slots = window.document.querySelectorAll<HTMLElement>("[data-block-id]");
    Array.from(slots)
      .find((slot) => slot.dataset.blockId === jump.id)
      ?.scrollIntoView?.();
  }, [jump]);

  const tab = document.tabs[active] ?? document.tabs[0];
  const entries = useMemo(() => (tab ? tableOfContents(tab, idPrefix) : []), [tab, idPrefix]);
  if (!tab) return null;
  const several = document.tabs.length > 1;

  return (
    <DocumentNavContext.Provider value={nav}>
    <div className="document" ref={root}>
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
              onClick={() => open(index)}
            >
              {t.title}
            </button>
          ))}
        </div>
      )}
      <div
        className="document-body"
        id={`${tabsId}-panel`}
        role={several ? "tabpanel" : undefined}
        aria-labelledby={several ? `${tabsId}-tab-${active}` : undefined}
      >
        {!hideToc && <Toc entries={entries} spy />}
        <div className="document-blocks">
          <Blocks tab={tab} prefix={idPrefix} />
        </div>
      </div>
    </div>
    </DocumentNavContext.Provider>
  );
}

/**
 * `spy` marks the on-screen table of contents: on wide screens it sits in a side rail and the
 * entry for the section being read is highlighted (`aria-current`). The print copy never spies.
 */
function Toc({ entries, spy = false }: { entries: TocEntry[]; spy?: boolean }) {
  const current = useCurrentAnchor(entries, spy);
  const [open, setOpen] = useState(false);
  const listId = useId();
  if (entries.length === 0) return null;
  return (
    <nav className="document-toc" aria-label="목차" data-spy={spy ? "" : undefined} data-open={open ? "" : undefined}>
      {/* only the blog post shows this (CSS), below 1600px, where the list folds away */}
      <button type="button" className="document-toc-toggle" aria-expanded={open} aria-controls={listId} onClick={() => setOpen(!open)}>
        목차
      </button>
      <ul id={listId}>
        {entries.map((entry) => (
          <li key={entry.anchor} data-level={entry.level}>
            <a href={`#${entry.anchor}`} aria-current={entry.anchor === current ? "location" : undefined}>
              {entry.text}
            </a>
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
    const head: TocEntry = { text: tab.title, level: 1, anchor: tabAnchor(idPrefix, tab) };
    return [head, ...own];
  });
  const nav = useMemo<DocumentNav>(
    () => ({
      openBlock: () => {},
      openTab: () => {},
      describe: (target) => describeTarget(document, target),
    }),
    [document],
  );
  return (
    <DocumentNavContext.Provider value={nav}>
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
    </DocumentNavContext.Provider>
  );
}
