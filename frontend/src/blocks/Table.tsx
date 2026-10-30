import { Heading } from "./Heading";
import type { TableBlock } from "./types";

type Cell = TableBlock["rows"][number][number];

// A merged cell is emphasised when it covers the highlighted column, not only when it starts there.
function highlightClass(column: number, span: number, highlighted: number | null | undefined) {
  return highlighted != null && column <= highlighted && highlighted < column + span
    ? "is-highlight"
    : undefined;
}

/** The <tr>s of a table body. A row lists only the cells that start in it, so the columns a
 *  rowspan from above still holds are skipped when counting. */
export function TableRows({
  rows,
  highlightColumn,
}: {
  rows: Cell[][];
  highlightColumn?: number | null;
}) {
  const occupied: Set<number>[] = rows.map(() => new Set<number>());
  return (
    <>
            {rows.map((row, r) => {
              // rows[r] lists only the cells that start in it; rowspan from above occupies columns.
              const covered = new Set<number>(occupied[r] ?? []);
              let column = 0;
              return (
                <tr key={r}>
                  {row.map((cell, c) => {
                    while (covered.has(column)) column += 1;
                    const { text, colspan, rowspan, align } =
                      typeof cell === "string"
                        ? { text: cell, colspan: 1, rowspan: 1, align: undefined }
                        : cell;
                    const start = column;
                    for (let dr = 1; dr < (rowspan ?? 1); dr += 1) {
                      const below = (occupied[r + dr] ??= new Set<number>());
                      for (let dc = 0; dc < (colspan ?? 1); dc += 1) below.add(start + dc);
                    }
                    column += colspan ?? 1;
                    return (
                      <td
                        key={c}
                        className={highlightClass(start, colspan ?? 1, highlightColumn)}
                        colSpan={colspan && colspan > 1 ? colspan : undefined}
                        rowSpan={rowspan && rowspan > 1 ? rowspan : undefined}
                        data-merged={(colspan ?? 1) > 1 || (rowspan ?? 1) > 1 ? "" : undefined}
                        data-align={align ?? undefined}
                      >
                        {text}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
    </>
  );
}

export function Table({ block, anchor }: { block: TableBlock; anchor: string }) {
  const highlight = (column: number) => highlightClass(column, 1, block.highlight_column);
  const footnotes = block.footnotes ?? [];
  return (
    <section className="block-table">
      {block.title && (
        <Heading level={3} id={anchor}>
          {block.title}
        </Heading>
      )}
      {block.unit && <p className="table-unit">{block.unit}</p>}
      <div className="sc-prose-table-scroll">
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
            <TableRows rows={block.rows} highlightColumn={block.highlight_column} />
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
