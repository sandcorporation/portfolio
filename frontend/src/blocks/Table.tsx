import { Heading } from "./Heading";
import type { TableBlock } from "./types";

export function Table({ block, anchor }: { block: TableBlock; anchor: string }) {
  const highlight = (column: number) =>
    column === block.highlight_column ? "is-highlight" : undefined;
  const footnotes = block.footnotes ?? [];
  return (
    <section className="block-table">
      {block.title && (
        <Heading level={3} id={anchor}>
          {block.title}
        </Heading>
      )}
      {block.unit && <p className="table-unit">{block.unit}</p>}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {block.columns.map((label, column) => (
                <th key={column} scope="col" className={highlight(column)}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, r) => (
              <tr key={r}>
                {row.map((cell, column) => (
                  <td key={column} className={highlight(column)}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {footnotes.length > 0 && (
        <ul className="table-footnotes">
          {footnotes.map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
