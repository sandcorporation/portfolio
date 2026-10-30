import { Prose } from "./Prose";
import type { CalloutBlock } from "./types";

const KIND_LABEL: Record<CalloutBlock["kind"], string> = {
  info: "안내",
  warning: "주의",
  condition: "조건",
};

export function Callout({ block }: { block: CalloutBlock; anchor: string }) {
  return (
    <aside className="block-callout sc-prose-callout" data-kind={block.kind} aria-label={KIND_LABEL[block.kind]}>
      <p className="sc-prose-callout-title">
        <span className="sc-prose-callout-kind">{KIND_LABEL[block.kind]}</span>
        {block.title && <strong>{block.title}</strong>}
      </p>
      <Prose source={block.body} />
    </aside>
  );
}
