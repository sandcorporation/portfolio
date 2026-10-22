import type { CoverBlock } from "./types";

export function Cover({ block }: { block: CoverBlock; anchor: string }) {
  return (
    <header className="block-cover">
      {block.recipient && <p className="cover-recipient">{block.recipient}</p>}
      <h1>{block.title}</h1>
      {block.subtitle && <p className="cover-subtitle">{block.subtitle}</p>}
    </header>
  );
}
