import { Heading } from "./Heading";
import { Prose } from "./Prose";
import type { MarkdownBlock } from "./types";

export function MarkdownSection({ block, anchor }: { block: MarkdownBlock; anchor: string }) {
  return (
    <section className="block-markdown">
      {block.title && (
        <Heading level={block.level ?? 2} id={anchor}>
          {block.title}
        </Heading>
      )}
      <Prose source={block.body ?? ""} />
    </section>
  );
}
