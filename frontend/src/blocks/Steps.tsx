import { Heading } from "./Heading";
import { useRenderMode } from "./mode";
import { Prose } from "./Prose";
import type { StepsBlock } from "./types";

export function Steps({ block, anchor }: { block: StepsBlock; anchor: string }) {
  const { print } = useRenderMode();
  // More than four steps do not fit across an A4 page, so paper stacks them. On screen the
  // narrow-width fold is CSS only.
  const layout = print && block.items.length > 4 ? "vertical" : block.layout;
  return (
    <section
      className="block-steps"
      data-layout={layout}
      data-numbered={block.numbered}
      data-print={print || undefined}
      aria-labelledby={block.title ? anchor : undefined}
    >
      {block.title && (
        <Heading level={3} id={anchor}>
          {block.title}
        </Heading>
      )}
      <ol className="steps-list">
        {block.items.map((item, index) => (
          <li key={item.id} className="step">
            {block.numbered && (
              <span className="step-badge" aria-hidden="true">
                {index + 1}
              </span>
            )}
            <strong className="step-title">{item.title}</strong>
            {item.body && <Prose source={item.body} />}
            {item.caption && <span className="step-caption">{item.caption}</span>}
          </li>
        ))}
      </ol>
    </section>
  );
}
