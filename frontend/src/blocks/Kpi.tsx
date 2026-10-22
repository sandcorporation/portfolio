import { Heading } from "./Heading";
import type { KpiBlock } from "./types";

export function Kpi({ block, anchor }: { block: KpiBlock; anchor: string }) {
  return (
    <section className="block-kpi" aria-labelledby={block.title ? anchor : undefined}>
      {block.title && (
        <Heading level={3} id={anchor}>
          {block.title}
        </Heading>
      )}
      <ul className="kpi-cards">
        {block.items.map((item, index) => (
          <li key={index} className="kpi-card">
            <span className="kpi-label">{item.label}</span>
            <strong className="kpi-value">{item.value}</strong>
            {item.note && <span className="kpi-note">{item.note}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
