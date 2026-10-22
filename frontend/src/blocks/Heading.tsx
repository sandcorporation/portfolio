import type { ReactNode } from "react";

/** A heading the table of contents can link to. */
export function Heading({ level, id, children }: { level: 2 | 3; id: string; children: ReactNode }) {
  const Tag = level === 2 ? "h2" : "h3";
  return (
    <Tag id={id} className="block-heading">
      {children}
    </Tag>
  );
}
