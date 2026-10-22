import { useId, useState } from "react";
import { entryFor } from "./registry";
import { anchorFor, tableOfContents } from "./toc";
import type { Document, Tab } from "./types";

interface Props {
  document: Document;
  /** Prefixes heading ids so two documents on one page never share an anchor. */
  idPrefix?: string;
}

/** The block renderer: document JSON in, screen out. Unknown block types are skipped. */
export function DocumentView({ document, idPrefix = "" }: Props) {
  const [active, setActive] = useState(0);
  const tabsId = useId();
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
        <Toc tab={tab} prefix={idPrefix} />
        {tab.blocks.map((block) => {
          const entry = entryFor(block);
          if (!entry) return null;
          return (
            <entry.Render key={block.id} block={block} anchor={anchorFor(idPrefix, block.id)} />
          );
        })}
      </div>
    </div>
  );
}

function Toc({ tab, prefix }: { tab: Tab; prefix: string }) {
  const entries = tableOfContents(tab, prefix);
  if (entries.length === 0) return null;
  return (
    <nav className="document-toc" aria-label="목차">
      <ol>
        {entries.map((entry) => (
          <li key={entry.anchor} data-level={entry.level}>
            <a href={`#${entry.anchor}`}>{entry.text}</a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
