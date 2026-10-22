import { Prose } from "./Prose";
import type { DetailsBlock } from "./types";

export function Details({ block }: { block: DetailsBlock; anchor: string }) {
  return (
    <details className="block-details">
      <summary>{block.summary}</summary>
      <Prose source={block.body} />
    </details>
  );
}
