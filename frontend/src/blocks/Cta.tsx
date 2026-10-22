import { useDocumentNav } from "./nav";
import { useRenderMode } from "./mode";
import type { CtaBlock } from "./types";

type Item = CtaBlock["items"][number];

export function Cta({ block }: { block: CtaBlock; anchor: string }) {
  const { print } = useRenderMode();
  return (
    <div className="block-cta" data-print={print || undefined}>
      {block.items.map((item, index) => (
        <CtaItem key={index} item={item} print={print} />
      ))}
    </div>
  );
}

// The printed line adds its own arrow before the destination; a label already ending in one would double it.
function printLabel(label: string) {
  return label.replace(/[\s→]+$/u, "");
}

function CtaItem({ item, print }: { item: Item; print: boolean }) {
  const nav = useDocumentNav();
  const { target } = item;

  if (print) {
    // Paper has no buttons: the label, then where it leads.
    const where =
      target.kind === "url"
        ? target.href
        : nav.describe(target) && `→ ${nav.describe(target)}`;
    return (
      <p className="cta-line">
        <span className="cta-label">{printLabel(item.label)}</span>
        {where && <span className="cta-where"> {where}</span>}
      </p>
    );
  }

  if (target.kind === "url") {
    return (
      <a
        className="cta-button"
        data-style={item.style}
        href={target.href}
        target="_blank"
        rel="noopener noreferrer"
      >
        {item.label}
      </a>
    );
  }
  return (
    <button
      type="button"
      className="cta-button"
      data-style={item.style}
      onClick={() => (target.kind === "block" ? nav.openBlock(target.block_id) : nav.openTab(target.tab_id))}
    >
      {item.label}
    </button>
  );
}
