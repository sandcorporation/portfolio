import { useRenderMode } from "./mode";
import { Prose } from "./Prose";
import type { DetailsBlock } from "./types";

export function Details({ block }: { block: DetailsBlock; anchor: string }) {
  const { print } = useRenderMode();
  // Paper has no way to open it.
  return (
    <details className="block-details" open={print || undefined}>
      <summary>{block.summary}</summary>
      <Prose source={block.body} />
    </details>
  );
}
